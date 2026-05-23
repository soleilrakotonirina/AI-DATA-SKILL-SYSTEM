"""
backend/skills/visualization_skill/core/charts.py
Generation des graphiques Plotly style BI / Power BI.

Chaque fonction retourne un go.Figure pret a etre exporte ou serialise.
Relations X/Y uniquement coherentes et analytiques.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

logger = logging.getLogger(__name__)

# ─── Palette BI style Power BI / Tableau ─────────────────────────────────────

_COLORS_BI = [
    "#0078D4",  # Azure Blue (primaire)
    "#107C10",  # Vert Teams
    "#A80000",  # Rouge SharePoint
    "#FFB900",  # Or
    "#8764B8",  # Violet
    "#038387",  # Teal
    "#C43501",  # Orange-Rouge
    "#004E8C",  # Bleu fonce
    "#498205",  # Vert fonce
    "#881798",  # Violet fonce
]

_COLOR_PRIMARY  = "#0078D4"
_COLOR_BG       = "#FAFAFA"
_COLOR_GRID     = "#E8E8E8"
_COLOR_TEXT     = "#323130"
_COLOR_SUBTEXT  = "#605E5C"

_LAYOUT_BASE = dict(
    template="plotly_white",
    paper_bgcolor="white",
    plot_bgcolor="white",
    font=dict(family="Segoe UI, Inter, sans-serif", size=12, color=_COLOR_TEXT),
    margin=dict(l=50, r=30, t=55, b=50),
    showlegend=True,
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=-0.25,
        xanchor="center",
        x=0.5,
        font=dict(size=11),
    ),
)

# Couleurs par statut (si present dans le dataset)
_STATUT_COLORS = {
    "Validé":    "#107C10",
    "valide":    "#107C10",
    "En cours":  "#0078D4",
    "en cours":  "#0078D4",
    "Inscrit":   "#FFB900",
    "inscrit":   "#FFB900",
    "Abandon":   "#A80000",
    "abandon":   "#A80000",
    "Echec":     "#C43501",
    "echec":     "#C43501",
}

# Couleurs par sexe
_SEXE_COLORS = {
    "M": "#0078D4",
    "F": "#C44E52",
    "m": "#0078D4",
    "f": "#C44E52",
}


def _layout(**kwargs) -> dict:
    """Retourne le layout de base fusionne avec les kwargs."""
    base = dict(**_LAYOUT_BASE)
    base.update(kwargs)
    return base


def _color_sequence_for(col: str, values: List[str]) -> List[str]:
    """Retourne une palette adaptee selon le nom de la colonne."""
    col_l = col.lower()
    if "statut" in col_l or "status" in col_l:
        return [_STATUT_COLORS.get(v, _COLORS_BI[4]) for v in values]
    if "sexe" in col_l or "genre" in col_l or "gender" in col_l:
        return [_SEXE_COLORS.get(v, _COLORS_BI[0]) for v in values]
    return _COLORS_BI[:len(values)]


# ─── generate_bar_count ───────────────────────────────────────────────────────

def generate_bar_count(
    df: pd.DataFrame,
    x_col: str,
    titre: str,
    orientation: str = "v",
    ordre_x: Optional[List[str]] = None,
    top_n: int = 15,
) -> go.Figure:
    """
    Bar chart du nombre d'enregistrements par valeur d'une dimension.

    Args:
        df:          DataFrame source.
        x_col:       Colonne dimension (X).
        titre:       Titre du graphique.
        orientation: 'v' (vertical) ou 'h' (horizontal).
        ordre_x:     Ordre des categories sur l'axe X.
        top_n:       Nombre maximum de valeurs a afficher.

    Returns:
        Figure Plotly.

    Raises:
        ValueError: Si x_col absent du DataFrame.
    """
    if x_col not in df.columns:
        raise ValueError(f"Colonne '{x_col}' absente")

    vc = df[x_col].value_counts().head(top_n)

    # Appliquer ordre logique si fourni
    if ordre_x:
        index_ordered = [v for v in ordre_x if v in vc.index]
        missing = [v for v in vc.index if v not in ordre_x]
        ordered_index = index_ordered + missing
        vc = vc.reindex(ordered_index).dropna()

    labels = vc.index.tolist()
    values = vc.values.tolist()
    colors = _color_sequence_for(x_col, labels)
    if len(colors) < len(labels):
        colors = (_COLORS_BI * (len(labels) // len(_COLORS_BI) + 1))[:len(labels)]

    if orientation == "h":
        fig = go.Figure(go.Bar(
            y=labels[::-1],
            x=values[::-1],
            orientation="h",
            marker=dict(color=colors[::-1]),
            text=[str(v) for v in values[::-1]],
            textposition="outside",
            hovertemplate="%{y}<br>Count : <b>%{x}</b><extra></extra>",
        ))
        fig.update_layout(
            **_layout(
                title=dict(text=titre, font=dict(size=14, color=_COLOR_TEXT), x=0),
                xaxis=dict(title="Effectif", showgrid=True, gridcolor=_COLOR_GRID),
                yaxis=dict(title="", showgrid=False),
                showlegend=False,
            )
        )
    else:
        fig = go.Figure(go.Bar(
            x=labels,
            y=values,
            marker=dict(color=colors),
            text=[str(v) for v in values],
            textposition="outside",
            hovertemplate="%{x}<br>Count : <b>%{y}</b><extra></extra>",
        ))
        fig.update_layout(
            **_layout(
                title=dict(text=titre, font=dict(size=14, color=_COLOR_TEXT), x=0),
                xaxis=dict(
                    title=x_col.replace("_", " ").title(),
                    showgrid=False,
                    tickangle=-20 if len(labels) > 6 else 0,
                    categoryorder="array",
                    categoryarray=labels,
                ),
                yaxis=dict(title="Effectif", showgrid=True, gridcolor=_COLOR_GRID),
                showlegend=False,
            )
        )

    return fig


# ─── generate_bar_mesure ─────────────────────────────────────────────────────

def generate_bar_mesure(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    agg: str,
    titre: str,
    orientation: str = "v",
    ordre_x: Optional[List[str]] = None,
    top_n: int = 15,
) -> go.Figure:
    """
    Bar chart d'une mesure aggregee par dimension.

    Args:
        df:          DataFrame source.
        x_col:       Colonne dimension (X).
        y_col:       Colonne mesure (Y).
        agg:         Agregation : 'mean', 'sum', 'median'.
        titre:       Titre du graphique.
        orientation: 'v' ou 'h'.
        ordre_x:     Ordre des categories.
        top_n:       Nombre max de valeurs.

    Returns:
        Figure Plotly.
    """
    for col in [x_col, y_col]:
        if col not in df.columns:
            raise ValueError(f"Colonne '{col}' absente")

    agg_func = {"mean": "mean", "sum": "sum", "median": "median"}.get(agg, "mean")
    grouped = df.groupby(x_col)[y_col].agg(agg_func).head(top_n)

    if ordre_x:
        idx_ordered = [v for v in ordre_x if v in grouped.index]
        missing = [v for v in grouped.index if v not in ordre_x]
        grouped = grouped.reindex(idx_ordered + missing).dropna()

    labels = grouped.index.tolist()
    values = grouped.values.tolist()
    colors = _color_sequence_for(x_col, labels)
    if len(colors) < len(labels):
        colors = (_COLORS_BI * (len(labels) // len(_COLORS_BI) + 1))[:len(labels)]

    y_label = f"{y_col.replace('_', ' ').title()} ({agg})"
    text_vals = [f"{v:,.1f}" for v in values]

    if orientation == "h":
        fig = go.Figure(go.Bar(
            y=labels[::-1],
            x=values[::-1],
            orientation="h",
            marker=dict(color=colors[::-1]),
            text=text_vals[::-1],
            textposition="outside",
            hovertemplate="%{y}<br>" + y_label + " : <b>%{x:,.2f}</b><extra></extra>",
        ))
        fig.update_layout(**_layout(
            title=dict(text=titre, font=dict(size=14, color=_COLOR_TEXT), x=0),
            xaxis=dict(title=y_label, showgrid=True, gridcolor=_COLOR_GRID),
            yaxis=dict(title="", showgrid=False),
            showlegend=False,
        ))
    else:
        fig = go.Figure(go.Bar(
            x=labels,
            y=values,
            marker=dict(color=colors),
            text=text_vals,
            textposition="outside",
            hovertemplate="%{x}<br>" + y_label + " : <b>%{y:,.2f}</b><extra></extra>",
        ))
        fig.update_layout(**_layout(
            title=dict(text=titre, font=dict(size=14, color=_COLOR_TEXT), x=0),
            xaxis=dict(
                title=x_col.replace("_", " ").title(),
                showgrid=False,
                tickangle=-20 if len(labels) > 6 else 0,
                categoryorder="array",
                categoryarray=labels,
            ),
            yaxis=dict(title=y_label, showgrid=True, gridcolor=_COLOR_GRID),
            showlegend=False,
        ))

    return fig


# ─── generate_donut ──────────────────────────────────────────────────────────

def generate_donut(
    df: pd.DataFrame,
    col: str,
    titre: str,
    top_n: int = 8,
) -> go.Figure:
    """
    Donut chart de la distribution d'une dimension.

    Args:
        df:    DataFrame source.
        col:   Colonne dimension (2-8 valeurs recommandees).
        titre: Titre du graphique.
        top_n: Nombre max de valeurs.

    Returns:
        Figure Plotly.
    """
    if col not in df.columns:
        raise ValueError(f"Colonne '{col}' absente")

    vc = df[col].value_counts().head(top_n)
    labels = vc.index.tolist()
    values = vc.values.tolist()
    total = sum(values)
    colors = _color_sequence_for(col, labels)
    if len(colors) < len(labels):
        colors = (_COLORS_BI * (len(labels) // len(_COLORS_BI) + 1))[:len(labels)]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.45,
        marker=dict(colors=colors, line=dict(color="white", width=2)),
        textinfo="label+percent",
        hovertemplate="<b>%{label}</b><br>Count : %{value}<br>Part : %{percent}<extra></extra>",
        sort=False,
    ))

    fig.add_annotation(
        text=f"<b>{total}</b><br>Total",
        x=0.5, y=0.5,
        font=dict(size=14, color=_COLOR_TEXT),
        showarrow=False,
    )

    fig.update_layout(
        title=dict(text=titre, font=dict(size=14, color=_COLOR_TEXT), x=0),
        paper_bgcolor="white",
        font=dict(family="Segoe UI, Inter, sans-serif", size=12),
        margin=dict(l=30, r=30, t=55, b=30),
        legend=dict(orientation="v", x=1.02, y=0.5),
        showlegend=True,
    )

    return fig


# ─── generate_stacked_bar ────────────────────────────────────────────────────

def generate_stacked_bar(
    df: pd.DataFrame,
    x_col: str,
    color_col: str,
    titre: str,
    ordre_x: Optional[List[str]] = None,
    top_n: int = 15,
    normalise: bool = False,
) -> go.Figure:
    """
    Stacked bar chart : X = dimension, couleur = autre dimension.

    Args:
        df:        DataFrame source.
        x_col:     Colonne dimension axe X.
        color_col: Colonne dimension couleur (stackee).
        titre:     Titre du graphique.
        ordre_x:   Ordre des categories X.
        top_n:     Nombre max de valeurs X.
        normalise: Si True, pourcentage (100% stacked).

    Returns:
        Figure Plotly.
    """
    for col in [x_col, color_col]:
        if col not in df.columns:
            raise ValueError(f"Colonne '{col}' absente")

    crosstab = pd.crosstab(df[x_col], df[color_col])

    if ordre_x:
        idx_ordered = [v for v in ordre_x if v in crosstab.index]
        missing = [v for v in crosstab.index if v not in ordre_x]
        crosstab = crosstab.reindex(idx_ordered + missing).dropna(how="all")

    crosstab = crosstab.head(top_n)

    if normalise:
        row_sums = crosstab.sum(axis=1)
        crosstab = crosstab.div(row_sums, axis=0) * 100

    color_vals = crosstab.columns.tolist()
    colors = _color_sequence_for(color_col, color_vals)
    if len(colors) < len(color_vals):
        colors = (_COLORS_BI * (len(color_vals) // len(_COLORS_BI) + 1))[:len(color_vals)]

    fig = go.Figure()
    for i, cat in enumerate(color_vals):
        y_vals = crosstab[cat].tolist()
        text_vals = [f"{v:.0f}{'%' if normalise else ''}" for v in y_vals]
        fig.add_trace(go.Bar(
            x=crosstab.index.tolist(),
            y=y_vals,
            name=str(cat),
            marker_color=colors[i],
            text=text_vals,
            textposition="inside",
            textfont=dict(size=10, color="white"),
            hovertemplate=(
                f"<b>%{{x}}</b><br>{color_col} : {cat}<br>"
                f"{'Pct' if normalise else 'Count'} : %{{y:.1f}}"
                f"{'%' if normalise else ''}<extra></extra>"
            ),
        ))

    y_title = "Pourcentage (%)" if normalise else "Effectif"
    fig.update_layout(
        barmode="stack",
        title=dict(text=titre, font=dict(size=14, color=_COLOR_TEXT), x=0),
        xaxis=dict(
            title=x_col.replace("_", " ").title(),
            showgrid=False,
            tickangle=-20 if len(crosstab) > 6 else 0,
        ),
        yaxis=dict(
            title=y_title,
            showgrid=True,
            gridcolor=_COLOR_GRID,
        ),
        **_layout(),
    )

    return fig


# ─── generate_boxplot_mesure ─────────────────────────────────────────────────

def generate_boxplot_mesure(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    titre: str,
    ordre_x: Optional[List[str]] = None,
) -> go.Figure:
    """
    Boxplot d'une mesure numerique par categorie.

    Args:
        df:      DataFrame source.
        x_col:   Colonne dimension (X).
        y_col:   Colonne mesure numerique (Y).
        titre:   Titre du graphique.
        ordre_x: Ordre des categories.

    Returns:
        Figure Plotly.
    """
    for col in [x_col, y_col]:
        if col not in df.columns:
            raise ValueError(f"Colonne '{col}' absente")

    categories = df[x_col].dropna().unique().tolist()
    if ordre_x:
        categories = [v for v in ordre_x if v in categories] + \
                     [v for v in categories if v not in ordre_x]

    colors = _color_sequence_for(x_col, categories)
    if len(colors) < len(categories):
        colors = (_COLORS_BI * (len(categories) // len(_COLORS_BI) + 1))[:len(categories)]

    fig = go.Figure()
    for i, cat in enumerate(categories):
        mask = df[x_col] == cat
        fig.add_trace(go.Box(
            y=df.loc[mask, y_col].dropna(),
            name=str(cat),
            boxpoints="outliers",
            marker=dict(color=colors[i], size=4),
            line=dict(color=colors[i]),
            hovertemplate=(
                f"<b>{cat}</b><br>"
                f"{y_col.replace('_', ' ').title()} : %{{y:.2f}}<extra></extra>"
            ),
        ))

    fig.update_layout(
        title=dict(text=titre, font=dict(size=14, color=_COLOR_TEXT), x=0),
        xaxis=dict(
            title=x_col.replace("_", " ").title(),
            showgrid=False,
            tickangle=-20 if len(categories) > 6 else 0,
        ),
        yaxis=dict(
            title=y_col.replace("_", " ").title(),
            showgrid=True,
            gridcolor=_COLOR_GRID,
        ),
        **_layout(showlegend=False),
    )

    return fig


# ─── generate_line_count ─────────────────────────────────────────────────────

def generate_line_count(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    agg: str,
    titre: str,
) -> go.Figure:
    """
    Line chart de l'evolution d'une mesure (ou du count) selon une dimension ordonnee.

    Args:
        df:    DataFrame source.
        x_col: Colonne axe X (temporelle ou ordonnee).
        y_col: Colonne axe Y ou "count".
        agg:   Agregation : 'count', 'mean', 'sum'.
        titre: Titre du graphique.

    Returns:
        Figure Plotly.
    """
    if x_col not in df.columns:
        raise ValueError(f"Colonne '{x_col}' absente")

    if y_col == "count" or agg == "count":
        grouped = df.groupby(x_col).size().reset_index(name="y")
        y_label = "Effectif"
    else:
        if y_col not in df.columns:
            raise ValueError(f"Colonne '{y_col}' absente")
        agg_func = {"mean": "mean", "sum": "sum", "median": "median"}.get(agg, "mean")
        grouped = df.groupby(x_col)[y_col].agg(agg_func).reset_index()
        grouped.columns = [x_col, "y"]
        y_label = f"{y_col.replace('_', ' ').title()} ({agg})"

    grouped = grouped.sort_values(x_col)
    x_vals = grouped[x_col].astype(str).tolist()
    y_vals = grouped["y"].tolist()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x_vals,
        y=y_vals,
        mode="lines+markers+text",
        line=dict(color=_COLOR_PRIMARY, width=2.5),
        marker=dict(size=7, color=_COLOR_PRIMARY, symbol="circle"),
        text=[f"{v:,.0f}" for v in y_vals],
        textposition="top center",
        textfont=dict(size=10),
        fill="tozeroy",
        fillcolor=f"rgba(0, 120, 212, 0.08)",
        hovertemplate=f"%{{x}}<br>{y_label} : <b>%{{y:,.0f}}</b><extra></extra>",
    ))

    fig.update_layout(
        title=dict(text=titre, font=dict(size=14, color=_COLOR_TEXT), x=0),
        xaxis=dict(
            title=x_col.replace("_", " ").title(),
            showgrid=False,
            tickangle=-20 if len(x_vals) > 6 else 0,
        ),
        yaxis=dict(title=y_label, showgrid=True, gridcolor=_COLOR_GRID),
        **_layout(showlegend=False),
    )

    return fig


# ─── generate_heatmap_crosstab ───────────────────────────────────────────────

def generate_heatmap_crosstab(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    titre: str,
    ordre_x: Optional[List[str]] = None,
) -> go.Figure:
    """
    Heatmap de contingence entre deux dimensions.

    Args:
        df:      DataFrame source.
        x_col:   Dimension axe X.
        y_col:   Dimension axe Y.
        titre:   Titre du graphique.
        ordre_x: Ordre des categories X.

    Returns:
        Figure Plotly.
    """
    for col in [x_col, y_col]:
        if col not in df.columns:
            raise ValueError(f"Colonne '{col}' absente")

    crosstab = pd.crosstab(df[y_col], df[x_col])

    if ordre_x:
        cols_ordered = [v for v in ordre_x if v in crosstab.columns]
        missing = [v for v in crosstab.columns if v not in ordre_x]
        crosstab = crosstab[[*cols_ordered, *missing]]

    z = crosstab.values
    x_labels = crosstab.columns.tolist()
    y_labels = crosstab.index.tolist()

    annotations = []
    for i in range(len(y_labels)):
        for j in range(len(x_labels)):
            val = int(z[i, j])
            annotations.append(dict(
                x=j, y=i,
                text=str(val),
                xref="x", yref="y",
                showarrow=False,
                font=dict(size=11, color="black" if val < z.max() * 0.6 else "white"),
            ))

    fig = go.Figure(go.Heatmap(
        z=z,
        x=x_labels,
        y=y_labels,
        colorscale="Blues",
        colorbar=dict(title="Count"),
        hovertemplate=(
            f"{x_col}: %{{x}}<br>{y_col}: %{{y}}<br>Count: %{{z}}<extra></extra>"
        ),
    ))

    fig.update_layout(
        title=dict(text=titre, font=dict(size=14, color=_COLOR_TEXT), x=0),
        xaxis=dict(
            title=x_col.replace("_", " ").title(),
            tickangle=-20 if len(x_labels) > 6 else 0,
        ),
        yaxis=dict(title=y_col.replace("_", " ").title()),
        annotations=annotations,
        paper_bgcolor="white",
        font=dict(family="Segoe UI, Inter, sans-serif", size=12),
        margin=dict(l=80, r=30, t=55, b=80),
        showlegend=False,
    )

    return fig


# ─── generate_scatter_mesures ────────────────────────────────────────────────

def generate_scatter_mesures(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    color_col: Optional[str],
    titre: str,
) -> go.Figure:
    """
    Scatter plot entre deux mesures numeriques.

    Args:
        df:        DataFrame source.
        x_col:     Colonne numerique axe X.
        y_col:     Colonne numerique axe Y.
        color_col: Colonne categorielle pour la couleur (optionnel).
        titre:     Titre du graphique.

    Returns:
        Figure Plotly.
    """
    for col in [x_col, y_col]:
        if col not in df.columns:
            raise ValueError(f"Colonne '{col}' absente")

    kwargs: dict = dict(
        x=x_col,
        y=y_col,
        template="plotly_white",
        opacity=0.7,
        color_discrete_sequence=_COLORS_BI,
        hover_data={c: True for c in df.columns[:5]},
    )

    if color_col and color_col in df.columns:
        kwargs["color"] = color_col

    fig = px.scatter(df, **kwargs)

    fig.update_layout(
        title=dict(text=titre, font=dict(size=14, color=_COLOR_TEXT), x=0),
        xaxis=dict(
            title=x_col.replace("_", " ").title(),
            showgrid=True,
            gridcolor=_COLOR_GRID,
        ),
        yaxis=dict(
            title=y_col.replace("_", " ").title(),
            showgrid=True,
            gridcolor=_COLOR_GRID,
        ),
        **_layout(),
    )

    return fig


# ─── Fonctions de compatibilite (ancienne API) ────────────────────────────────

def generate_histogram(
    df: pd.DataFrame,
    column: str,
    nbins: int = 30,
    color: Optional[str] = None,
) -> go.Figure:
    """Histogramme de la distribution d'une colonne numerique."""
    if column not in df.columns:
        raise ValueError(f"Colonne '{column}' absente du DataFrame")
    if not pd.api.types.is_numeric_dtype(df[column]):
        raise ValueError(f"Colonne '{column}' n'est pas numerique")

    series = df[column].dropna()
    bar_color = color or _COLOR_PRIMARY

    fig = go.Figure(go.Histogram(
        x=series,
        nbinsx=nbins,
        name="Frequence",
        marker_color=bar_color,
        opacity=0.75,
        hovertemplate="Valeur : %{x}<br>Count : %{y}<extra></extra>",
    ))

    try:
        from scipy.stats import gaussian_kde
        kde = gaussian_kde(series)
        x_range = np.linspace(float(series.min()), float(series.max()), 200)
        y_kde = kde(x_range)
        bin_width = (float(series.max()) - float(series.min())) / nbins
        y_kde_scaled = y_kde * len(series) * bin_width
        fig.add_trace(go.Scatter(
            x=x_range, y=y_kde_scaled,
            mode="lines", name="KDE",
            line=dict(color=_COLORS_BI[2], width=2),
        ))
    except Exception:
        pass

    fig.update_layout(
        title=dict(text=f"Distribution de {column}", font=dict(size=14), x=0),
        xaxis_title=column,
        yaxis_title="Frequence",
        **_layout(showlegend=True),
    )
    return fig


