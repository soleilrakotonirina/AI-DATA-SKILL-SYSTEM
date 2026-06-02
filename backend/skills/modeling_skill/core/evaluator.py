"""
backend/skills/modeling_skill/core/evaluator.py
Evaluation des modeles ML : metriques, graphiques Plotly, Model Card MDX.

Logique Python pure — testable independamment.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go

logger = logging.getLogger(__name__)

# Palette BI
_COLORS = ["#0078D4", "#107C10", "#A80000", "#FFB900", "#8764B8"]


# ─── Metriques ────────────────────────────────────────────────────────────────

def compute_classification_metrics(
    y_true: Any,
    y_pred: Any,
    y_proba: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Calcule les metriques de classification.

    Args:
        y_true:  Labels reels.
        y_pred:  Labels predits.
        y_proba: Probabilites predites (pour roc_auc).

    Returns:
        Dict : {accuracy, precision, recall, f1, roc_auc, confusion_matrix}
    """
    from sklearn.metrics import (
        accuracy_score,
        classification_report,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
    )

    metrics: Dict[str, Any] = {}

    try:
        metrics["accuracy"] = round(float(accuracy_score(y_true, y_pred)), 4)

        avg = "binary" if len(set(y_true)) == 2 else "weighted"

        metrics["precision"] = round(
            float(precision_score(y_true, y_pred, average=avg, zero_division=0)), 4
        )
        metrics["recall"] = round(
            float(recall_score(y_true, y_pred, average=avg, zero_division=0)), 4
        )
        metrics["f1"] = round(
            float(f1_score(y_true, y_pred, average=avg, zero_division=0)), 4
        )

        if y_proba is not None:
            try:
                multi_class = "raise" if avg == "binary" else "ovr"
                metrics["roc_auc"] = round(
                    float(roc_auc_score(y_true, y_proba, multi_class=multi_class)),
                    4,
                )
            except Exception as exc:
                logger.debug("[Evaluator] roc_auc impossible : %s", exc)

        # Matrice de confusion comme liste de listes
        cm = confusion_matrix(y_true, y_pred)
        metrics["confusion_matrix"] = cm.tolist()

    except Exception as exc:
        logger.error("[Evaluator] Erreur metriques classification : %s", exc)

    logger.info("[Evaluator] Metriques classification : %s", metrics)
    return metrics


def compute_regression_metrics(
    y_true: Any,
    y_pred: Any,
) -> Dict[str, float]:
    """
    Calcule les metriques de regression.

    Args:
        y_true: Valeurs reelles.
        y_pred: Valeurs predites.

    Returns:
        Dict : {rmse, mae, r2, mape}
    """
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    metrics: Dict[str, float] = {}
    try:
        y_true_arr = np.array(y_true, dtype=float)
        y_pred_arr = np.array(y_pred, dtype=float)

        metrics["rmse"] = round(
            float(np.sqrt(mean_squared_error(y_true_arr, y_pred_arr))), 4
        )
        metrics["mae"] = round(
            float(mean_absolute_error(y_true_arr, y_pred_arr)), 4
        )
        metrics["r2"] = round(float(r2_score(y_true_arr, y_pred_arr)), 4)

        # MAPE — eviter division par zero
        mask = y_true_arr != 0
        if mask.any():
            mape = float(
                np.mean(np.abs((y_true_arr[mask] - y_pred_arr[mask]) / y_true_arr[mask]))
            ) * 100
            metrics["mape"] = round(mape, 4)

    except Exception as exc:
        logger.error("[Evaluator] Erreur metriques regression : %s", exc)

    logger.info("[Evaluator] Metriques regression : %s", metrics)
    return metrics


# ─── Graphiques Plotly ────────────────────────────────────────────────────────

