"""
backend/skills/visualization_skill/scripts/helpers.py
Fonctions utilitaires internes du Visualization Skill.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go


def infer_chart_type(series: pd.Series) -> str:
    """
    Retourne le type de graphique recommande selon dtype et cardinalite.

    Regles :
    - Numerique : histogram
    - Categorielle cardinalite <= 30 : bar_chart
    - Categorielle cardinalite > 30  : bar_chart (top 10)
    - Datetime                       : line_chart
    - Autre                          : bar_chart

    Args:
        series: Serie pandas a analyser.

    Returns:
        Type de graphique recommande : "histogram", "bar_chart", "line_chart".
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return "line_chart"
    if pd.api.types.is_numeric_dtype(series):
        return "histogram"
    n_unique = series.nunique()
    if n_unique <= 30:
        return "bar_chart"
    return "bar_chart"


def truncate_title(title: str, max_len: int = 60) -> str:
    """
    Tronque un titre long en ajoutant '...'.

    Args:
        title:   Titre a tronquer.
        max_len: Longueur maximale (defaut 60).

    Returns:
        Titre tronque si necessaire.
    """
    if len(title) <= max_len:
        return title
    return title[: max_len - 3] + "..."


def sanitize_filename(name: str) -> str:
    """
    Remplace les caracteres speciaux par des underscores pour noms de fichiers.

    Args:
        name: Nom a nettoyer.

    Returns:
        Nom nettoyé compatible avec les systemes de fichiers.
    """
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    sanitized = re.sub(r"_+", "_", sanitized)
    return sanitized.strip("_")


def build_chart_stats_summary(
    figure: go.Figure,
    df: pd.DataFrame,
    columns: List[str],
) -> str:
    """
    Extrait les statistiques cles d'un graphique pour les prompts Gemini.

    Collecte mean, std, min, max et nb de valeurs uniques pour
    chaque colonne impliquee dans le graphique.

    Args:
        figure:  Figure Plotly (non utilise directement, reserve).
        df:      DataFrame source.
        columns: Colonnes impliquees dans le graphique.

    Returns:
        Resume textuel des statistiques pour le prompt Gemini.
    """
    parts: List[str] = []

    for col in columns:
        if col not in df.columns:
            continue
        series = df[col].dropna()

        if pd.api.types.is_numeric_dtype(series):
            parts.append(
                f"{col} : mean={series.mean():.4g}, "
                f"std={series.std():.4g}, "
                f"min={series.min():.4g}, "
                f"max={series.max():.4g}, "
                f"skew={series.skew():.4g}"
            )
        else:
            n_unique = series.nunique()
            top = series.value_counts().head(3)
            top_str = ", ".join(f"{v}({c})" for v, c in top.items())
            parts.append(
                f"{col} : {n_unique} valeurs uniques, top 3 = [{top_str}]"
            )

    return " | ".join(parts) if parts else "Statistiques non disponibles"


def get_plotly_color_palette() -> List[str]:
    """
    Retourne la palette de couleurs standard du projet.

    Palette colorblind-friendly.

    Returns:
        Liste de 5 couleurs hex.
    """
    return [
        "#4C72B0",  # Bleu
        "#DD8452",  # Orange
        "#55A868",  # Vert
        "#C44E52",  # Rouge
        "#8172B3",  # Violet
    ]