def generate_boxplot(
    df: pd.DataFrame,
    columns: List[str],
    group_by: Optional[str] = None,
) -> go.Figure:
    """Boxplot pour une ou plusieurs colonnes numeriques."""
    valid_cols = [c for c in columns if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
    if not valid_cols:
        raise ValueError("Aucune colonne numerique valide")

    fig = go.Figure()
    for i, col in enumerate(valid_cols):
        fig.add_trace(go.Box(
            y=df[col].dropna(),
            name=col,
            boxpoints="outliers",
            marker_color=_COLORS_BI[i % len(_COLORS_BI)],
        ))

    fig.update_layout(
        title=dict(text=f"Boxplot — {', '.join(valid_cols[:3])}", font=dict(size=14), x=0),
        yaxis_title="Valeur",
        **_layout(showlegend=len(valid_cols) > 1),
    )
    return fig


def generate_bar_chart(
    df: pd.DataFrame,
    column: str,
    top_n: int = 10,
    orientation: str = "v",
) -> go.Figure:
    """Bar chart de compatibilite."""
    return generate_bar_count(df, column, f"Distribution de {column}", orientation, None, top_n)


def generate_line_chart(
    df: pd.DataFrame,
    x_column: str,
    y_columns: List[str],
) -> go.Figure:
    """Line chart de compatibilite."""
    if not y_columns or y_columns[0] not in df.columns:
        raise ValueError("Aucune colonne Y valide")
    return generate_line_count(df, x_column, y_columns[0], "mean", f"Evolution — {x_column}")


def generate_scatter_plot(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    color_column: Optional[str] = None,
    size_column: Optional[str] = None,
) -> go.Figure:
    """Scatter de compatibilite."""
    return generate_scatter_mesures(df, x_column, y_column, color_column, f"{x_column} vs {y_column}")


def generate_heatmap_correlation(corr_matrix: pd.DataFrame) -> go.Figure:
    """Heatmap de correlation Pearson."""
    if corr_matrix.empty:
        raise ValueError("Matrice de correlation vide")

    cols = corr_matrix.columns.tolist()
    n = len(cols)
    mask = np.triu(np.ones((n, n), dtype=bool), k=1)
    z = corr_matrix.values.copy().astype(float)
    z[mask] = np.nan

    annotations = []
    for i in range(n):
        for j in range(n):
            if not mask[i, j]:
                val = z[i, j]
                annotations.append(dict(
                    x=j, y=i, text=f"{val:.2f}",
                    xref="x", yref="y", showarrow=False,
                    font=dict(size=max(8, min(12, 100 // n)), color="black"),
                ))

    fig = go.Figure(go.Heatmap(
        z=z, x=cols, y=cols,
        colorscale="RdBu_r", zmid=0, zmin=-1, zmax=1,
        colorbar=dict(title="Correlation"),
        hovertemplate="X : %{x}<br>Y : %{y}<br>r : %{z:.4f}<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text="Matrice de Correlation (Pearson)", font=dict(size=14), x=0),
        xaxis=dict(tickangle=-45),
        annotations=annotations,
        paper_bgcolor="white",
        font=dict(family="Segoe UI, Inter, sans-serif", size=12),
        margin=dict(l=100, r=30, t=80, b=100),
        height=max(400, n * 50),
        showlegend=False,
    )
    return fig


def generate_pairplot(
    df: pd.DataFrame,
    columns: List[str],
    color_column: Optional[str] = None,
) -> go.Figure:
    """Scatter matrix."""
    valid_cols = [c for c in columns if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
    if len(valid_cols) < 2:
        raise ValueError("Au moins 2 colonnes numeriques necessaires")
    valid_cols = valid_cols[:6]

    kwargs: dict = dict(
        dimensions=valid_cols, template="plotly_white",
        color_discrete_sequence=_COLORS_BI, opacity=0.6,
    )
    if color_column and color_column in df.columns:
        kwargs["color"] = color_column

    fig = px.scatter_matrix(df, **kwargs)
    fig.update_traces(diagonal_visible=True, showupperhalf=False, marker=dict(size=3))
    fig.update_layout(
        title=dict(text=f"Pairplot — {len(valid_cols)} variables", font=dict(size=14), x=0),
        font=dict(family="Segoe UI, Inter, sans-serif", size=10),
        margin=dict(l=80, r=30, t=80, b=80),
        height=max(600, len(valid_cols) * 150),
    )
    return fig