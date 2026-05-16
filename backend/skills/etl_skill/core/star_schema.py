"""
backend/skills/etl_skill/core/star_schema.py
Modelisation dimensionnelle avancee : Star Schema (mono-feuille)
et Table Jointe (multi-feuilles).

Fonctions :
    decomposer_table_plate    : Decompose une table plate en Star Schema
                                via detection des dependances fonctionnelles
    detecter_schema_relationnel : Detecte FK\u2192PK entre feuilles Excel
    creer_table_jointe        : Construit la table jointe via BFS (multi-feuilles)
    sauvegarder_star_schema   : Sauvegarde tables dim_* et fact_* dans mapping_tables/

Principe central :
    Les fonctions operent sur les valeurs LISIBLES (originales).
    Elles sont appelees AVANT encode_categorical et scale_features.
    Les CSV produits dans mapping_tables/ contiennent des valeurs comprehensibles.
"""

from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

from skills.etl_skill.core.cleaner import is_protected_column

logger = logging.getLogger(__name__)


def _sans_accent(s: str) -> str:
    """Supprime les accents d'une chaine."""
    return "".join(
        c for c in unicodedata.normalize("NFD", str(s))
        if unicodedata.category(c) != "Mn"
    )


# \u2500\u2500 Decomposition Star Schema (mono-feuille) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def decomposer_table_plate(
    df: pd.DataFrame, nom_table: str,
) -> dict[str, Any]:
    """
    Decompose une table plate en Star Schema via detection des dependances
    fonctionnelles entre colonnes.

    Algorithme :
    1. Classifier les colonnes : mesures, dimensions candidates, dates, protegees
    2. Detecter les dependances fonctionnelles A donne B
       (chaque valeur de A correspond toujours a la meme valeur de B)
       Exemple : produit donne categorie (chaque produit a toujours la meme categorie)
    3. Regrouper les colonnes liees en tables de dimensions coherentes
    4. Construire la table de faits avec FK vers chaque dimension
    5. Retourner le schema complet

    Args:
        df        : DataFrame plat a decomposer (valeurs lisibles).
        nom_table : Nom de la feuille source (pour les logs et fichiers).

    Returns:
        Dict contenant :
        - schema : {fact: df_fact, dim_<nom>: df_dim, ...}
        - rapport : metadonnees de decomposition
        - has_star_schema : True si decomposition possible, False sinon
    """
    logger.info(
        "[ETL] Decomposition table plate '%s' en Star Schema...", nom_table,
    )

    # \u2500\u2500 Etape 1 : Classifier les colonnes \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    mesures: list[str] = []
    dim_cols: list[str] = []
    date_cols: list[str] = []
    protected: list[str] = []

    for col in df.columns:
        serie = df[col]
        if is_protected_column(col, serie):
            protected.append(col)
            continue
        if pd.api.types.is_datetime64_any_dtype(serie):
            date_cols.append(col)
            continue
        if pd.api.types.is_numeric_dtype(serie):
            if serie.std() > 0:
                mesures.append(col)
            else:
                protected.append(col)
            continue
        # Colonne texte : dimension si cardinalite raisonnable
        nuniq = serie.nunique()
        if 1 < nuniq <= 50:
            dim_cols.append(col)
        else:
            protected.append(col)

    if not mesures or not dim_cols:
        logger.info(
            "[ETL] Table '%s' : pas assez de mesures ou dimensions \u2192 "
            "pas de Star Schema",
            nom_table,
        )
        return {
            "schema": {nom_table: df},
            "rapport": {},
            "has_star_schema": False,
        }

    logger.info("[ETL] Mesures detectees : %s", mesures)
    logger.info("[ETL] Dimensions candidates : %s", dim_cols)

    # \u2500\u2500 Etape 2 : Detecter les dependances fonctionnelles A \u2192 B \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    dependances: dict[str, list[str]] = {c: [c] for c in dim_cols}

    for col_a in dim_cols:
        for col_b in dim_cols:
            if col_b == col_a or col_b in dependances[col_a]:
                continue
            try:
                grouped = df.groupby(col_a)[col_b].nunique()
                if (grouped <= 1).all():
                    dependances[col_a].append(col_b)
                    logger.info(
                        "[ETL] Dependance fonctionnelle : %s \u2192 %s",
                        col_a, col_b,
                    )
            except Exception:
                continue

    # \u2500\u2500 Etape 3 : Construire les groupes de dimensions (sans doublons) \u2500\u2500\u2500\u2500\u2500\u2500\u2500
    groupes_dims: list[list[str]] = []
    cols_assignees: set[str] = set()

    cols_triees = sorted(
        dim_cols, key=lambda c: len(dependances[c]), reverse=True,
    )

    for col_principale in cols_triees:
        if col_principale in cols_assignees:
            continue
        groupe = [
            c for c in dependances[col_principale]
            if c not in cols_assignees
        ]
        if groupe:
            groupes_dims.append(groupe)
            cols_assignees.update(groupe)

    logger.info("[ETL] Groupes de dimensions : %s", groupes_dims)

    # \u2500\u2500 Etape 4 : Construire le schema \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    schema: dict[str, pd.DataFrame] = {}
    rapport: dict[str, Any] = {
        "mesures": mesures,
        "dimensions": {},
        "date_columns": date_cols,
        "protected_columns": protected,
    }

    df_fact = df.copy()
    cols_fact_garder = set(mesures + date_cols + protected)

    for groupe in groupes_dims:
        col_principale = groupe[0]
        dim_name = f"dim_{_sans_accent(col_principale).lower()}"
        pk_name = f"id_{_sans_accent(col_principale).lower()}"

        # Construire la table de dimension : valeurs uniques du groupe
        df_dim_raw = df[groupe].drop_duplicates().reset_index(drop=True)
        df_dim = pd.DataFrame({pk_name: range(1, len(df_dim_raw) + 1)})
        df_dim = pd.concat([df_dim, df_dim_raw], axis=1)

        schema[dim_name] = df_dim

        # Ajouter la FK dans la table de faits
        val_to_pk: dict = {}
        for _, row in df_dim.iterrows():
            key = row[col_principale]
            val_to_pk[key] = row[pk_name]

        df_fact[pk_name] = df_fact[col_principale].map(val_to_pk)
        cols_fact_garder.add(pk_name)

        rapport["dimensions"][dim_name] = {
            "col_principale": col_principale,
            "colonnes": groupe,
            "pk": pk_name,
            "n_valeurs": len(df_dim),
        }
        logger.info(
            "[ETL] Dimension creee : '%s' (%d valeurs, colonnes=%s)",
            dim_name, len(df_dim), groupe,
        )

    # Supprimer de la table de faits les colonnes maintenant dans les dimensions
    cols_dim_toutes = set(col for g in groupes_dims for col in g)
    cols_supprimer = cols_dim_toutes - cols_fact_garder
    df_fact = df_fact.drop(columns=list(cols_supprimer), errors="ignore")

    schema["fact"] = df_fact
    rapport["fact_columns"] = df_fact.columns.tolist()

    logger.info(
        "[ETL] \u2605 Star Schema cree : fact (%d lignes � %d colonnes) "
        "+ %d dimension(s)",
        len(df_fact), len(df_fact.columns), len(groupes_dims),
    )

    return {
        "schema": schema,
        "rapport": rapport,
        "has_star_schema": True,
    }


