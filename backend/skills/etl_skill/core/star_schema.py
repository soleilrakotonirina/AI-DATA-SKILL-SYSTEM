"""
backend/skills/etl_skill/core/star_schema.py
Modelisation dimensionnelle automatique.
"""

from __future__ import annotations

import logging
import re
from collections import deque
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _contient_pattern_attribut(series: pd.Series) -> bool:
    sample = series.dropna().astype(str).head(30)
    if sample.empty:
        return False
    if sample.str.contains("@", regex=False).mean() > 0.5:
        return True
    if sample.str.lower().str.contains(r"http|www\.", regex=True).mean() > 0.3:
        return True
    cleaned = sample.str.replace(r"[\s\+\-\.\(\)]", "", regex=True)
    if cleaned.str.match(r"^\d{8,15}$").mean() > 0.5:
        return True
    return False


def _est_temporelle(col: str, series: pd.Series) -> bool:
    cl = col.lower()
    mots = ("annee", "year", "mois", "month", "trimestre",
            "quarter", "semestre", "periode")
    if any(m in cl for m in mots):
        return True
    try:
        vals = series.dropna()
        if pd.api.types.is_integer_dtype(vals) and len(vals) > 0:
            vmin, vmax = float(vals.min()), float(vals.max())
            if 1900 <= vmin and vmax <= 2100 and vals.nunique() <= 20:
                return True
            if 1 <= vmin and vmax <= 12 and vals.nunique() <= 12:
                if set(vals.unique()).issubset(set(range(1, 13))):
                    return True
    except Exception:
        pass
    return False


def _est_dimension(col: str, series: pd.Series, n_rows: int) -> bool:
    n_unique = series.nunique()
    if n_unique <= 1 or n_unique > 30:
        return False
    if pd.api.types.is_datetime64_any_dtype(series):
        return False
    cl = col.lower()
    if cl.startswith("date_") or cl.endswith("_date") or cl == "date":
        return False
    if _contient_pattern_attribut(series):
        return False
    if _est_temporelle(col, series):
        return True
    if n_rows <= 20:
        seuil = 0.70
    elif n_rows <= 50:
        seuil = 0.65
    elif n_rows <= 200:
        seuil = 0.50
    else:
        seuil = 0.40
    ratio = n_unique / n_rows
    return ratio <= seuil


def _est_mesure(col: str, series: pd.Series) -> bool:
    try:
        vals = series.dropna()
        if len(vals) == 0:
            return False
        vmin = float(vals.min())
        vmax = float(vals.max())
        if (pd.api.types.is_integer_dtype(vals)
                and 1900 <= vmin and vmax <= 2100
                and vals.nunique() <= 20):
            return False
        if (pd.api.types.is_integer_dtype(vals)
                and 1 <= vmin and vmax <= 12
                and vals.nunique() <= 12
                and set(vals.unique()).issubset(set(range(1, 13)))):
            return False
        if vmin > 10_000:
            mean_val = float(vals.mean())
            std_val = float(vals.std())
            if mean_val > 0 and std_val / mean_val < 0.20:
                return False
        if vals.std() == 0:
            return False
    except Exception:
        pass
    return True


def _grouper_colonnes_correlees(
    df: pd.DataFrame, candidates: list[str]
) -> list[tuple[str, list[str]]]:
    """
    Regroupe les colonnes dimensionnelles qui décrivent la même entité.

    Deux colonnes sont considérées co-dépendantes si leur mapping est
    bijectif (même cardinalité et correlation fonctionnelle >= 95%).
    Retourne une liste de (col_principale, [col1, col2, ...]).
    La colonne principale est celle au nom le plus court (label lisible).
    """
    remaining = list(candidates)
    groups: list[list[str]] = []

    while remaining:
        col = remaining.pop(0)
        group = [col]
        to_remove = []
        for other in remaining:
            try:
                # Correlation fonctionnelle : col → other
                paired = df[[col, other]].dropna()
                if len(paired) == 0:
                    continue
                # Chaque valeur de col mappe-t-elle toujours la même valeur de other ?
                mapping_fwd = paired.groupby(col)[other].nunique().max()
                mapping_bwd = paired.groupby(other)[col].nunique().max()
                if mapping_fwd == 1 and mapping_bwd == 1:
                    group.append(other)
                    to_remove.append(other)
            except Exception:
                continue
        for c in to_remove:
            remaining.remove(c)
        groups.append(group)

    result = []
    for group in groups:
        # Colonne principale = la plus courte (favorise les labels humains)
        principal = min(group, key=lambda c: (len(c), c))
        result.append((principal, group))
    return result


