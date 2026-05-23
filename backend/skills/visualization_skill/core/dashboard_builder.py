"""
backend/skills/visualization_skill/core/dashboard_builder.py
Construction intelligente du dashboard BI.

Utilise Gemini pour planifier les graphiques et les KPIs.
Fallback local base sur kpi_engine si Gemini est indisponible.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go

from skills.visualization_skill.core.kpi_engine import (
    detecter_mappings_id_label,
    classifier_colonnes,
    calculer_kpis,
    plan_graphiques_local,
)
from skills.visualization_skill.core.charts import (
    generate_bar_count,
    generate_bar_mesure,
    generate_donut,
    generate_stacked_bar,
    generate_boxplot_mesure,
    generate_line_count,
    generate_heatmap_crosstab,
    generate_scatter_mesures,
)

logger = logging.getLogger(__name__)


# ─── Prompt Gemini pour le plan de dashboard ─────────────────────────────────

_PROMPT_PLAN = """Tu es un expert en Business Intelligence et visualisation de données.

Dataset: {n_rows} lignes × {n_cols} colonnes

Colonnes classifiées:
DIMENSIONS (catégorielles analytiques, utilisables comme axe X ou couleur):
{detail_entites}

MESURES (numériques réelles, utilisables comme axe Y):
{detail_mesures}

TEMPORELLES (années/périodes, pour les axes X temporels):
{detail_temporelles}

EXCLUES (ne jamais utiliser): {exclues}

Génère un dashboard BI avec 8 à 14 graphiques pertinents et 4 à 8 KPIs.

RÈGLES STRICTES (violation = plan invalide):
1. x et y doivent avoir une relation logique et analytique
2. Jamais d'ID ou de colonne exclue comme x, y ou color
3. Pour type "bar": x=dimension, y="count" OU y=mesure_numerique, agg="count"|"mean"|"sum"
4. Pour type "line": x=temporelle OU dimension ordonnée, y="count" OU y=mesure, agg="count"|"mean"
5. Pour type "donut": x=dimension (2-6 valeurs), y="count"
6. Pour type "stacked_bar": x=dimension, y="count", color=autre_dimension (2-6 valeurs)
7. Pour type "boxplot": x=dimension (2-10 valeurs), y=mesure_numerique
8. Pour type "heatmap": x=dimension1 (2-10 val), y=dimension2 (2-10 val), agg="count"
9. Pour type "scatter": x=mesure1, y=mesure2, color=dimension (optionnel)
10. orientation: "v" (vertical, defaut) ou "h" (horizontal si > 8 valeurs sur X)
11. ordre_x: tableau ordonné si applicable (ex: ["L1","L2","L3","M1","M2"]) sinon null