# \u2500\u2500 Detection schema relationnel (multi-feuilles) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def detecter_schema_relationnel(
    dfs: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    """
    Detecte les relations FK\u2192PK entre feuilles d'un Excel multi-feuilles.

    Pour chaque paire de feuilles (source, cible) :
    - Cherche une colonne source contenant des valeurs presentes dans une
      colonne cible avec un fort taux de couverture (>= 80%)
    - Privilegie les colonnes au nom similaire (ex: id_etudiant \u2194 id_etudiant)

    Args:
        dfs: Dict {nom_feuille: DataFrame}.

    Returns:
        Dict avec :
        - table_fait : nom de la feuille identifiee comme table de faits
        - liaisons   : liste de {source_table, source_col, cible_table, cible_col}
    """
    if len(dfs) < 2:
        return {"table_fait": None, "liaisons": []}

    liaisons: list[dict] = []

    # Pour chaque paire ordonnee
    for nom_src, df_src in dfs.items():
        for nom_cible, df_cible in dfs.items():
            if nom_src == nom_cible:
                continue
            for col_src in df_src.columns:
                for col_cible in df_cible.columns:
                    # Filtre rapide : noms similaires
                    if _sans_accent(col_src).lower() != _sans_accent(col_cible).lower():
                        continue
                    # Verifier que cible est unique sur cette colonne (PK)
                    if df_cible[col_cible].nunique() != len(df_cible):
                        continue
                    # Verifier la couverture
                    vals_src = set(df_src[col_src].dropna().unique())
                    vals_cible = set(df_cible[col_cible].dropna().unique())
                    if not vals_src:
                        continue
                    coverage = len(vals_src & vals_cible) / len(vals_src)
                    if coverage >= 0.8:
                        liaisons.append({
                            "source_table": nom_src,
                            "source_col": col_src,
                            "cible_table": nom_cible,
                            "cible_col": col_cible,
                            "coverage": coverage,
                        })
                        logger.info(
                            "[ETL] FK detectee : %s.%s \u2192 %s.%s (coverage=%.0f%%)",
                            nom_src, col_src, nom_cible, col_cible, coverage * 100,
                        )

    # Identifier la table de faits : celle avec le plus de FK sortantes
    if not liaisons:
        return {"table_fait": None, "liaisons": []}

    compte_fk: dict[str, int] = {}
    for lien in liaisons:
        compte_fk[lien["source_table"]] = compte_fk.get(lien["source_table"], 0) + 1

    table_fait = max(compte_fk, key=compte_fk.get)
    liaisons_fait = [l for l in liaisons if l["source_table"] == table_fait]

    logger.info(
        "[ETL] Table de faits identifiee : '%s' (%d FK)",
        table_fait, len(liaisons_fait),
    )

    return {"table_fait": table_fait, "liaisons": liaisons_fait}