def decomposer_table_plate(df: pd.DataFrame, nom_feuille: str) -> dict[str, Any]:
    n_rows = len(df)

    mesures: list[str] = []
    for col in df.columns:
        cl = col.lower()
        if cl.startswith("id_") or cl.endswith("_id") or cl == "id":
            continue
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue
        if df[col].nunique() <= 1 or df[col].std() == 0:
            continue
        if not _est_mesure(col, df[col]):
            continue
        mesures.append(col)

    dim_candidates: list[str] = []
    for col in df.columns:
        cl = col.lower()
        if cl.startswith("id_") or cl.endswith("_id") or cl == "id":
            continue
        if col in mesures:
            continue
        if not _est_dimension(col, df[col], n_rows):
            continue
        dim_candidates.append(col)

    if not dim_candidates:
        logger.info("[StarSchema] %s : aucune dimension (n_rows=%d)", nom_feuille, n_rows)
        return {"has_star_schema": False}

    # Regrouper les colonnes co-dépendantes (ex: country_value + countryiso3code)
    dim_groups = _grouper_colonnes_correlees(df, dim_candidates)

    fact_df = df.copy()
    dimensions: dict[str, pd.DataFrame] = {}
    rapport_dims: dict[str, dict] = {}

    for col_principale, group_cols in dim_groups:
        dim_name = f"dim_{col_principale}"
        id_col = f"id_{col_principale}"
        dim_df = df[group_cols].drop_duplicates().reset_index(drop=True)
        dim_df.insert(0, id_col, range(1, len(dim_df) + 1))
        dimensions[dim_name] = dim_df
        mapping = dict(zip(dim_df[col_principale], dim_df[id_col]))
        fact_df[id_col] = fact_df[col_principale].map(mapping)
        fact_df = fact_df.drop(columns=group_cols)
        rapport_dims[dim_name] = {
            "col_principale": col_principale,
            "colonnes": group_cols,
            "n_valeurs": int(dim_df[col_principale].nunique()),
        }
        logger.info(
            "[StarSchema] %s dim %s : %d valeurs, colonnes=%s",
            nom_feuille, dim_name, rapport_dims[dim_name]["n_valeurs"], group_cols,
        )

    logger.info("[StarSchema] %s : %d dim, %d mesures, fact=%d x %d",
                nom_feuille, len(dimensions), len(mesures),
                len(fact_df), fact_df.shape[1])

    return {
        "has_star_schema": True,
        "fact_df": fact_df,
        "dimensions": dimensions,
        "rapport": {
            "dimensions": rapport_dims,
            "mesures": mesures,
            "fact_columns": list(fact_df.columns),
        },
    }


def sauvegarder_star_schema(star_result: dict, stem: str,
                             nom_feuille: str, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^a-zA-Z0-9_-]", "_", stem)
    safe_feuille = re.sub(r"[^a-zA-Z0-9_-]", "_", nom_feuille)
    fichiers: list[Path] = []

    for dim_name, dim_df in star_result.get("dimensions", {}).items():
        path = output_dir / f"{safe_stem}_{dim_name}.csv"
        dim_df.to_csv(path, index=False, encoding="utf-8")
        fichiers.append(path)
        logger.info("[StarSchema] Dim : %s (%d lignes)", path.name, len(dim_df))

    fact_df = star_result.get("fact_df")
    if fact_df is not None:
        path = output_dir / f"{safe_stem}_fact_{safe_feuille}.csv"
        fact_df.to_csv(path, index=False, encoding="utf-8")
        fichiers.append(path)
        logger.info("[StarSchema] Fait : %s (%d lignes)", path.name, len(fact_df))

    return fichiers


