"""
backend/skills/visualization_skill/core/exporter.py
Export des graphiques Plotly et generation du rapport EDA MDX.

Format du rapport : identique au rapport de reference avec
KPIs principaux, score global, distributions, graphiques commentes.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

logger = logging.getLogger(__name__)


# ─── Export HTML ──────────────────────────────────────────────────────────────

def export_chart_html(figure: go.Figure, output_path: str) -> str:
    """
    Sauvegarde un graphique Plotly en HTML autonome.

    Args:
        figure:      Figure Plotly.
        output_path: Chemin de sortie (.html).

    Returns:
        Chemin absolu du fichier cree.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(str(path), include_plotlyjs="cdn", full_html=True)
    logger.debug("[Exporter] HTML : %s", path.name)
    return str(path)


# ─── Export PNG ───────────────────────────────────────────────────────────────

def export_chart_png(
    figure: go.Figure,
    output_path: str,
    width: int = 1200,
    height: int = 700,
) -> str:
    """
    Sauvegarde un graphique Plotly en PNG via kaleido.

    Si kaleido est absent, logue un avertissement et retourne "".

    Args:
        figure:      Figure Plotly.
        output_path: Chemin de sortie (.png).
        width:       Largeur en pixels.
        height:      Hauteur en pixels.

    Returns:
        Chemin du fichier PNG, ou "" si kaleido absent.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        pio.write_image(figure, str(path), format="png", width=width, height=height)
        logger.debug("[Exporter] PNG : %s", path.name)
        return str(path)
    except Exception as exc:
        logger.warning(
            "[Exporter] PNG echoue (kaleido absent) : %s. "
            "Installer : pip install kaleido",
            exc,
        )
        return ""


# ─── Export de tous les graphiques ────────────────────────────────────────────

def export_all_charts(
    charts_list: List[Dict[str, Any]],
    output_dir: str,
    formats: Tuple[str, ...] = ("html", "png"),
) -> Dict[str, Dict[str, str]]:
    """
    Exporte tous les graphiques dans le dossier de sortie.

    Nommage : {index:02d}_{chart_type}_{cols}.{ext}

    Args:
        charts_list: [{title, figure, chart_type, columns_involved}].
        output_dir:  Dossier de sortie.
        formats:     Formats a exporter ('html' et/ou 'png').

    Returns:
        {chart_title: {html: path, png: path}}
    """
    result: Dict[str, Dict[str, str]] = {}
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    for i, chart in enumerate(charts_list):
        title  = chart.get("title", f"chart_{i}")
        figure = chart.get("figure")
        ctype  = chart.get("chart_type", "chart")
        cols   = chart.get("columns_involved", [])

        if not isinstance(figure, go.Figure):
            continue

        cols_str  = "_".join(cols[:2])[:30]
        safe_name = _safe_filename(f"{i + 1:02d}_{ctype}_{cols_str}")
        paths: Dict[str, str] = {}

        if "html" in formats:
            paths["html"] = export_chart_html(
                figure, str(Path(output_dir) / f"{safe_name}.html")
            )
        if "png" in formats:
            exported = export_chart_png(
                figure, str(Path(output_dir) / f"{safe_name}.png")
            )
            if exported:
                paths["png"] = exported

        result[title] = paths

    logger.info(
        "[Exporter] %d graphiques exportes dans %s",
        len(result), output_dir,
    )
    return result


# ─── Serialisation JSON pour Directus ─────────────────────────────────────────

def serialize_chart_json(figure: go.Figure) -> Dict[str, Any]:
    """
    Serialise un graphique Plotly en dict JSON pour Directus.

    Args:
        figure: Figure Plotly.

    Returns:
        Dict JSON valide (non vide) avec cles 'data' et 'layout'.
    """
    return json.loads(pio.to_json(figure))


# ─── Generation du rapport MDX ────────────────────────────────────────────────

def generate_mdx_report(
    stats: Dict[str, Any],
    charts_list: List[Dict[str, Any]],
    gemini_comments: Dict[str, str],
    gemini_summary: List[str],
    output_path: str,
    chart_ids_by_title: Optional[Dict[str, str]] = None,
    target_analysis: Optional[Dict[str, Any]] = None,
    high_corr_pairs: Optional[List[Dict[str, Any]]] = None,
    dataset_info: Optional[Dict[str, Any]] = None,
    kpis_data: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """
    Genere le rapport MDX complet compatible MDXRenderer.tsx.

    Structure :
    1. Frontmatter YAML (title, date, n_rows, n_cols, n_charts, score_global)
    2. Resume Executif (<KeyPoints>)
    3. KPI Principaux (tableau)
    4. Statistiques Numeriques (tableau)
    5. Statistiques Categorielles (tableaux par colonne)
    6. Analyse variable cible (si fournie)
    7. Graphiques EDA (type, colonnes, <ChartEmbed>, commentaire)
    8. Correlations fortes
    9. Conclusions et Recommandations

    Args:
        stats:               {numeric_stats, categorical_stats}.
        charts_list:         [{title, figure, chart_type, columns_involved}].
        gemini_comments:     {chart_title: commentaire}.
        gemini_summary:      Liste de points cles Gemini.
        output_path:         Chemin du fichier MDX de sortie.
        chart_ids_by_title:  {chart_title: chart_id_directus}.
        target_analysis:     Analyse de la variable cible.
        high_corr_pairs:     Paires fortement correlees.
        dataset_info:        {n_rows, n_cols, dataset_name}.
        kpis_data:           Donnees KPI depuis kpi_engine.

    Returns:
        Tuple (chemin_fichier, contenu_mdx_str).
    """
    now           = datetime.now().strftime("%d/%m/%Y %H:%M")
    n_rows        = dataset_info.get("n_rows", "?") if dataset_info else "?"
    n_cols        = dataset_info.get("n_cols", "?") if dataset_info else "?"
    dataset_name  = dataset_info.get("dataset_name", "dataset") if dataset_info else "dataset"
    chart_ids     = chart_ids_by_title or {}
    n_charts      = len(charts_list)
    kpis          = kpis_data or {}
    kpis_principaux = kpis.get("kpis_principaux", [])
    stats_mesures   = kpis.get("stats_mesures", {})
    distributions   = kpis.get("distributions", {})
    evolution       = kpis.get("evolution", {})

    # Score global : depuis kpi_engine ou calcul simple
    score_global = _calculer_score_global(n_rows, kpis_principaux, stats)

    lines: List[str] = []

    # ── 1. Frontmatter YAML ───────────────────────────────────────────────────
    lines += [
        "---",
        f"title: Rapport EDA — {dataset_name}",
        f"date: {now}",
        f"dataset: {dataset_name}",
        f"n_rows: {n_rows}",
        f"n_cols: {n_cols}",
        f"n_charts: {n_charts}",
        f"score_global: {score_global}",
        "---",
        "",
        f"# Rapport EDA — {dataset_name}",
        "",
        f"**Généré le** : {now}  |  "
        f"**Score global** : {score_global}/100  |  "
        f"**Dataset** : {dataset_name}",
        "",
        "---",
        "",
    ]

    # ── 2. Resume Executif ────────────────────────────────────────────────────
    lines += ["## Résumé Exécutif", "", "<KeyPoints>"]

    if gemini_summary:
        for point in gemini_summary:
            lines.append(f"- {point}")
    else:
        lines.append(f"- Dataset **{dataset_name}** : {n_rows} enregistrements × {n_cols} colonnes analysés.")
        lines.append(f"- **{n_charts} graphiques** générés automatiquement.")
        if kpis_principaux:
            for kpi in kpis_principaux[:4]:
                val = kpi.get("valeur", "")
                if isinstance(val, float):
                    val = f"{val:,.2f}"
                elif isinstance(val, int):
                    val = f"{val:,}"
                lines.append(f"- **{kpi['label']}** : {val}")

    lines += ["</KeyPoints>", "", "---", ""]

    # ── 3. KPI Principaux ─────────────────────────────────────────────────────
    if kpis_principaux:
        lines += [
            "## KPI Principaux",
            "",
            "| Indicateur | Valeur | Unité |",
            "|------------|--------|-------|",
        ]
        for kpi in kpis_principaux:
            label   = kpi.get("label", "")
            val     = kpi.get("valeur", "")
            icone   = kpi.get("icone", "")
            formule = kpi.get("formule", "")

            # Formater la valeur
            if isinstance(val, float):
                val_str = f"{val:,.2f}"
            elif isinstance(val, int) and val > 999:
                val_str = f"{val:,}"
            else:
                val_str = str(val) if val is not None else "—"

            # Unite
            unite = "%" if "pct" in formule.lower() else ""

            lines.append(f"| **{icone} {label}** | {val_str} | {unite} |")

        lines += ["", "---", ""]

    # ── 4. Statistiques Numeriques ────────────────────────────────────────────
    numeric_stats = stats.get("numeric_stats", {})
    # Fusionner avec stats_mesures de kpi_engine si disponible
    if stats_mesures:
        for col, s in stats_mesures.items():
            if col not in numeric_stats:
                numeric_stats[col] = s

    if numeric_stats:
        lines += [
            "## Statistiques Numériques",
            "",
            "| Colonne | Moy. | Écart-type | Min | Médiane | Max | Skewness | Nulls |",
            "|---------|------|------------|-----|---------|-----|----------|-------|",
        ]
        for col, s in numeric_stats.items():
            mean  = s.get("mean")
            std   = s.get("std")
            mn    = s.get("min")
            med   = s.get("median") or s.get("q50")
            mx    = s.get("max")
            skew  = s.get("skewness", s.get("skew", ""))
            nulls = s.get("null_count", 0)
            null_pct = s.get("null_pct", 0.0)

            def _fmt(v: Any) -> str:
                if v is None:
                    return "—"
                if isinstance(v, (int, float)):
                    # Notation scientifique si tres grand ou tres petit
                    if abs(v) >= 1e6 or (abs(v) < 0.01 and v != 0):
                        return f"{v:.3e}"
                    return f"{v:,.4g}"
                return str(v)

            lines.append(
                f"| `{col}` | {_fmt(mean)} | {_fmt(std)} | {_fmt(mn)} | "
                f"{_fmt(med)} | {_fmt(mx)} | {_fmt(skew)} | "
                f"{nulls} ({null_pct}%) |"
            )
        lines += ["", "---", ""]

    # ── 5. Statistiques Categorielles ─────────────────────────────────────────
    categorical_stats = stats.get("categorical_stats", {})

    # Fusionner avec les distributions de kpi_engine
    if distributions:
        for col, dist_list in distributions.items():
            if col not in categorical_stats:
                categorical_stats[col] = {
                    "n_unique":   len(set(d["valeur"] for d in dist_list)),
                    "null_count": 0,
                    "null_pct":   0.0,
                    "top_values": [
                        {"value": d["valeur"], "count": d["count"], "pct": d["pct"]}
                        for d in dist_list
                    ],
                }

    if categorical_stats:
        lines += ["## Statistiques Catégorielles", ""]
        for col, s in categorical_stats.items():
            n_unique   = s.get("n_unique", "?")
            null_count = s.get("null_count", 0)
            null_pct   = s.get("null_pct", 0.0)
            top_values = s.get("top_values", [])

            lines += [
                f"### {col}",
                "",
                f"**Valeurs uniques** : {n_unique}  |  "
                f"**Valeurs manquantes** : {null_count} ({null_pct}%)",
                "",
                "| Valeur | Count | % |",
                "|--------|-------|---|",
            ]

            for tv in top_values[:5]:
                val = tv.get("value", tv.get("valeur", ""))
                cnt = tv.get("count", 0)
                pct = tv.get("pct", 0.0)
                lines.append(f"| {val} | {cnt} | {pct}% |")

            lines.append("")
        lines += ["---", ""]

    # ── 6. Variable Cible ─────────────────────────────────────────────────────
    if target_analysis:
        col_cible    = target_analysis.get("column", "")
        n_classes    = target_analysis.get("n_classes", 0)
        imb_ratio    = target_analysis.get("imbalance_ratio", 1.0)
        is_imbalanced = target_analysis.get("is_imbalanced", False)

        lines += [
            f"## Analyse Variable Cible : `{col_cible}`",
            "",
            f"- **Classes** : {n_classes}",
            f"- **Ratio déséquilibre** : {imb_ratio:.2f}",
        ]
        if is_imbalanced:
            lines.append(
                "- ⚠️ **Déséquilibre détecté** (ratio > 3) — "
                "envisager SMOTE ou repondération."
            )
        lines += ["", "| Classe | Count | % |", "|--------|-------|---|"]
        for dist in target_analysis.get("distribution", []):
            lines.append(
                f"| {dist['class']} | {dist['count']} | {dist['pct']}% |"
            )
        lines += ["", "---", ""]

    # ── 7. Evolution Temporelle ───────────────────────────────────────────────
    if evolution:
        lines += ["## Évolution Temporelle", ""]
        for col, evo_list in evolution.items():
            lines += [
                f"### {col.replace('_', ' ').title()}",
                "",
                "| Période | Effectif |",
                "|---------|----------|",
            ]
            for entry in evo_list:
                periode = entry.get("periode", "")
                count   = entry.get("count", 0)
                lines.append(f"| {periode} | {count:,} |")
            lines.append("")
        lines += ["---", ""]

    # ── 8. Graphiques EDA ─────────────────────────────────────────────────────
    lines += ["## Graphiques EDA", ""]

    for i, chart in enumerate(charts_list):
        title   = chart.get("title", f"Graphique {i + 1}")
        ctype   = chart.get("chart_type", "")
        cols    = chart.get("columns_involved", [])
        chart_id = chart_ids.get(title, "")
        comment  = gemini_comments.get(title, "")

        cols_str = ", ".join(f"`{c}`" for c in cols) if cols else "—"

        lines += [
            f"### {i + 1}. {title}",
            "",
            f"**Type** : `{ctype}` | **Colonnes** : {cols_str}",
            "",
        ]

        if chart_id:
            lines += [
                f'<ChartEmbed chartId="{chart_id}" title="{title}" />',
                "",
            ]
        else:
            lines += [
                "*Graphique disponible localement "
                "(chart_id non publié dans Directus)*",
                "",
            ]

        if comment:
            # Formater le commentaire comme blockquote propre
            comment_lines = comment.replace("\n\n", "\n").strip().split("\n")
            for cl in comment_lines:
                if cl.strip():
                    lines.append(f"> {cl.strip()}")
            lines.append("")

    lines += ["---", ""]

    # ── 9. Correlations Fortes ────────────────────────────────────────────────
    if high_corr_pairs:
        lines += [
            "## Corrélations Fortes (|r| > 0.8)",
            "",
            "| Variable A | Variable B | Corrélation |",
            "|-----------|-----------|-------------|",
        ]
        for pair in high_corr_pairs:
            lines.append(
                f"| `{pair['col_a']}` | `{pair['col_b']}` | "
                f"{pair['correlation']:.4f} |"
            )
        lines += [
            "",
            "> Variables fortement corrélées — attention à la multicolinéarité "
            "lors de la modélisation.",
            "",
            "---",
            "",
        ]

    # ── 10. Conclusions ───────────────────────────────────────────────────────
    lines += [
        "## Conclusions et Recommandations",
        "",
        f"Ce rapport EDA couvre **{n_rows} lignes** et **{n_cols} colonnes** "
        f"du dataset *{dataset_name}* avec **{n_charts} graphiques** générés.",
        "",
        "Prochaines étapes recommandées :",
        "- Valider les outliers identifiés dans les boxplots avec un expert métier.",
    ]

    if high_corr_pairs:
        lines.append(
            "- Traiter les corrélations fortes avant la modélisation "
            "(sélection de features)."
        )
    if target_analysis and target_analysis.get("is_imbalanced"):
        lines.append(
            "- Appliquer SMOTE ou repondération avant l'entraînement."
        )
    lines.append(
        "- Lancer le **Modeling Skill** pour construire un modèle ML sur ce dataset."
    )

    lines += [
        "",
        "_Rapport généré automatiquement par AI DATA SKILL SYSTEM_",
        "",
    ]

    # ── Ecrire le fichier ─────────────────────────────────────────────────────
    content = "\n".join(lines)
    path    = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    logger.info(
        "[Exporter] Rapport MDX : %s (%d lignes)",
        path.name, len(lines),
    )
    return str(path), content


# ─── Utilitaires ──────────────────────────────────────────────────────────────

def _safe_filename(name: str) -> str:
    """Remplace les caracteres speciaux par underscore."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name).strip("_")


def _calculer_score_global(
    n_rows: Any,
    kpis_principaux: List[Dict[str, Any]],
    stats: Dict[str, Any],
) -> int:
    """Calcule un score global simple (0-100) pour le dataset."""
    scores = []

    # Completude des donnees
    numeric_stats = stats.get("numeric_stats", {})
    if numeric_stats:
        null_pcts = [
            s.get("null_pct", 0.0)
            for s in numeric_stats.values()
            if s.get("null_pct") is not None
        ]
        if null_pcts:
            completude = max(0, 100 - (sum(null_pcts) / len(null_pcts)))
            scores.append(completude * 0.4)

    # Volume des donnees
    try:
        n = int(n_rows)
        vol_score = min(100, n / 10 * 100) if n < 1000 else 100
        scores.append(vol_score * 0.3)
    except (TypeError, ValueError):
        pass

    # Richesse KPIs
    kpi_score = min(100, len(kpis_principaux) * 15)
    scores.append(kpi_score * 0.3)

    if not scores:
        return 75

    return int(np.clip(sum(scores), 0, 100))