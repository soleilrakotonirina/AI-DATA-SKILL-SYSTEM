"""
backend/skills/modeling_skill/core/feature_engineer.py
Feature engineering pour le Modeling Skill.

Logique Python pure — testable independamment.
Analyse les correlations, cree des features derivees,
gere le desequilibre de classes, filtre les colonnes non-analytiques.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def analyze_feature_correlations(
    df: pd.DataFrame,
    target_column: str,
) -> Dict[str, Any]:
    """
    Analyse les correlations entre les features et avec la colonne cible.

    Identifie :
    - Les features fortement correlees avec la cible (|corr| > 0.3)
    - Les paires de features colineaires entre elles (|corr| > 0.8)
    - Le classement des features par correlation avec la cible

    Args:
        df:            DataFrame avec features et target.
        target_column: Nom de la colonne cible.

    Returns:
        Dict :
        {
          "target_correlations": {col: corr_value},
          "collinear_pairs":    [{"col_a", "col_b", "correlation"}],
          "feature_ranking":    [(col, abs_corr), ...] tri decroissant,
        }
    """
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    target_correlations: Dict[str, float] = {}
    collinear_pairs: List[Dict[str, Any]] = []

    if target_column in numeric_cols and len(numeric_cols) >= 2:
        corr_matrix = df[numeric_cols].corr(method="pearson")

        for col in numeric_cols:
            if col == target_column:
                continue
            corr_val = corr_matrix.loc[col, target_column]
            if pd.isna(corr_val):
                continue
            if abs(corr_val) > 0.3:
                target_correlations[col] = round(float(corr_val), 4)

        feature_cols = [c for c in numeric_cols if c != target_column]
        seen: set = set()

        for i, col_a in enumerate(feature_cols):
            for j, col_b in enumerate(feature_cols):
                if i >= j:
                    continue
                pair_key = tuple(sorted([col_a, col_b]))
                if pair_key in seen:
                    continue
                seen.add(pair_key)
                corr_val = corr_matrix.loc[col_a, col_b]
                if pd.isna(corr_val):
                    continue
                if abs(corr_val) > 0.8:
                    collinear_pairs.append({
                        "col_a":       col_a,
                        "col_b":       col_b,
                        "correlation": round(float(corr_val), 4),
                    })

        collinear_pairs.sort(key=lambda x: abs(x["correlation"]), reverse=True)

    feature_ranking = sorted(
        target_correlations.items(),
        key=lambda x: abs(x[1]),
        reverse=True,
    )

    logger.info(
        "[FE] Correlations : %d features liees a la cible, %d paires colineaires",
        len(target_correlations),
        len(collinear_pairs),
    )

    return {
        "target_correlations": target_correlations,
        "collinear_pairs":     collinear_pairs,
        "feature_ranking":     feature_ranking,
    }


def create_derived_features(
    df: pd.DataFrame,
    operations: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """
    Cree des features derivees a partir d'operations definies.

    Si operations=None, detecte automatiquement les colonnes skewed
    (skewness > 1 et valeurs >= 0) et applique log1p.

    Args:
        df:         DataFrame source.
        operations: Liste de dicts {type, source_columns, new_column_name}.

    Returns:
        (df_enriched, features_log).
    """
    df = df.copy()
    features_log: List[Dict[str, Any]] = []

    if operations is None:
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        operations = []
        for col in numeric_cols:
            series = df[col].dropna()
            if len(series) < 10:
                continue
            try:
                skewness = float(series.skew())
                col_min  = float(series.min())
                if abs(skewness) > 1.0 and col_min >= 0:
                    operations.append({
                        "type":            "log",
                        "source_columns":  [col],
                        "new_column_name": f"{col}_log",
                    })
            except Exception:
                continue

    for op in operations:
        op_type      = op.get("type", "")
        source_cols  = op.get("source_columns", [])
        new_col_name = op.get("new_column_name", f"derived_{len(features_log)}")

        missing = [c for c in source_cols if c not in df.columns]
        if missing:
            logger.warning("[FE] Colonnes source manquantes pour '%s' : %s", new_col_name, missing)
            continue

        try:
            if op_type == "interaction" and len(source_cols) == 2:
                df[new_col_name] = df[source_cols[0]] * df[source_cols[1]]
                features_log.append({"operation": "interaction", "column": new_col_name})

            elif op_type == "ratio" and len(source_cols) == 2:
                denominator      = df[source_cols[1]].replace(0, np.nan)
                df[new_col_name] = df[source_cols[0]] / denominator
                df[new_col_name] = df[new_col_name].replace([np.inf, -np.inf], np.nan)
                features_log.append({"operation": "ratio", "column": new_col_name})

            elif op_type == "polynomial" and len(source_cols) == 1:
                df[new_col_name] = df[source_cols[0]] ** 2
                features_log.append({"operation": "polynomial", "column": new_col_name})

            elif op_type == "log" and len(source_cols) == 1:
                df[new_col_name] = np.log1p(df[source_cols[0]])
                features_log.append({"operation": "log", "column": new_col_name})

            else:
                logger.warning("[FE] Operation inconnue : type=%s, cols=%s", op_type, source_cols)
                continue

            logger.debug("[FE] Feature creee : %s (%s)", new_col_name, op_type)

        except Exception as exc:
            logger.warning("[FE] Erreur creation feature '%s' : %s", new_col_name, exc)

    logger.info("[FE] %d features derivees creees", len(features_log))
    return df, features_log


def handle_class_imbalance(
    df: pd.DataFrame,
    target_column: str,
    method: str = "auto",
) -> Tuple[pd.DataFrame, str, float]:
    """
    Gere le desequilibre des classes dans un probleme de classification.

    Args:
        df:            DataFrame avec features et target.
        target_column: Colonne cible.
        method:        'auto', 'smote', 'class_weight', 'none'.

    Returns:
        (df_balanced, method_used, imbalance_ratio)
    """
    if target_column not in df.columns:
        logger.warning("[FE] target_column '%s' absent — pas de gestion desequilibre", target_column)
        return df, "none", 1.0

    vc = df[target_column].value_counts()
    if len(vc) < 2:
        return df, "none", 1.0

    imbalance_ratio = float(vc.iloc[0] / vc.iloc[-1])
    logger.info(
        "[FE] Desequilibre : ratio=%.2f (maj=%d, min=%d)",
        imbalance_ratio, int(vc.iloc[0]), int(vc.iloc[-1]),
    )

    if imbalance_ratio <= 3.0 or method == "none":
        logger.info("[FE] Ratio <= 3 ou method=none — aucune action")
        return df, "none", imbalance_ratio

    if method in ("smote", "auto"):
        try:
            from imblearn.over_sampling import SMOTE

            X = df.drop(columns=[target_column])
            y = df[target_column]

            X_numeric = X.select_dtypes(include="number")
            if X_numeric.shape[1] == 0:
                logger.warning("[FE] SMOTE : aucune colonne numerique, passage a class_weight")
                return df, "class_weight", imbalance_ratio

            min_samples  = int(vc.iloc[-1])
            k_neighbors  = min(5, max(1, min_samples - 1))

            if min_samples < 2:
                logger.warning("[FE] SMOTE : minorite trop petite (%d), passage a class_weight", min_samples)
                return df, "class_weight", imbalance_ratio

            smote          = SMOTE(k_neighbors=k_neighbors, random_state=42)
            X_res, y_res   = smote.fit_resample(X_numeric, y)

            df_balanced                = pd.DataFrame(X_res, columns=X_numeric.columns)
            df_balanced[target_column] = y_res

            logger.info("[FE] SMOTE applique : %d → %d lignes", len(df), len(df_balanced))
            return df_balanced, "smote", imbalance_ratio

        except ImportError:
            logger.warning("[FE] imbalanced-learn non installe — passage a class_weight")
            return df, "class_weight", imbalance_ratio
        except Exception as exc:
            logger.warning("[FE] SMOTE echoue (%s) — passage a class_weight", exc)
            return df, "class_weight", imbalance_ratio

    return df, "class_weight", imbalance_ratio


def select_analytical_features(
    df: pd.DataFrame,
    target_column: str,
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Filtre les colonnes non-analytiques avant le modeling.

    Exclut automatiquement :
    - IDs sequentiels ou codes (id_*, *_id, *_code, matricule...)
    - Contacts (email, telephone, mobile, fax)
    - Noms propres non-analytiques (nom, prenom, *_Enseignants)
    - Constantes (< 2 valeurs uniques)
    - Dates au format string YYYY-MM-DD (encodage one-hot inutile)
    - Bureau / salle / code interne (A272, B251...)
    - Texte a cardinalite quasi-unique (>= 50% valeurs uniques et > 15 valeurs)

    Conserve toujours :
    - La colonne cible (target_column)
    - Les colonnes numeriques analytiques non-ID
    - Les colonnes categorielles analytiques (cardinalite raisonnable)

    Args:
        df:            DataFrame source.
        target_column: Colonne cible — toujours conservee.

    Returns:
        (df_filtered, excluded_cols) :
        - df_filtered   : DataFrame sans les colonnes non-analytiques.
        - excluded_cols : Liste des colonnes exclues avec raison.
    """
    _RE_ID = re.compile(
        r"(^id[_\s]|[_\s]id$|.*_id$|.*_code$"
        r"|^num[_\s]?$|^numero$|^matricule$|^uuid$|^pk$|^fk$"
        r"|^id_inscription$|^id_etudiant$|^id_cours$|^id_enseignant$)",
        re.IGNORECASE,
    )
    _KW_CONTACT = [
        "telephone", "tel", "phone", "mobile", "portable",
        "email", "mail", "fax",
    ]
    _RE_NOM = re.compile(
        r"(^nom$|^prenom$|^firstname$|^lastname$"
        r"|^nom_|_nom$|^prenom_|_prenom$"
        r"|nom_enseignants|prenom_enseignants)",
        re.IGNORECASE,
    )

    excluded: List[str] = []
    n_rows = len(df)

    for col in df.columns:
        if col == target_column:
            continue

        col_l = col.lower().strip()
        serie = df[col]

        # 1. Constante
        if serie.nunique() < 2:
            excluded.append(col)
            logger.debug("[FE] Exclu (constante) : %s", col)
            continue

        # 2. ID sequentiel ou code
        if _RE_ID.match(col_l):
            excluded.append(col)
            logger.debug("[FE] Exclu (ID) : %s", col)
            continue

        # 3. Contact
        if any(kw in col_l for kw in _KW_CONTACT):
            excluded.append(col)
            logger.debug("[FE] Exclu (contact) : %s", col)
            continue

        # 4. Nom propre
        if _RE_NOM.search(col_l):
            excluded.append(col)
            logger.debug("[FE] Exclu (nom propre) : %s", col)
            continue

        # 5. Date au format string YYYY-MM-DD
        if pd.api.types.is_string_dtype(serie) or serie.dtype == object:
            sample = serie.dropna().astype(str).head(20)
            if len(sample) > 0:
                date_ratio = sample.str.match(r"^\d{4}-\d{2}-\d{2}$").mean()
                if date_ratio >= 0.7:
                    excluded.append(col)
                    logger.debug("[FE] Exclu (date string YYYY-MM-DD) : %s", col)
                    continue

        # 6. Bureau / salle / code interne
        if any(kw in col_l for kw in ["bureau", "salle", "office", "room", "batiment"]):
            excluded.append(col)
            logger.debug("[FE] Exclu (bureau/salle) : %s", col)
            continue

        # 7. Texte a cardinalite quasi-unique (>= 50% valeurs uniques)
        if pd.api.types.is_string_dtype(serie) or serie.dtype == object:
            n_unique = serie.nunique()
            if n_rows >= 50 and n_unique / n_rows >= 0.50 and n_unique > 15:
                excluded.append(col)
                logger.debug(
                    "[FE] Exclu (cardinalite quasi-unique %.0f%%) : %s",
                    n_unique / n_rows * 100, col,
                )
                continue

    df_filtered = df.drop(columns=excluded, errors="ignore")
    logger.info(
        "[FE] Features : %d colonnes conservees, %d exclues (IDs/contacts/constantes)",
        df_filtered.shape[1], len(excluded),
    )
    if excluded:
        logger.info("[FE] Colonnes exclues : %s", excluded[:10])

    return df_filtered, excluded