Réponds UNIQUEMENT avec ce JSON valide (pas de markdown, pas de texte avant/après):
{{
  "kpis": [
    {{"label": "Libelle court max 25 chars", "colonne": "nom_col ou null", "formule": "count|nunique|sum|mean|pct_value=XXX", "icone": "emoji"}},
    ...
  ],
  "graphiques": [
    {{
      "type": "bar|line|donut|stacked_bar|boxplot|heatmap|scatter",
      "x": "nom_colonne",
      "y": "nom_colonne ou count",
      "color": "nom_colonne ou null",
      "titre": "Titre clair et informatif",
      "orientation": "v ou h",
      "ordre_x": ["val1", "val2"] ou null,
      "top_n": null ou entier,
      "agg": "count|sum|mean|median|distribution",
      "justification": "Pourquoi ce graphique est utile en 1 phrase"
    }},
    ...
  ]
}}"""


def analyser_avec_gemini(
    df: pd.DataFrame,
    colonnes: Dict[str, List[str]],
) -> Optional[Dict[str, Any]]:
    """
    Demande a Gemini de planifier les graphiques et KPIs.

    Args:
        df:       DataFrame source.
        colonnes: Colonnes classifiees.

    Returns:
        Plan JSON valide ou None si Gemini indisponible.
    """
    try:
        from src.utils.gemini_client import generate_content
    except ImportError:
        logger.warning("[Dashboard] gemini_client non disponible")
        return None

    entites = colonnes.get("entites", [])
    mesures = colonnes.get("mesures", [])
    temporelles = colonnes.get("temporelles", [])
    exclues = colonnes.get("exclues", []) + colonnes.get("noms_propres", [])

    # Detail des dimensions
    detail_entites_lines = []
    for col in entites:
        vals = df[col].dropna().value_counts().head(8)
        vals_str = ", ".join([f'"{v}"({c})' for v, c in vals.items()])
        detail_entites_lines.append(f"  - {col} ({df[col].nunique()} valeurs): {vals_str}")

    # Detail des mesures
    detail_mesures_lines = []
    for col in mesures:
        v = df[col].dropna()
        detail_mesures_lines.append(
            f"  - {col}: min={v.min():.2g}, moy={v.mean():.2g}, max={v.max():.2g}"
        )

    # Detail des temporelles
    detail_temporelles_lines = []
    for col in temporelles:
        vals = sorted(df[col].dropna().unique().tolist())[:10]
        detail_temporelles_lines.append(f"  - {col}: {vals}")

    prompt = _PROMPT_PLAN.format(
        n_rows=len(df),
        n_cols=df.shape[1],
        detail_entites="\n".join(detail_entites_lines) or "  (aucune)",
        detail_mesures="\n".join(detail_mesures_lines) or "  (aucune)",
        detail_temporelles="\n".join(detail_temporelles_lines) or "  (aucune)",
        exclues=", ".join(exclues[:20]),
    )

    logger.info("[Dashboard] Appel Gemini pour planifier le dashboard...")
    text = generate_content(prompt, temperature=0.1)

    if not text:
        logger.warning("[Dashboard] Gemini n'a pas repondu — fallback local")
        return None

    # Nettoyer le JSON
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    text = text.strip().lstrip("json").strip()

    try:
        plan = json.loads(text)
        # Valider la structure minimale
        if "graphiques" not in plan:
            raise ValueError("Cle 'graphiques' manquante")
        plan = valider_plan(plan, df, colonnes)
        logger.info(
            "[Dashboard] Plan Gemini valide : %d graphiques, %d KPIs",
            len(plan.get("graphiques", [])),
            len(plan.get("kpis", [])),
        )
        return plan
    except Exception as exc:
        logger.warning("[Dashboard] Plan Gemini invalide (%s) — fallback local", exc)
        return None


def valider_plan(
    plan: Dict[str, Any],
    df: pd.DataFrame,
    colonnes: Dict[str, List[str]],
) -> Dict[str, Any]:
    """
    Valide et corrige le plan de graphiques.

    Supprime les specs avec colonnes inexistantes ou incoherentes.
    Corrige les types invalides.

    Args:
        plan:     Plan JSON a valider.
        df:       DataFrame source.
        colonnes: Colonnes classifiees.

    Returns:
        Plan valide (graphiques incoherents supprimes).
    """
    valid_types = {"bar", "line", "donut", "stacked_bar", "boxplot", "heatmap", "scatter"}
    exclues_set = set(
        colonnes.get("exclues", []) + colonnes.get("noms_propres", [])
    )
    all_cols = set(df.columns)

    graphiques_valides = []
    for spec in plan.get("graphiques", []):
        spec_type = spec.get("type", "")
        x = spec.get("x", "")
        y = spec.get("y", "")
        color = spec.get("color")

        # Type valide
        if spec_type not in valid_types:
            logger.debug("[Dashboard] Spec ignoree — type invalide : %s", spec_type)
            continue

        # X doit exister (sauf si x est une colonne)
        if x not in all_cols:
            logger.debug("[Dashboard] Spec ignoree — x='%s' inexistant", x)
            continue

        # Y doit exister ou etre "count"
        if y != "count" and y not in all_cols:
            logger.debug("[Dashboard] Spec ignoree — y='%s' inexistant", y)
            continue

        # X et Y ne doivent pas etre des colonnes exclues
        if x in exclues_set:
            logger.debug("[Dashboard] Spec ignoree — x='%s' exclu", x)
            continue
        if y != "count" and y in exclues_set:
            logger.debug("[Dashboard] Spec ignoree — y='%s' exclu", y)
            continue

        # Color doit exister si specifiee
        if color and color not in all_cols:
            spec["color"] = None

        # Defaults
        spec.setdefault("orientation", "v")
        spec.setdefault("agg", "count")
        spec.setdefault("top_n", None)
        spec.setdefault("ordre_x", None)

        graphiques_valides.append(spec)

    plan["graphiques"] = graphiques_valides
    logger.info("[Dashboard] Validation : %d/%d graphiques retenus",
                len(graphiques_valides), len(plan.get("graphiques", [])) + len(graphiques_valides))
    return plan


# ─── Construction des graphiques Plotly ──────────────────────────────────────



def _construire_dict_id_label(
    df: "pd.DataFrame",
    id_col: str,
    label_col: str,
) -> Dict[str, str]:
    """
    Construit {id_value: label_value} depuis le DataFrame.

    Args:
        df:        DataFrame source.
        id_col:    Colonne identifiant (ex: id_cours).
        label_col: Colonne libelle (ex: nom_cours).

    Returns:
        {CRS001: "Comptabilite Generale", CRS002: "Analyse Financiere", ...}
    """
    if id_col not in df.columns or label_col not in df.columns:
        return {}
    return (
        df[[id_col, label_col]]
        .drop_duplicates(subset=[id_col])
        .set_index(id_col)[label_col]
        .astype(str)
        .to_dict()
    )


def _ajouter_reference_ids(
    fig: go.Figure,
    df: "pd.DataFrame",
    columns_involved: List[str],
    mappings_id: Dict[str, str],
) -> go.Figure:
    """
    Ajoute un tableau de reference ID -> Libelle a droite du graphique.

    S'active automatiquement quand une colonne impliquee est un identifiant
    et qu'une colonne libelle correspondante existe dans le DataFrame.

    Format affiche :
        📋 Id Cours
        CRS001 : Comptabilite Generale
        CRS002 : Analyse Financiere
        ...

    Args:
        fig:              Figure Plotly a enrichir.
        df:               DataFrame source.
        columns_involved: Colonnes utilisees dans le graphique.
        mappings_id:      {id_col: label_col} depuis detecter_mappings_id_label().

    Returns:
        Figure enrichie du tableau de reference.
    """
    import re as _re

    ref_blocks: List[str] = []

    for col in columns_involved:
        if col not in df.columns:
            continue

        col_l = col.lower().strip()
        is_id_col = (
            col_l.startswith("id_")
            or col_l.startswith("id ")
            or col_l.endswith("_id")
        )
        if not is_id_col:
            continue

        # Chercher la colonne libelle depuis mappings ou auto-detection
        label_col = mappings_id.get(col)
        if not label_col or label_col not in df.columns:
            base = _re.sub(r"^id[_\s]?", "", col_l).strip("_")
            for cand in df.columns:
                if (cand != col
                        and base in cand.lower()
                        and (pd.api.types.is_string_dtype(df[cand]) or df[cand].dtype == object)
                        and df[cand].nunique() == df[col].nunique()):
                    label_col = cand
                    break

        if not label_col or label_col not in df.columns:
            continue

        # Construire le dict {id_value: label_value}
        id_label = _construire_dict_id_label(df, col, label_col)
        if not id_label:
            continue

        # Titre du bloc
        col_title = col.replace("_", " ").title()
        lines = [f"<b>📋 {col_title}</b>"]

        # Lignes de correspondance triees
        for id_val, label_val in sorted(id_label.items()):
            label_short = (label_val[:22] + "...") if len(label_val) > 25 else label_val
            lines.append(
                f"<span style='color:#0078D4;font-family:monospace'>"
                f"{id_val}</span>"
                f"<span style='color:#605E5C'> : {label_short}</span>"
            )

        ref_blocks.append("<br>".join(lines))

    if not ref_blocks:
        return fig

    full_text = "<br><br>".join(ref_blocks)

    # Calculer la marge droite necessaire
    all_lines = full_text.replace("<b>", "").replace("</b>", "")
    all_lines = _re.sub(r"<[^>]+>", "", all_lines).split("<br>")
    max_chars  = max((len(l) for l in all_lines), default=30)
    right_margin = max(180, min(380, max_chars * 7 + 20))

    fig.add_annotation(
        text=full_text,
        xref="paper",
        yref="paper",
        x=1.01,
        y=1.0,
        xanchor="left",
        yanchor="top",
        showarrow=False,
        font=dict(
            size=9,
            color="#323130",
            family="Segoe UI, Consolas, monospace",
        ),
        align="left",
        bgcolor="rgba(250, 250, 250, 0.95)",
        bordercolor="#D0D0D0",
        borderwidth=1,
        borderpad=8,
    )

    # Appliquer la marge droite elargie
    fig.update_layout(margin=dict(r=right_margin))
    return fig

def build_intelligent_charts(
    df: pd.DataFrame,
    plan_graphiques: List[Dict[str, Any]],
    mappings_id: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    Genere les graphiques Plotly depuis le plan de specs.

    Args:
        df:              DataFrame source.
        plan_graphiques: Liste de specs issues de Gemini ou du fallback local.

    Returns:
        Liste de dicts :
        [{"title", "figure", "chart_type", "columns_involved"}]
    """
    charts: List[Dict[str, Any]] = []

    for i, spec in enumerate(plan_graphiques):
        spec_type = spec.get("type", "bar")
        x        = spec.get("x", "")
        y        = spec.get("y", "count")
        color    = spec.get("color")
        titre    = spec.get("titre", f"Graphique {i + 1}")
        orient   = spec.get("orientation", "v")
        ordre_x  = spec.get("ordre_x")
        top_n    = spec.get("top_n", 15)
        agg      = spec.get("agg", "count")

        if x not in df.columns:
            continue

        try:
            fig = _generer_figure(
                df=df,
                spec_type=spec_type,
                x=x,
                y=y,
                color=color,
                titre=titre,
                orientation=orient,
                ordre_x=ordre_x,
                top_n=top_n or 15,
                agg=agg,
            )
            if fig is None:
                continue

            cols_involved = [c for c in [x, y, color]
                             if c and c != "count" and c in df.columns]

            # Ajouter le tableau de reference ID -> Libelle si necessaire
            if mappings_id is not None:
                fig = _ajouter_reference_ids(fig, df, cols_involved, mappings_id)
            else:
                # Auto-detection sans mappings fournis
                fig = _ajouter_reference_ids(fig, df, cols_involved, {})

            charts.append({
                "title":            titre,
                "figure":           fig,
                "chart_type":       spec_type,
                "columns_involved": cols_involved,
            })
            logger.debug("[Dashboard] Graphique '%s' genere (%s)", titre, spec_type)

        except Exception as exc:
            logger.warning("[Dashboard] Graphique '%s' echoue : %s", titre, exc)

    logger.info("[Dashboard] %d graphiques Plotly construits", len(charts))
    return charts


