"""
backend/skills/etl_skill/core/transformer.py
Encodage, scaling, outliers, feature engineering, modelisation dimensionnelle.

REGLE CENTRALE :
  Les colonnes protegees (IDs, emails, telephones, dates, noms libres)
  sont TOUJOURS exclues de l'encodage et du scaling.
  Seules les colonnes categorielles a faible cardinalite sont encodees.
  Seules les colonnes numeriques mesures sont scalees.

Fonctions principales :
    encode_categorical        : LabelEncoder ou OneHotEncoder selon cardinalite
    scale_features            : StandardScaler ou MinMaxScaler
    detect_and_treat_outliers : IQR ou Z-score, cap/remove/flag
    create_features           : Feature engineering (age_from_date, ratio, difference)
    get_gemini_suggestions    : Suggestions IA pour transformations
    build_dimensional_model   : Star Schema depuis table plate
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import (
    LabelEncoder,
    MinMaxScaler,
    OneHotEncoder,
    StandardScaler,
)

logger = logging.getLogger(__name__)

# Seuils de cardinalite pour l'encodage automatique
_ONEHOT_THRESHOLD: int = 10  # cardinalite max pour LabelEncoder (sinon OneHot)
_MAX_ENCODE_CARD: int = 50  # au-dela : colonne ignoree (texte libre)


def _sans_accent(s: str) -> str:
    """Supprime les accents d'une chaine."""
    return "".join(
        c for c in unicodedata.normalize("NFD", str(s))
        if unicodedata.category(c) != "Mn"
    )


# ── Encodage categorial ───────────────────────────────────────────────────────