def generate_confusion_matrix_figure(
    y_true: Any,
    y_pred: Any,
    model_name: str = "",
    labels: Optional[List[str]] = None,
) -> go.Figure:
    """
    Genere un graphique Plotly de la matrice de confusion.

    Heatmap avec annotations des valeurs. Palette bleu clair → bleu fonce.

    Args:
        y_true:     Labels reels.
        y_pred:     Labels predits.
        model_name: Nom du modele pour le titre.
        labels:     Labels des classes (optionnel).

    Returns:
        Figure Plotly.
    """
    from sklearn.metrics import confusion_matrix

    cm = confusion_matrix(y_true, y_pred, labels=labels)
    classes = labels or sorted(list(set(list(y_true) + list(y_pred))))
    classes = [str(c) for c in classes]

    n = len(classes)
    annotations = []
    for i in range(n):
        for j in range(n):
            val = int(cm[i, j])
            annotations.append(dict(
                x=j, y=i,
                text=str(val),
                xref="x", yref="y",
                showarrow=False,
                font=dict(
                    size=max(10, min(16, 100 // max(n, 1))),
                    color="white" if cm[i, j] > cm.max() * 0.5 else "black",
                ),
            ))

    fig = go.Figure(go.Heatmap(
        z=cm,
        x=classes,
        y=classes,
        colorscale="Blues",
        colorbar=dict(title="Count"),
        hovertemplate=(
            "Reel : %{y}<br>Predit : %{x}<br>Count : %{z}<extra></extra>"
        ),
    ))

    title = f"Matrice de Confusion"
    if model_name:
        title += f" — {model_name}"

    fig.update_layout(
        title=dict(text=title, font=dict(size=14), x=0),
        xaxis=dict(title="Predit", tickangle=-20 if n > 6 else 0),
        yaxis=dict(title="Reel"),
        annotations=annotations,
        paper_bgcolor="white",
        font=dict(family="Segoe UI, Inter, sans-serif", size=12),
        margin=dict(l=80, r=30, t=60, b=80),
        height=max(400, n * 60),
    )

    logger.debug("[Evaluator] Confusion matrix figure generee (%dx%d)", n, n)
    return fig


def generate_roc_curve_figure(
    y_true: Any,
    y_proba: Any,
    model_name: str = "",
) -> go.Figure:
    """
    Genere un graphique Plotly de la courbe ROC (binary classification uniquement).

    Trace la courbe ROC + diagonale de reference (AUC=0.5).

    Args:
        y_true:     Labels reels (binaires).
        y_proba:    Probabilites predites pour la classe positive.
        model_name: Nom du modele pour le titre.

    Returns:
        Figure Plotly.

    Raises:
        ValueError: Si le probleme n'est pas binaire.
    """
    from sklearn.metrics import auc, roc_auc_score, roc_curve

    n_classes = len(set(y_true))
    if n_classes != 2:
        raise ValueError(
            f"ROC curve uniquement pour classification binaire (n_classes={n_classes})"
        )

    fpr, tpr, _ = roc_curve(y_true, y_proba)
    roc_auc     = round(float(auc(fpr, tpr)), 4)

    fig = go.Figure()

    # Courbe ROC
    fig.add_trace(go.Scatter(
        x=fpr,
        y=tpr,
        mode="lines",
        name=f"ROC (AUC = {roc_auc:.3f})",
        line=dict(color=_COLORS[0], width=2.5),
        hovertemplate="FPR : %{x:.4f}<br>TPR : %{y:.4f}<extra></extra>",
    ))

    # Diagonale de reference
    fig.add_trace(go.Scatter(
        x=[0, 1],
        y=[0, 1],
        mode="lines",
        name="Reference (AUC = 0.5)",
        line=dict(color="#A0A0A0", width=1.5, dash="dash"),
        hoverinfo="skip",
    ))

    title = f"Courbe ROC (AUC = {roc_auc:.3f})"
    if model_name:
        title += f" — {model_name}"

    fig.update_layout(
        title=dict(text=title, font=dict(size=14), x=0),
        xaxis=dict(
            title="Taux de Faux Positifs (FPR)",
            range=[-0.02, 1.02],
            showgrid=True, gridcolor="#E8E8E8",
        ),
        yaxis=dict(
            title="Taux de Vrais Positifs (TPR)",
            range=[-0.02, 1.02],
            showgrid=True, gridcolor="#E8E8E8",
        ),
        paper_bgcolor="white",
        font=dict(family="Segoe UI, Inter, sans-serif", size=12),
        legend=dict(x=0.6, y=0.1),
        margin=dict(l=70, r=30, t=60, b=70),
    )

    logger.debug("[Evaluator] ROC figure generee — AUC=%.4f", roc_auc)
    return fig


# ─── Model Card MDX ───────────────────────────────────────────────────────────

def generate_model_card_mdx(
    model_name: str,
    problem_type: str,
    metrics: Dict[str, Any],
    feature_names: List[str],
    best_params: Dict[str, Any],
    dataset_info: Dict[str, Any],
    output_path: str,
    confusion_matrix_chart_id: Optional[str] = None,
    roc_chart_id: Optional[str] = None,
    feature_importance: Optional[Dict[str, float]] = None,
    all_models_results: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, str]:
    """
    Genere la Model Card MDX complete compatible MDXRenderer.tsx Next.js.

    Contenu :
    - Frontmatter YAML
    - Informations du modele
    - Tableau des metriques (<MetricTable>)
    - Comparaison des modeles
    - Hyperparametres
    - Features importantes (top 10)
    - <ChartEmbed> confusion matrix + ROC
    - Instructions de chargement
    - Limitations

    Args:
        model_name:                Nom du meilleur algorithme.
        problem_type:              Type de probleme ML.
        metrics:                   Metriques du meilleur modele.
        feature_names:             Noms des features utilisees.
        best_params:               Meilleurs hyperparametres (apres tuning).
        dataset_info:              {n_rows, n_cols, n_features, dataset_name}.
        output_path:               Chemin de sortie du fichier MDX.
        confusion_matrix_chart_id: ID du chart Directus (optionnel).
        roc_chart_id:              ID du chart ROC Directus (optionnel).
        feature_importance:        {feature: importance} optionnel.
        all_models_results:        Resultats de tous les modeles evalues.

    Returns:
        Tuple (chemin_fichier, contenu_mdx_str).
    """
    now          = datetime.now().strftime("%d/%m/%Y %H:%M")
    dataset_name = dataset_info.get("dataset_name", "dataset")
    n_rows       = dataset_info.get("n_rows", "?")
    n_features   = dataset_info.get("n_features", "?")
    lines: List[str] = []

    # ── Frontmatter ──────────────────────────────────────────────────────────
    lines += [
        "---",
        f"title: Model Card — {model_name}",
        f"date: {now}",
        f"model: {model_name}",
        f"problem_type: {problem_type}",
        f"dataset: {dataset_name}",
        "---",
        "",
        f"# Model Card — {model_name}",
        "",
        (
            f"**Entraine le** : {now}  |  "
            f"**Type** : {problem_type}  |  "
            f"**Dataset** : {dataset_name}"
        ),
        "",
        "---",
        "",
    ]

    # ── Informations generales ────────────────────────────────────────────────
    lines += [
        "## Informations du Modele",
        "",
        "| Parametre      | Valeur                        |",
        "|----------------|-------------------------------|",
        f"| Algorithme     | `{model_name}`                |",
        f"| Type probleme  | {problem_type}                |",
        f"| Dataset        | {dataset_name}                |",
        f"| Lignes train   | {n_rows}                      |",
        f"| Features       | {n_features}                  |",
        f"| Date           | {now}                         |",
        "",
        "---",
        "",
    ]

    # ── Metriques ─────────────────────────────────────────────────────────────
    lines += [
        "## Metriques d'Evaluation",
        "",
        "<MetricTable>",
        "",
        "| Metrique | Valeur |",
        "|----------|--------|",
    ]
    for k, v in metrics.items():
        if k == "confusion_matrix":
            continue
        val_str = f"{v:.4f}" if isinstance(v, float) else str(v)
        lines.append(f"| **{k}** | {val_str} |")
    lines += ["", "</MetricTable>", "", "---", ""]

    # ── Comparaison des modeles ───────────────────────────────────────────────
    if all_models_results:
        lines += ["## Comparaison des Modeles", "", "| Modele | Metrique principale | Score CV |", "|--------|---------------------|----------|"]
        for res in sorted(
            all_models_results,
            key=lambda r: list(r.get("metrics", {0: 0}).values())[0]
            if r.get("metrics") else 0,
            reverse=True,
        )[:10]:
            name_r   = res.get("model_name", "?")
            m        = res.get("metrics", {})
            cv       = res.get("cv_scores", {})
            primary  = list(m.values())[0] if m else "?"
            cv_mean  = cv.get("mean", "?")
            primary_str = f"{primary:.4f}" if isinstance(primary, float) else str(primary)
            cv_str      = f"{cv_mean:.4f}" if isinstance(cv_mean, float) else str(cv_mean)
            star = " ⭐" if name_r == model_name else ""
            lines.append(f"| {name_r}{star} | {primary_str} | {cv_str} |")
        lines += ["", "---", ""]

    # ── Hyperparametres ───────────────────────────────────────────────────────
    if best_params:
        lines += [
            "## Hyperparametres (apres tuning)",
            "",
            "| Parametre | Valeur |",
            "|-----------|--------|",
        ]
        for k, v in best_params.items():
            lines.append(f"| `{k}` | `{v}` |")
        lines += ["", "---", ""]

    # ── Feature Importance ────────────────────────────────────────────────────
    if feature_importance:
        sorted_fi = sorted(
            feature_importance.items(), key=lambda x: x[1], reverse=True
        )[:10]
        lines += [
            "## Top 10 Features les Plus Importantes",
            "",
            "| Rang | Feature | Importance |",
            "|------|---------|------------|",
        ]
        for i, (feat, imp) in enumerate(sorted_fi, start=1):
            lines.append(f"| {i} | `{feat}` | {imp:.4f} |")
        lines += ["", "---", ""]

    # ── Graphiques ────────────────────────────────────────────────────────────
    has_charts = confusion_matrix_chart_id or roc_chart_id
    if has_charts:
        lines += ["## Graphiques d'Evaluation", ""]

    if confusion_matrix_chart_id:
        lines += [
            "### Matrice de Confusion",
            "",
            f'<ChartEmbed chartId="{confusion_matrix_chart_id}" title="Matrice de Confusion" />',
            "",
        ]

    if roc_chart_id:
        lines += [
            "### Courbe ROC",
            "",
            f'<ChartEmbed chartId="{roc_chart_id}" title="Courbe ROC" />',
            "",
        ]

    if has_charts:
        lines += ["---", ""]

    # ── Chargement du modele ──────────────────────────────────────────────────
    lines += [
        "## Utilisation du Modele",
        "",
        "```python",
        "import joblib",
        "",
        f"# Charger le pipeline complet",
        f'artefact = joblib.load("models/{model_name}_YYYYMMDD_v1.pkl")',
        'pipeline = artefact["pipeline"]',
        "",
        "# Predire sur de nouvelles donnees",
        "predictions = pipeline.predict(X_new)",
        "",
        "# Probabilites (si classification)",
        "if hasattr(pipeline, 'predict_proba'):",
        "    probas = pipeline.predict_proba(X_new)",
        "```",
        "",
        "---",
        "",
    ]

    # ── Limitations ───────────────────────────────────────────────────────────
    lines += [
        "## Limitations Connues",
        "",
        "- Ce modele n'est pas adapte aux series temporelles avec dependances temporelles.",
        "- Les performances peuvent degrader sur des distributions tres differentes du jeu d'entrainement.",
        "- Pas de deep learning — pour les donnees non-structurees (images, texte), utiliser un Skill specialise.",
        f"- Entraine sur {n_rows} lignes — a re-entrainer si le volume de donnees augmente significativement.",
        "",
        "_Model Card generee automatiquement par AI DATA SKILL SYSTEM_",
        "",
    ]

    # ── Ecrire le fichier ─────────────────────────────────────────────────────
    content = "\n".join(lines)
    path    = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    logger.info("[Evaluator] Model Card MDX : %s (%d lignes)", path.name, len(lines))
    return str(path), content