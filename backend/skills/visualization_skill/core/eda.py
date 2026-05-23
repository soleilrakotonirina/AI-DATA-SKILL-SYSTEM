"""
backend/skills/visualization_skill/core/eda.py
Statistiques EDA autonomes — sans dependance a kpi_engine.

Fonctions utilisees par logic.py :
    compute_descriptive_stats()   Statistiques par colonne
    compute_correlation_matrix()  Matrice de correlation Pearson
    analyze_target_variable()     Distribution variable cible
    detect_data_patterns()        Detection colonnes temporelles/geo/texte
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_descriptive_stats(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Statistiques descriptives pour chaque colonne.

    Args:
        df: DataFrame a analyser.

    Returns:
        {"numeric_stats": {col: {...}}, "categorical_stats": {col: {...}}}
    """
    n_rows = len(df)
    numeric_stats: Dict[str, Any] = {}
    categorical_stats: Dict[str, Any] = {}

    for col in df.columns:
        null_count = int(df[col].isna().sum())
        null_pct = round(null_count / n_rows * 100, 2) if n_rows > 0 else 0.0

        if pd.api.types.is_numeric_dtype(df[col]):
            series = df[col].dropna()
            if len(series) == 0:
                numeric_stats[col] = {
                    "mean": None, "std": None, "min": None,
                    "q25": None, "q50": None, "q75": None, "max": None,
                    "skewness": None, "kurtosis": None,
                    "null_count": null_count, "null_pct": null_pct,
                }
                continue
            numeric_stats[col] = {
                "mean":      round(float(series.mean()), 4),
                "std":       round(float(series.std()), 4),
                "min":       round(float(series.min()), 4),
                "q25":       round(float(series.quantile(0.25)), 4),
                "q50":       round(float(series.quantile(0.50)), 4),
                "q75":       round(float(series.quantile(0.75)), 4),
                "max":       round(float(series.max()), 4),
                "skewness":  round(float(series.skew()), 4),
                "kurtosis":  round(float(series.kurtosis()), 4),
                "null_count": null_count,
                "null_pct":   null_pct,
            }
        else:
            series = df[col].dropna().astype(str)
            n_unique = int(series.nunique())
            vc = series.value_counts().head(10)
            top_values = [
                {"value": str(val), "count": int(cnt),
                 "pct": round(cnt / len(series) * 100, 2) if len(series) > 0 else 0.0}
                for val, cnt in vc.items()
            ]
            categorical_stats[col] = {
                "n_unique":   n_unique,
                "null_count": null_count,
                "null_pct":   null_pct,
                "top_values": top_values,
            }

    return {"numeric_stats": numeric_stats, "categorical_stats": categorical_stats}


def compute_correlation_matrix(
    df: pd.DataFrame,
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """
    Matrice de correlation Pearson sur les colonnes numeriques.

    Args:
        df: DataFrame a analyser.

    Returns:
        (corr_matrix, high_corr_pairs) ou (DataFrame vide, []) si < 2 colonnes.
    """
    numeric_cols = df.select_dtypes(include="number").columns.tolist()

    if len(numeric_cols) < 2:
        logger.warning("[EDA] Moins de 2 colonnes numeriques — pas de correlation")
        return pd.DataFrame(), []

    corr_matrix = df[numeric_cols].corr(method="pearson")
    high_corr_pairs: List[Dict[str, Any]] = []
    seen: set = set()

    for i, col_a in enumerate(corr_matrix.columns):
        for j, col_b in enumerate(corr_matrix.columns):
            if i >= j:
                continue
            corr_val = corr_matrix.loc[col_a, col_b]
            if pd.isna(corr_val):
                continue
            pair_key = tuple(sorted([col_a, col_b]))
            if pair_key in seen:
                continue
            seen.add(pair_key)
            if abs(corr_val) > 0.8:
                high_corr_pairs.append({
                    "col_a":       col_a,
                    "col_b":       col_b,
                    "correlation": round(float(corr_val), 4),
                })

    high_corr_pairs.sort(key=lambda x: abs(x["correlation"]), reverse=True)
    logger.info(
        "[EDA] Correlation : %d colonnes, %d paires |r| > 0.8",
        len(numeric_cols), len(high_corr_pairs),
    )
    return corr_matrix, high_corr_pairs


def analyze_target_variable(
    df: pd.DataFrame,
    target_column: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Analyse la distribution de la variable cible.

    Args:
        df:            DataFrame source.
        target_column: Nom de la colonne cible. None → retourne None.

    Returns:
        None ou dict {column, n_classes, distribution, imbalance_ratio, is_imbalanced}.
    """
    if target_column is None or target_column not in df.columns:
        return None

    series = df[target_column].dropna()
    if len(series) == 0:
        return None

    vc = series.value_counts()
    total = len(series)
    distribution = [
        {"class": str(cls), "count": int(cnt),
         "pct": round(cnt / total * 100, 2)}
        for cls, cnt in vc.items()
    ]

    imbalance_ratio = round(float(vc.iloc[0] / vc.iloc[-1]), 4) if len(vc) >= 2 else 1.0
    return {
        "column":          target_column,
        "n_classes":       int(len(vc)),
        "distribution":    distribution,
        "imbalance_ratio": imbalance_ratio,
        "is_imbalanced":   imbalance_ratio > 3.0,
    }


def detect_data_patterns(df: pd.DataFrame) -> Dict[str, List[str]]:
    """
    Detecte colonnes temporelles, geographiques et texte libre.

    Args:
        df: DataFrame a analyser.

    Returns:
        {"time_series_columns": [...], "geo_columns": [...], "text_columns": [...]}
    """
    _date_kw = {
        "date", "time", "year", "month", "day", "week",
        "annee", "mois", "jour", "semaine", "datetime",
        "timestamp", "periode", "created_at", "updated_at",
    }
    _geo_kw = {
        "country", "pays", "region", "ville", "city", "province",
        "state", "district", "lat", "lon", "latitude", "longitude",
        "geo", "location", "localisation", "address",
    }
    time_cols: List[str] = []
    geo_cols: List[str] = []
    text_cols: List[str] = []

    for col in df.columns:
        cl = col.lower()
        if pd.api.types.is_datetime64_any_dtype(df[col]) or any(kw in cl for kw in _date_kw):
            time_cols.append(col)
        elif any(kw in cl for kw in _geo_kw):
            geo_cols.append(col)
        elif df[col].dtype == object or pd.api.types.is_string_dtype(df[col]):
            sample = df[col].dropna().astype(str).head(100)
            if len(sample) > 0 and float(sample.str.len().mean()) > 50:
                text_cols.append(col)

    return {
        "time_series_columns": time_cols,
        "geo_columns":         geo_cols,
        "text_columns":        text_cols,
    }