# \u2500\u2500 Construction Table Jointe (multi-feuilles) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def creer_table_jointe(
    dfs_propres: dict[str, pd.DataFrame],
    schema: dict[str, Any],
    stem: str,
    chemin_mapping: Path,
) -> Path | None:
    """
    Cree la table jointe depuis plusieurs feuilles via jointures successives BFS.

    Args:
        dfs_propres   : Dict {nom_feuille: DataFrame nettoye}.
        schema        : Output de detecter_schema_relationnel.
        stem          : Nom du fichier source (sans extension).
        chemin_mapping: Dossier mapping_tables/ ou ecrire le CSV.

    Returns:
        Chemin du CSV jointe genere, ou None si pas de liaisons.
    """
    nom_fait = schema.get("table_fait")
    liaisons = schema.get("liaisons", [])
    if not nom_fait or not liaisons or nom_fait not in dfs_propres:
        return None

    logger.info("[ETL] Creation de la TABLE JOINTE \u2605")

    df_joint = dfs_propres[nom_fait].copy()
    fk_suppr: list[str] = []

    for lien in liaisons:
        nom_dim = lien["cible_table"]
        col_fk = lien["source_col"]
        col_pk = lien["cible_col"]

        if nom_dim not in dfs_propres or col_fk not in df_joint.columns:
            continue
        df_dim = dfs_propres[nom_dim].copy()
        if col_pk not in df_dim.columns:
            continue

        fk_eq_pk = (col_fk == col_pk)
        conflits = set(df_joint.columns) & (set(df_dim.columns) - {col_pk})
        if conflits:
            df_dim = df_dim.rename(
                columns={c: f"{c}_{nom_dim}" for c in conflits},
            )

        if col_pk in df_joint.columns and not fk_eq_pk:
            nv_pk = f"{col_pk}_{nom_dim}"
            df_dim = df_dim.rename(columns={col_pk: nv_pk})
            col_pk_merge = nv_pk
        else:
            col_pk_merge = col_pk

        nb_avant = df_joint.shape[1]
        df_joint = df_joint.merge(
            df_dim,
            left_on=col_fk,
            right_on=col_pk_merge,
            how="left",
            suffixes=("", f"_dup_{nom_dim}"),
        )
        dups = [c for c in df_joint.columns if f"_dup_{nom_dim}" in c]
        if dups:
            df_joint = df_joint.drop(columns=dups)

        logger.info(
            "  JOIN %s.%s \u2192 %s.%s : +%d colonnes",
            nom_fait, col_fk, nom_dim, col_pk,
            df_joint.shape[1] - nb_avant,
        )

        if not fk_eq_pk and col_fk not in fk_suppr:
            fk_suppr.append(col_fk)

    a_suppr = [c for c in fk_suppr if c in df_joint.columns]
    if a_suppr:
        df_joint = df_joint.drop(columns=a_suppr)

    chemin_mapping.mkdir(parents=True, exist_ok=True)
    chemin_jointe = chemin_mapping / f"{stem}_JOINTE.csv"
    df_joint.to_csv(chemin_jointe, index=False, encoding="utf-8-sig")

    logger.info(
        "\u2605 TABLE JOINTE sauvegardee : %s (%d lignes � %d colonnes)",
        chemin_jointe.name, *df_joint.shape,
    )
    return chemin_jointe