def detecter_schema_relationnel(feuilles: dict[str, pd.DataFrame],
                                  coverage_min: float = 0.5) -> dict:
    pks: dict[str, str] = {}
    for table, df in feuilles.items():
        for col in df.columns:
            cl = col.lower()
            is_id = cl.startswith("id_") or cl.endswith("_id") or cl == "id"
            if is_id and df[col].nunique() == len(df[col].dropna()):
                pks[table] = col
                break

    all_liaisons: list[dict] = []
    for src_table, df_src in feuilles.items():
        for col in df_src.columns:
            cl = col.lower()
            if not (cl.startswith("id_") or cl.endswith("_id")):
                continue
            for cible_table, df_cible in feuilles.items():
                if cible_table == src_table:
                    continue
                if pks.get(cible_table) != col:
                    continue
                vals_src = df_src[col].dropna()
                vals_cible = df_cible[col].dropna()
                if len(vals_src) == 0:
                    continue
                coverage = float(vals_src.isin(vals_cible).mean())
                if coverage < coverage_min:
                    continue
                all_liaisons.append({
                    "source_table": src_table,
                    "source_col": col,
                    "cible_table": cible_table,
                    "cible_col": col,
                    "coverage": round(coverage, 4),
                })
                logger.info("[StarSchema] Liaison : %s.%s -> %s (%.0f%%)",
                            src_table, col, cible_table, coverage * 100)

    if not all_liaisons:
        return {}

    fk_count: dict[str, int] = {}
    for l in all_liaisons:
        fk_count[l["source_table"]] = fk_count.get(l["source_table"], 0) + 1
    pk_tables = {l["cible_table"] for l in all_liaisons}
    candidates = {t: n for t, n in fk_count.items() if t not in pk_tables}
    if not candidates:
        candidates = fk_count
    table_fait = max(candidates, key=lambda t: candidates[t])

    adjacency: dict[str, list[dict]] = {}
    for l in all_liaisons:
        adjacency.setdefault(l["source_table"], []).append(l)

    ordre: list[dict] = []
    visited: set[str] = {table_fait}
    queue: deque = deque([table_fait])
    while queue:
        current = queue.popleft()
        for lien in adjacency.get(current, []):
            if lien["cible_table"] not in visited:
                visited.add(lien["cible_table"])
                ordre.append(lien)
                queue.append(lien["cible_table"])

    logger.info("[StarSchema] Schema : table_fait=%s, %d liaison(s), %d table(s)",
                table_fait, len(all_liaisons), len(visited))
    return {
        "table_fait": table_fait,
        "liaisons": all_liaisons,
        "ordre_jointures": ordre,
    }


def creer_table_jointe(feuilles: dict[str, pd.DataFrame], schema_rel: dict,
                        stem: str, output_dir: Path) -> Optional[Path]:
    table_fait = schema_rel.get("table_fait", "")
    ordre = schema_rel.get("ordre_jointures", schema_rel.get("liaisons", []))

    if not table_fait or table_fait not in feuilles:
        logger.warning("[StarSchema] table_fait %s introuvable", table_fait)
        return None

    df_result = feuilles[table_fait].copy()
    tables_jointes: set[str] = {table_fait}

    for lien in ordre:
        cible_table = lien["cible_table"]
        src_col = lien["source_col"]
        cible_col = lien["cible_col"]

        if cible_table in tables_jointes or cible_table not in feuilles:
            continue

        col_in_result = src_col
        if src_col not in df_result.columns:
            variant = f"{src_col}_{lien['source_table']}"
            if variant in df_result.columns:
                col_in_result = variant
            else:
                logger.warning("[StarSchema] %s absent — jointure %s ignoree",
                               src_col, cible_table)
                continue

        df_cible = feuilles[cible_table].copy()
        cols_rename = {
            c: f"{c}_{cible_table}"
            for c in df_cible.columns
            if c != cible_col and c in df_result.columns
        }
        if cols_rename:
            df_cible = df_cible.rename(columns=cols_rename)

        df_result = df_result.merge(
            df_cible, left_on=col_in_result, right_on=cible_col,
            how="left", suffixes=("", f"_{cible_table}"),
        )
        tables_jointes.add(cible_table)
        logger.info("[StarSchema] Jointure : %s -> %s (%d lignes, %d cols)",
                    src_col, cible_table, len(df_result), df_result.shape[1])

    output_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^a-zA-Z0-9_-]", "_", stem)
    output_path = output_dir / f"{safe_stem}_JOINTE.csv"
    df_result.to_csv(output_path, index=False, encoding="utf-8")
    logger.info("[StarSchema] Table jointe : %s (%d x %d)",
                output_path.name, len(df_result), df_result.shape[1])
    return output_path