def encode_categorical(
    df: pd.DataFrame,
    columns: list[str],
    method: str = "auto",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Encode les variables categorielles.

    Methodes :
        'label'  : LabelEncoder (ordinale)
        'onehot' : OneHotEncoder drop='first' (nominale)
        'auto'   : label si cardinalite <= _ONEHOT_THRESHOLD,
                   sinon onehot. Ignorer si cardinalite > _MAX_ENCODE_CARD (texte libre).

    Args:
        df      : DataFrame a encoder.
        columns : Liste des colonnes categorielles a encoder.
        method  : 'label', 'onehot', ou 'auto'.

    Returns:
        Tuple (df_encoded, encoders_dict) ou encoders_dict = {colonne: encodeur}.

    Raises:
        ValueError: Si method invalide ou colonnes absentes du DataFrame.
    """
    valid_methods = {"label", "onehot", "auto"}
    if method not in valid_methods:
        raise ValueError(
            f"Methode invalide '{method}'. Choisir parmi : {valid_methods}"
        )

    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes absentes du DataFrame : {missing}")

    df_out = df.copy()
    encoders: dict[str, Any] = {}

    for col in columns:
        cardinality = int(df_out[col].nunique())

        # Ignorer les colonnes a trop haute cardinalite (texte libre)
        if method == "auto" and cardinality > _MAX_ENCODE_CARD:
            logger.info(
                "Colonne '%s' ignoree (cardinalite=%d > %d — texte libre)",
                col,
                cardinality,
                _MAX_ENCODE_CARD,
            )
            continue

        use_onehot = (
            method == "onehot"
            or (method == "auto" and cardinality > _ONEHOT_THRESHOLD)
        )

        if use_onehot:
            enc = OneHotEncoder(
                drop="first", sparse_output=False, handle_unknown="ignore"
            )
            values = df_out[[col]].astype(str)
            encoded = enc.fit_transform(values)
            feature_names = [
                f"{col}_{c.replace(f'{col}_', '')}"
                for c in enc.get_feature_names_out([col])
            ]
            encoded_df = pd.DataFrame(
                encoded, columns=feature_names, index=df_out.index
            )
            df_out = pd.concat([df_out.drop(columns=[col]), encoded_df], axis=1)
            encoders[col] = enc
            logger.info(
                "OneHotEncoding '%s' (cardinalite=%d) → %d colonnes",
                col,
                cardinality,
                len(feature_names),
            )
        else:
            enc = LabelEncoder()
            df_out[col] = enc.fit_transform(df_out[col].astype(str))
            encoders[col] = enc
            logger.info("LabelEncoding '%s' (cardinalite=%d)", col, cardinality)

    return df_out, encoders


# ── Scaling ───────────────────────────────────────────────────────────────────

def scale_features(
    df: pd.DataFrame,
    columns: list[str],
    method: str = "standard",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Normalise/standardise les colonnes numeriques mesures.

    Methodes :
        'standard' : StandardScaler (moyenne=0, ecart-type=1)
        'minmax'   : MinMaxScaler ([0, 1])

    Args:
        df      : DataFrame a normaliser.
        columns : Liste des colonnes numeriques a normaliser.
        method  : 'standard' ou 'minmax'.

    Returns:
        Tuple (df_scaled, scalers_dict) ou scalers_dict = {colonne: scaler}.

    Raises:
        ValueError: Si method invalide ou colonnes absentes du DataFrame.
    """
    valid_methods = {"standard", "minmax"}
    if method not in valid_methods:
        raise ValueError(
            f"Methode invalide '{method}'. Choisir parmi : {valid_methods}"
        )

    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes absentes du DataFrame : {missing}")

    df_out = df.copy()
    scalers: dict[str, Any] = {}

    for col in columns:
        scaler = StandardScaler() if method == "standard" else MinMaxScaler()
        values = df_out[[col]].values.astype(float)
        df_out[col] = scaler.fit_transform(values).ravel()
        scalers[col] = scaler
        logger.info("Scaling '%s' avec %s", col, scaler.__class__.__name__)

    return df_out, scalers


# ── Outliers ──────────────────────────────────────────────────────────────────

def detect_and_treat_outliers(
    df: pd.DataFrame,
    columns: list[str],
    method: str = "iqr",
    action: str = "cap",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Detecte et traite les valeurs aberrantes (outliers).

    Methodes de detection :
        'iqr'    : Q1 - 1.5*IQR et Q3 + 1.5*IQR
        'zscore' : |zscore| > 3

    Actions :
        'cap'    : Remplacer par la borne detectee
        'remove' : Supprimer les lignes contenant des outliers
        'flag'   : Ajouter colonne booleenne {colonne}_is_outlier

    Args:
        df      : DataFrame a analyser.
        columns : Liste des colonnes numeriques.
        method  : 'iqr' ou 'zscore'.
        action  : 'cap', 'remove', ou 'flag'.

    Returns:
        Tuple (df_treated, outliers_report) ou outliers_report documente
        pour chaque colonne les bornes detectees et nb outliers.

    Raises:
        ValueError: Si method ou action invalide.
    """
    valid_methods = {"iqr", "zscore"}
    valid_actions = {"cap", "remove", "flag"}
    if method not in valid_methods:
        raise ValueError(
            f"Methode invalide '{method}'. Choisir parmi : {valid_methods}"
        )
    if action not in valid_actions:
        raise ValueError(
            f"Action invalide '{action}'. Choisir parmi : {valid_actions}"
        )

    df_out = df.copy()
    report: dict[str, Any] = {}

    for col in columns:
        if col not in df_out.columns:
            continue

        series = df_out[col].dropna()
        n_total = len(series)
        if n_total == 0:
            continue

        # Calcul des bornes
        if method == "iqr":
            q1, q3 = series.quantile(0.25), series.quantile(0.75)
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        else:  # zscore
            mean, std = series.mean(), series.std()
            lower, upper = mean - 3 * std, mean + 3 * std

        # Detection des outliers
        mask = (df_out[col] < lower) | (df_out[col] > upper)
        n_outliers = int(mask.sum())

        # Traitement
        if action == "cap":
            df_out[col] = df_out[col].clip(lower=lower, upper=upper)
        elif action == "remove":
            df_out = df_out[~mask]
        else:  # flag
            df_out[f"{col}_is_outlier"] = mask

        report[col] = {
            "method": method,
            "action": action,
            "lower_bound": round(float(lower), 4),
            "upper_bound": round(float(upper), 4),
            "n_outliers": n_outliers,
            "percent_outliers": (
                round(n_outliers / n_total * 100, 2) if n_total > 0 else 0.0
            ),
        }
        logger.info(
            "Outliers '%s' : %d (%.1f%%) — action=%s",
            col,
            n_outliers,
            report[col]["percent_outliers"],
            action,
        )

    return df_out, report


# ── Feature Engineering ───────────────────────────────────────────────────────

def create_features(
    df: pd.DataFrame,
    operations: list[dict[str, Any]] | None = None,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """
    Cree des features derivees (age_from_date, ratio, difference).

    Operations supportees :
        - type='age_from_date'  : age en annees depuis date
        - type='ratio'          : colonne1 / colonne2 (gerer division par zero)
        - type='difference'     : colonne1 - colonne2

    Args:
        df        : DataFrame contenant les colonnes sources.
        operations: Liste de dict {type, source_columns, new_column_name}.
                    Si None : retourner df inchange et log vide.

    Returns:
        Tuple (df_enriched, features_log) ou features_log = {type, source,
        new_column, status, reason_if_error}.
    """
    df_out = df.copy()
    log: list[dict[str, Any]] = []

    if operations is None:
        return df_out, log

    for op in operations:
        op_type = op.get("type", "")
        src_cols = op.get("source_columns", [])
        new_col = op.get("new_column_name", f"feature_{len(log)}")

        try:
            if op_type == "age_from_date":
                col = src_cols[0]
                dates = pd.to_datetime(df_out[col], errors="coerce")
                df_out[new_col] = (
                    (pd.Timestamp.now() - dates).dt.days // 365
                ).astype("Int64")
                log.append({
                    "type": op_type,
                    "source": col,
                    "new_column": new_col,
                    "status": "ok",
                })
            elif op_type == "ratio":
                c1, c2 = src_cols[0], src_cols[1]
                denom = df_out[c2].replace(0, np.nan)
                df_out[new_col] = (df_out[c1] / denom).replace(
                    [np.inf, -np.inf], np.nan
                )
                log.append({
                    "type": op_type,
                    "source": f"{c1}/{c2}",
                    "new_column": new_col,
                    "status": "ok",
                })
            elif op_type == "difference":
                c1, c2 = src_cols[0], src_cols[1]
                df_out[new_col] = df_out[c1] - df_out[c2]
                log.append({
                    "type": op_type,
                    "source": f"{c1}-{c2}",
                    "new_column": new_col,
                    "status": "ok",
                })
            else:
                log.append({
                    "type": op_type,
                    "status": "skipped",
                    "reason": "type inconnu",
                })
        except Exception as exc:
            log.append({
                "type": op_type,
                "status": "error",
                "reason": str(exc),
            })
            logger.error("Erreur feature '%s' : %s", new_col, exc)

    return df_out, log


# ── Suggestions Gemini ────────────────────────────────────────────────────────

def get_gemini_suggestions(
    df_schema: dict[str, Any],
    applied_transformations: list[dict[str, Any]],
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """
    Demande des suggestions de features au modele Gemini 2.5 Flash.

    Args:
        df_schema              : Resume du schema du DataFrame
                                (sortie de build_schema_summary).
        applied_transformations: Liste des transformations deja appliquees.
        api_key                : Cle API Gemini (optionnelle, lue depuis .env).

    Returns:
        Liste de dict {nom, colonne, action, justification}.
        Liste vide si echec API ou parsing JSON impossible.
    """
    if not api_key:
        import os

        api_key = os.getenv("GEMINI_API_KEY", "")

    if not api_key:
        logger.warning(
            "GEMINI_API_KEY non configure — pas de suggestions Gemini"
        )
        return []

    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        prompt = f"""
Tu es un specialiste en feature engineering. Analyse le schema du dataset ci-dessous
et propose 3 a 5 features derivees utiles pour l'apprentissage automatique.

Schema du dataset :
{json.dumps(df_schema, indent=2, ensure_ascii=False)}

Transformations deja appliquees :
{json.dumps(applied_transformations, indent=2, ensure_ascii=False)}

Reponds UNIQUEMENT avec un JSON valide (liste de dict) sans texte supplementaire.
Format : [
  {{"nom": "feature_name", "colonne": "source_column", "action": "age_from_date|ratio|difference", "justification": "..."}},
  ...
]
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai.types.GenerateContentConfig(temperature=0.2, max_output_tokens=1000),
        )

        text = response.text.strip()
        # Extraire JSON si le modele a ajoute du texte
        json_start = text.find("[")
        json_end = text.rfind("]") + 1
        if json_start >= 0 and json_end > json_start:
            json_str = text[json_start:json_end]
            suggestions = json.loads(json_str)
            logger.info("Suggestions Gemini recues : %d propositions", len(suggestions))
            return suggestions
        else:
            logger.warning("Reponse Gemini non parsable : %s", text[:200])
            return []

    except ImportError:
        logger.warning("google-genai non installe — pas de suggestions Gemini")
        return []
    except json.JSONDecodeError as exc:
        logger.error("Erreur parsing JSON Gemini : %s", exc)
        return []
    except Exception as exc:
        logger.error("Erreur appel Gemini : %s", exc)
        return []


# ── Star Schema ───────────────────────────────────────────────────────────────

def build_dimensional_model(
    df: pd.DataFrame,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """
    Construit un Star Schema depuis une table plate.

    Detecte :
    - Colonnes numeriques agregables (mesures) -> table de faits
    - Colonnes descriptives a faible cardinalite -> tables de dimensions

    Construit :
    - Star schema : dict {fact: df_fact, dim_{nom}: df_dim, ...}
    - Cles primaires id_{dimension} auto-incrementees
    - Cles etrangeres dans la table de faits

    Args:
        df: DataFrame plat a decomposer.

    Returns:
        Tuple (schema_dict, rapport_structure) ou schema_dict contient
        toutes les tables et rapport_structure documente la decomposition.
    """
    from .cleaner import is_protected_column

    # Detection des mesures et dimensions
    measure_cols = [
        c for c in df.select_dtypes(include=[np.number]).columns
        if df[c].nunique() > 1 and df[c].std() > 0
    ]

    dim_candidates = [
        c for c in df.columns
        if c not in measure_cols
        and (df[c].dtype == object or pd.api.types.is_string_dtype(df[c]))
        and 2 <= df[c].nunique() <= 50
        and not is_protected_column(c, df[c])
    ]

    schema: dict[str, pd.DataFrame] = {}
    fk_map: dict[str, str] = {}
    rapport: dict[str, Any] = {
        "measure_columns": measure_cols,
        "dimension_tables": {},
    }

    df_fact = df.copy()

    # Construction des dimensions
    for dim_col in dim_candidates:
        dim_name = f"dim_{_sans_accent(dim_col).lower().replace(' ', '_')}"
        pk_name = f"id_{_sans_accent(dim_col).lower().replace(' ', '_')}"

        unique_vals = df[dim_col].dropna().unique()
        df_dim = pd.DataFrame({
            pk_name: range(1, len(unique_vals) + 1),
            dim_col: unique_vals,
        })

        schema[dim_name] = df_dim

        # Mapping valeur -> PK
        val_to_pk = dict(zip(unique_vals, range(1, len(unique_vals) + 1)))
        df_fact[pk_name] = df_fact[dim_col].map(val_to_pk)
        df_fact = df_fact.drop(columns=[dim_col])
        fk_map[dim_col] = pk_name

        rapport["dimension_tables"][dim_name] = {
            "original_column": dim_col,
            "pk_column": pk_name,
            "n_unique_values": len(unique_vals),
        }
        logger.info(
            "Dimension creee : '%s' (%d valeurs)", dim_name, len(unique_vals)
        )

    schema["fact"] = df_fact
    rapport["fact_columns"] = df_fact.columns.tolist()
    rapport["fk_map"] = fk_map

    return schema, rapport