"""
backend/skills/etl_skill/core/validator.py
Generation de rapports qualite et validation de l'integrite referentielle.

Fonctions principales :
    generate_quality_report        : Rapport detaille avant/apres sur la qualite
    validate_referential_integrity : Verification des cles etrangeres
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def generate_quality_report(
    df: pd.DataFrame,
    label: str = "initial",
    output_dir: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """
    Genere un rapport de qualite detaille d'un DataFrame.

    Contenu du rapport :
    - Shape globale, taux de nullite global, nb doublons
    - Par colonne : nb nulls, % nulls, type, nb valeurs uniques
    - Stats descriptives pour les colonnes numeriques
    - Distribution top 10 pour les colonnes categorielles

    Ecriture du rapport en Markdown dans output_dir/etl_quality_report_{label}.md.

    Args:
        df        : DataFrame a analyser.
        label     : Etiquette du rapport ('initial', 'after', ou nom libre).
        output_dir: Dossier de sortie pour le fichier Markdown.
                    Par defaut 'outputs/'.

    Returns:
        Tuple (rapport_dict, chemin_fichier_markdown).
    """
    out_dir = Path(output_dir) if output_dir else Path("outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"etl_quality_report_{label}.md"

    # ── Calculs globaux ───────────────────────────────────────────────────────
    total_cells = df.size
    total_nulls = int(df.isnull().sum().sum())
    global_null = (
        round(total_nulls / total_cells * 100, 2) if total_cells > 0 else 0.0
    )
    n_duplicates = int(df.duplicated().sum())

    # ── Calculs par colonne ───────────────────────────────────────────────────
    per_column: dict[str, dict] = {}
    for col in df.columns:
        n_null = int(df[col].isnull().sum())
        pct_null = round(n_null / len(df) * 100, 2) if len(df) > 0 else 0.0
        maybe_numeric = False

        if pd.api.types.is_string_dtype(df[col]) or df[col].dtype == object:
            converted = pd.to_numeric(df[col].dropna(), errors="coerce")
            if len(converted) > 0 and converted.notna().mean() > 0.8:
                maybe_numeric = True

        per_column[col] = {
            "dtype": str(df[col].dtype),
            "n_null": n_null,
            "pct_null": pct_null,
            "n_unique": int(df[col].nunique()),
            "maybe_numeric": maybe_numeric,
        }

    # ── Stats descriptives numeriques ─────────────────────────────────────────
    numeric_stats: dict[str, dict] = {}
    for col in df.select_dtypes(include=[np.number]).columns:
        s = df[col].dropna()
        if len(s) == 0:
            continue
        numeric_stats[col] = {
            "mean": round(float(s.mean()), 4),
            "std": round(float(s.std()), 4),
            "min": round(float(s.min()), 4),
            "25%": round(float(s.quantile(0.25)), 4),
            "50%": round(float(s.median()), 4),
            "75%": round(float(s.quantile(0.75)), 4),
            "max": round(float(s.max()), 4),
        }

    # ── Distribution categorielles ────────────────────────────────────────────
    categorical_dist: dict[str, dict] = {}
    str_cols = [
        c for c in df.columns
        if df[c].dtype == object or pd.api.types.is_string_dtype(df[c])
    ]
    for col in str_cols:
        vc = df[col].value_counts().head(10)
        categorical_dist[col] = vc.to_dict()

    # ── Rapport dict ──────────────────────────────────────────────────────────
    rapport = {
        "label": label,
        "shape": list(df.shape),
        "n_rows": int(df.shape[0]),
        "n_cols": int(df.shape[1]),
        "global_null_rate_pct": global_null,
        "total_nulls": total_nulls,
        "n_duplicates": n_duplicates,
        "per_column": per_column,
        "numeric_stats": numeric_stats,
        "categorical_dist": categorical_dist,
    }

    # ── Generation Markdown ───────────────────────────────────────────────────
    lines = [
        f"# Rapport Qualite — {label}",
        "",
        "## Vue d'ensemble",
        "",
        "| Indicateur | Valeur |",
        "|------------|--------|",
        f"| Shape | {df.shape[0]} lignes × {df.shape[1]} colonnes |",
        f"| Taux de nullite global | {global_null}% |",
        f"| Valeurs manquantes | {total_nulls} |",
        f"| Lignes dupliquees | {n_duplicates} |",
        "",
        "## Detail par Colonne",
        "",
        "| Colonne | Type | Nulls | % Nulls | Valeurs uniques | Remarque |",
        "|---------|------|-------|---------|-----------------|----------|",
    ]

    for col, s in per_column.items():
        remark = "⚠ Peut etre numerique" if s["maybe_numeric"] else ""
        lines.append(
            f"| {col} | {s['dtype']} | {s['n_null']} | {s['pct_null']}% | {s['n_unique']} | {remark} |"
        )

    if numeric_stats:
        lines += [
            "",
            "## Statistiques Descriptives (numeriques)",
            "",
            "| Colonne | Mean | Std | Min | 25% | Mediane | 75% | Max |",
            "|---------|------|-----|-----|-----|---------|-----|-----|",
        ]
        for col, s in numeric_stats.items():
            lines.append(
                f"| {col} | {s['mean']} | {s['std']} | {s['min']} | {s['25%']} | {s['50%']} | {s['75%']} | {s['max']} |"
            )

    if categorical_dist:
        lines += ["", "## Distribution Categorielles (top 10)", ""]
        for col, dist in categorical_dist.items():
            lines += [f"### {col}", "", "| Valeur | Count |", "|--------|-------|"]
            for val, cnt in dist.items():
                lines.append(f"| {val} | {cnt} |")
            lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Rapport qualite '%s' ecrit : %s", label, report_path)

    return rapport, report_path


def validate_referential_integrity(
    df_fact: pd.DataFrame,
    dim_dict: dict[str, tuple[pd.DataFrame, str]],
) -> dict[str, dict[str, Any]]:
    """
    Valide l'integrite referentielle entre une table de faits et ses dimensions.

    Pour chaque dimension, verifie que les valeurs de la FK dans df_fact
    existent toutes dans la PK de la table de dimension.

    Args:
        df_fact: Table de faits contenant les cles etrangeres.
        dim_dict: Dictionnaire {nom_dimension: (df_dimension, colonne_pk)}.

    Returns:
        Dict {nom_dimension: {fk_column, status, invalid_count,
        invalid_values_sample}}.
        Status : 'ok', 'missing_fk', 'missing_pk', ou 'violations_found'.
    """
    results: dict[str, dict[str, Any]] = {}

    for dim_name, (df_dim, pk_col) in dim_dict.items():
        # Verification de l'existence de la FK dans df_fact
        if pk_col not in df_fact.columns:
            results[dim_name] = {
                "fk_column": pk_col,
                "status": "missing_fk",
                "invalid_count": 0,
                "invalid_values_sample": [],
            }
            logger.warning(
                "Integrite '%s' : FK manquante dans table de faits", dim_name
            )
            continue

        # Verification de l'existence de la PK dans la dimension
        if pk_col not in df_dim.columns:
            results[dim_name] = {
                "fk_column": pk_col,
                "status": "missing_pk",
                "invalid_count": 0,
                "invalid_values_sample": [],
            }
            logger.warning("Integrite '%s' : PK manquante dans dimension", dim_name)
            continue

        # Verification des valeurs
        valid_pks = set(df_dim[pk_col].dropna().tolist())
        fk_values = df_fact[pk_col].dropna()
        invalid = fk_values[~fk_values.isin(valid_pks)]
        n_inv = int(len(invalid))

        results[dim_name] = {
            "fk_column": pk_col,
            "status": "ok" if n_inv == 0 else "violations_found",
            "invalid_count": n_inv,
            "invalid_values_sample": invalid.head(10).tolist(),
        }

        if n_inv > 0:
            logger.warning("Integrite '%s' : %d violation(s)", dim_name, n_inv)
        else:
            logger.info("Integrite '%s' : OK", dim_name)

    return results