# \u2500\u2500 Sauvegarde Star Schema dans mapping_tables/ \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def sauvegarder_star_schema(
    star_result: dict[str, Any],
    stem: str,
    nom_feuille: str,
    chemin_mapping: Path,
) -> list[Path]:
    """
    Sauvegarde les tables d'un Star Schema dans mapping_tables/.

    Genere :
    - {stem}_dim_<nom>.csv pour chaque dimension
    - {stem}_fact_<feuille>.csv pour la table de faits

    Args:
        star_result   : Output de decomposer_table_plate.
        stem          : Nom du fichier source.
        nom_feuille   : Nom de la feuille source.
        chemin_mapping: Dossier mapping_tables/ ou ecrire les CSV.

    Returns:
        Liste des chemins des fichiers crees.
    """
    if not star_result.get("has_star_schema"):
        return []

    schema = star_result.get("schema", {})
    chemin_mapping.mkdir(parents=True, exist_ok=True)
    fichiers_crees: list[Path] = []

    # Sauvegarder chaque table de dimension
    for table_name, df_table in schema.items():
        if table_name == "fact":
            continue
        csv_path = chemin_mapping / f"{stem}_{table_name}.csv"
        df_table.to_csv(csv_path, index=False, encoding="utf-8-sig")
        logger.info(
            "[ETL] Dim sauvegardee : %s (%d lignes � %d colonnes)",
            csv_path.name, *df_table.shape,
        )
        fichiers_crees.append(csv_path)

    # Sauvegarder la table de faits
    df_fact = schema.get("fact")
    if df_fact is not None:
        fact_name = f"{stem}_fact_{nom_feuille}.csv"
        fact_path = chemin_mapping / fact_name
        df_fact.to_csv(fact_path, index=False, encoding="utf-8-sig")
        logger.info(
            "[ETL] Fait sauvegarde : %s (%d lignes � %d colonnes)",
            fact_path.name, *df_fact.shape,
        )
        fichiers_crees.append(fact_path)

    return fichiers_crees