def _generer_figure(
    df: pd.DataFrame,
    spec_type: str,
    x: str,
    y: str,
    color: Optional[str],
    titre: str,
    orientation: str,
    ordre_x: Optional[List[str]],
    top_n: int,
    agg: str,
) -> Optional[go.Figure]:
    """Dispatch vers la bonne fonction de generation selon le type."""

    if spec_type == "donut":
        return generate_donut(df, x, titre)

    if spec_type == "line":
        return generate_line_count(df, x, y, agg, titre)

    if spec_type == "stacked_bar":
        if color and color in df.columns:
            return generate_stacked_bar(df, x, color, titre, ordre_x)
        return None

    if spec_type == "boxplot":
        if y != "count" and y in df.columns:
            return generate_boxplot_mesure(df, x, y, titre, ordre_x)
        return None

    if spec_type == "heatmap":
        if y != "count" and y in df.columns:
            return generate_heatmap_crosstab(df, x, y, titre, ordre_x)
        # Si y = "count", on fait un crosstab entre x et une autre dimension
        return None

    if spec_type == "scatter":
        if y != "count" and y in df.columns and pd.api.types.is_numeric_dtype(df[y]):
            return generate_scatter_mesures(df, x, y, color, titre)
        return None

    # Par defaut : bar
    if y == "count" or agg == "count":
        return generate_bar_count(df, x, titre, orientation, ordre_x, top_n)
    else:
        if y in df.columns:
            return generate_bar_mesure(df, x, y, agg, titre, orientation, ordre_x, top_n)
        return generate_bar_count(df, x, titre, orientation, ordre_x, top_n)


# ─── Pipeline complet analyse + planification ─────────────────────────────────



def _appliquer_mappings_id(
    plan_graphiques: List[Dict[str, Any]],
    mappings: Dict[str, str],
) -> List[Dict[str, Any]]:
    """
    Remplace les colonnes ID par leurs libelles dans le plan de graphiques.

    Ex : x="id_cours" -> x="nom_cours" si le mapping existe.
    L ID reste reference interne mais n est jamais affiche dans les graphiques.

    Args:
        plan_graphiques: Liste de specs graphiques.
        mappings:        {id_col: label_col} depuis detecter_mappings_id_label().

    Returns:
        Plan avec colonnes ID remplacees par leurs libelles.
    """
    if not mappings:
        return plan_graphiques

    result = []
    for spec in plan_graphiques:
        spec = dict(spec)
        for field in ("x", "y", "color"):
            val = spec.get(field)
            if val and val in mappings:
                old_val = val
                spec[field] = mappings[val]
                logger.debug(
                    "[Dashboard] Substitution %s : %s -> %s",
                    field, old_val, spec[field],
                )
        result.append(spec)
    return result

def analyser_et_planifier(
    df: pd.DataFrame,
    use_gemini: bool = True,
    question: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Pipeline complet : classifier → planifier (Gemini ou local) → calculer KPIs.

    Args:
        df:         DataFrame source.
        use_gemini: Tenter Gemini d'abord.
        question:   Question analytique pour orienter le plan.

    Returns:
        Dict :
        {
          "colonnes":        dict classifiees,
          "plan_graphiques": list de specs,
          "kpis_data":       dict KPIs calcules,
          "source":          "gemini" ou "local",
        }
    """
    # 1. Classifier les colonnes
    colonnes = classifier_colonnes(df)

    # 2. Planifier les graphiques
    plan_gemini = None
    source = "local"

    if use_gemini:
        plan_gemini = analyser_avec_gemini(df, colonnes)

    if plan_gemini and plan_gemini.get("graphiques"):
        plan_graphiques = plan_gemini["graphiques"]
        spec_kpis = plan_gemini.get("kpis")
        source = "gemini"
    else:
        plan_graphiques = plan_graphiques_local(df, colonnes)
        spec_kpis = None

    # 3. Calculer les KPIs
    kpis_data = calculer_kpis(df, colonnes, spec_kpis)

    # Substituer les IDs par leurs libelles dans le plan
    mappings_id = detecter_mappings_id_label(df)
    plan_graphiques = _appliquer_mappings_id(plan_graphiques, mappings_id)

    logger.info(
        "[Dashboard] Analyse complete — source=%s, graphiques=%d, kpis=%d, mappings_id=%d",
        source,
        len(plan_graphiques),
        len(kpis_data.get("kpis_principaux", [])),
        len(mappings_id),
    )

    return {
        "colonnes":        colonnes,
        "plan_graphiques": plan_graphiques,
        "kpis_data":       kpis_data,
        "source":          source,
        "mappings_id":     mappings_id,
    }


# ─── Commentaire Gemini par graphique ─────────────────────────────────────────

def get_gemini_chart_comment(
    chart_title: str,
    chart_stats: str,
    api_key: Optional[str] = None,
) -> str:
    """
    Genere un commentaire narratif Gemini sur un graphique.

    Args:
        chart_title: Titre du graphique.
        chart_stats: Statistiques associees.
        api_key:     Cle API (non utilisee — rotation via gemini_client).

    Returns:
        Commentaire de 2-3 phrases, chaine vide si echec.
    """
    try:
        from src.utils.gemini_client import generate_content
    except ImportError:
        return ""

    prompt = (
        f"Tu es un expert Data Analyst.\n"
        f"Graphique : {chart_title}\n"
        f"Données : {chart_stats}\n\n"
        f"Ecris un commentaire de 2 a 3 phrases en francais. "
        f"Decris les tendances et insights cles en langage metier. Sois direct et precis."
    )

    try:
        result = generate_content(prompt, temperature=0.3)
        return result or ""
    except Exception as exc:
        logger.debug("[Gemini] Commentaire echoue pour '%s' : %s", chart_title, exc)
        return ""


def get_gemini_eda_summary(
    kpis_data: Dict[str, Any],
    colonnes: Dict[str, List[str]],
    source_plan: str,
    api_key: Optional[str] = None,
) -> List[str]:
    """
    Genere un resume executif global via Gemini.

    Returns:
        Liste de 4-6 points cles. Liste vide si echec.
    """
    try:
        from src.utils.gemini_client import generate_content
    except ImportError:
        return []

    kpis_principaux = kpis_data.get("kpis_principaux", [])
    kpis_str = "\n".join(
        f"- {k['label']}: {k['valeur']}"
        for k in kpis_principaux[:8]
    )
    n_entites = len(colonnes.get("entites", []))
    n_mesures = len(colonnes.get("mesures", []))

    prompt = (
        f"Tu es un Data Scientist expert.\n"
        f"Dataset analysé : {n_entites} dimensions, {n_mesures} mesures.\n"
        f"KPIs principaux :\n{kpis_str}\n\n"
        f"Génère 4 a 6 points cles du résumé executif en francais. "
        f"Réponds UNIQUEMENT avec un tableau JSON de strings : [\"point 1\", \"point 2\", ...]"
    )

    try:
        text = generate_content(prompt, temperature=0.3)
        if not text:
            return []
        text = text.strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:-1])
        result = json.loads(text)
        return [str(item) for item in result] if isinstance(result, list) else []
    except Exception as exc:
        logger.debug("[Gemini] Resume EDA echoue : %s", exc)
        return []