"""
backend/skills/visualization_skill/scripts/logic.py
Pipeline principal du Visualization Skill — version intelligente v2.

14 etapes : classification → KPIs → plan Gemini/local
→ graphiques → commentaires → export → Directus → rapport MDX complet.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from schemas.visualization import ChartResult, VisualizationRequest, VisualizationResponse
from skills.visualization_skill.core.dashboard_builder import (
    analyser_et_planifier,
    build_intelligent_charts,
    get_gemini_chart_comment,
    get_gemini_eda_summary,
)
from skills.visualization_skill.core.eda import compute_correlation_matrix
from skills.visualization_skill.core.exporter import (
    export_all_charts,
    generate_mdx_report,
    serialize_chart_json,
)
from skills.visualization_skill.scripts.helpers import build_chart_stats_summary
from src.utils.directus_client import push_chart, push_report_mdx

logger = logging.getLogger(__name__)


async def run_visualization_pipeline(
    request: VisualizationRequest,
) -> VisualizationResponse:
    """
    Pipeline intelligent de visualisation en 14 etapes.

    Etapes :
    1.  Charger le dataset
    2.  Classifier colonnes + calculer KPIs + planifier graphiques (Gemini/local)
    3.  Construire les graphiques Plotly
    4.  Calculer la matrice de correlation
    5.  Generer commentaires Gemini par graphique
    6.  Generer resume executif Gemini
    7.  Exporter graphiques (HTML + PNG)
    8.  Serialiser + pousser chaque graphique vers Directus
    9.  Generer le rapport MDX complet
    10. Pousser le rapport MDX vers Directus
    11. Retourner VisualizationResponse

    Args:
        request: VisualizationRequest valide.

    Returns:
        VisualizationResponse avec chart_ids, report_mdx_id, KPIs.
    """
    t_start = time.monotonic()
    session_id = request.session_id
    errors: List[str] = []
    viz_log: List[Dict[str, Any]] = []

    def _log(etape: str, **kwargs: Any) -> None:
        viz_log.append({"etape": etape, **kwargs})

    # ── Etape 1 : Charger le dataset ──────────────────────────────────────────
    dataset_path = Path(request.dataset_path)
    if not dataset_path.exists():
        return VisualizationResponse(
            session_id=session_id,
            status="error",
            errors=[f"Fichier introuvable : {request.dataset_path}"],
            error_message=f"Fichier introuvable : {request.dataset_path}",
        )

    try:
        t0 = time.monotonic()
        df = _load_dataset(dataset_path)

        if request.columns_to_include:
            valid_cols = [c for c in request.columns_to_include if c in df.columns]
            if valid_cols:
                df = df[valid_cols]

        logger.info(
            "[Viz] Dataset charge : %s (%d lignes x %d cols)",
            dataset_path.name, len(df), df.shape[1],
        )
        _log("load_dataset", n_rows=len(df), n_cols=df.shape[1],
             duration_ms=round((time.monotonic() - t0) * 1000, 1))
    except Exception as exc:
        msg = f"Erreur chargement : {exc}"
        logger.error("[Viz] %s", msg)
        return VisualizationResponse(
            session_id=session_id,
            status="error",
            errors=[msg],
            error_message=msg,
        )


    # ── Chemins de sortie calcules une seule fois apres chargement ────────────
    stem = dataset_path.stem
    _parts = list(dataset_path.parts)
    _dataset_group = None
    try:
        _idx = _parts.index("processed")
        _candidate = _parts[_idx + 1]
        if _candidate != stem:
            _dataset_group = _candidate
    except (ValueError, IndexError):
        pass

    if _dataset_group:
        chart_output_dir = f"outputs/charts/{_dataset_group}/{stem}"
        mdx_output = (
            f"outputs/rapport_eda/{_dataset_group}/{stem}/"
            f"eda_report_{stem}.md"
        )
    else:
        chart_output_dir = f"outputs/charts/{stem}"
        mdx_output = f"outputs/rapport_eda/{stem}/eda_report_{stem}.md"

    logger.info("[Viz] Sorties : charts=%s", chart_output_dir)

    # ── Etape 2 : Analyser + Planifier ───────────────────────────────────────
    t0 = time.monotonic()
    use_gemini = request.gemini_comments
    try:
        analyse = analyser_et_planifier(
            df, use_gemini=use_gemini, question=request.question
        )
        colonnes             = analyse["colonnes"]
        plan_graphiques      = analyse["plan_graphiques"]
        kpis_data            = analyse["kpis_data"]
        source_plan          = analyse["source"]
        mappings_id_detected = analyse.get("mappings_id", {})
    except Exception as exc:
        logger.error("[Viz] analyser_et_planifier echoue : %s", exc)
        colonnes        = {"entites": [], "mesures": [], "temporelles": [], "exclues": []}
        plan_graphiques = []
        kpis_data       = {"kpis_principaux": [], "distributions": {}, "stats_mesures": {}, "evolution": {}}
        source_plan          = "error"
        mappings_id_detected = {}
        errors.append(f"Analyse echouee : {exc}")

    _log("analyser_et_planifier",
         n_graphiques=len(plan_graphiques), source=source_plan,
         duration_ms=round((time.monotonic() - t0) * 1000, 1))
    logger.info(
        "[Viz] Plan : %d graphiques (%s), %d KPIs",
        len(plan_graphiques), source_plan,
        len(kpis_data.get("kpis_principaux", [])),
    )

    # ── Etape 3 : Construire les graphiques ───────────────────────────────────
    t0 = time.monotonic()
    try:
        charts_list = build_intelligent_charts(df, plan_graphiques, mappings_id=mappings_id_detected)
    except Exception as exc:
        charts_list = []
        errors.append(f"Generation graphiques echouee : {exc}")
        logger.error("[Viz] build_intelligent_charts echoue : %s", exc)
    _log("build_charts", nb=len(charts_list),
         duration_ms=round((time.monotonic() - t0) * 1000, 1))

    # ── Etape 4 : Matrice de correlation ─────────────────────────────────────
    t0 = time.monotonic()
    high_corr_pairs = []
    try:
        corr_matrix, high_corr_pairs = compute_correlation_matrix(df)
    except Exception as exc:
        logger.debug("[Viz] Correlation echouee : %s", exc)
    _log("correlation", n_pairs=len(high_corr_pairs),
         duration_ms=round((time.monotonic() - t0) * 1000, 1))

    # ── Etape 5 : Commentaires Gemini par graphique ───────────────────────────
    gemini_comments: Dict[str, str] = {}
    if request.gemini_comments and charts_list:
        t0 = time.monotonic()
        for chart in charts_list:
            title = chart.get("title", "")
            try:
                stats_str = build_chart_stats_summary(
                    chart["figure"], df, chart.get("columns_involved", [])
                )
                comment = get_gemini_chart_comment(title, stats_str)
                if comment:
                    gemini_comments[title] = comment
            except Exception as exc:
                logger.debug("[Viz] Commentaire '%s' echoue : %s", title, exc)
        _log("gemini_comments", nb=len(gemini_comments),
             duration_ms=round((time.monotonic() - t0) * 1000, 1))

    # ── Etape 6 : Resume executif Gemini ──────────────────────────────────────
    gemini_summary: List[str] = []
    if request.gemini_comments:
        t0 = time.monotonic()
        try:
            gemini_summary = get_gemini_eda_summary(kpis_data, colonnes, source_plan)
        except Exception as exc:
            logger.debug("[Viz] Resume Gemini echoue : %s", exc)
        _log("gemini_summary", nb=len(gemini_summary),
             duration_ms=round((time.monotonic() - t0) * 1000, 1))

    # ── Etape 7 : Export HTML + PNG ───────────────────────────────────────────
    charts_paths: Dict[str, Any] = {}
    t0 = time.monotonic()
    try:
        charts_paths = export_all_charts(
            charts_list,
            chart_output_dir,
            formats=tuple(request.export_formats),
        )
    except Exception as exc:
        errors.append(f"Export echoue : {exc}")
        logger.warning("[Viz] export_all_charts echoue : %s", exc)
    _log("export_charts", nb=len(charts_paths),
         duration_ms=round((time.monotonic() - t0) * 1000, 1))

    # ── Etape 8 : Push Directus — graphiques ─────────────────────────────────
    chart_results: List[ChartResult] = []
    chart_ids_by_title: Dict[str, str] = {}
    t0 = time.monotonic()

    for chart in charts_list:
        title            = chart.get("title", "")
        chart_type       = chart.get("chart_type", "chart")
        columns_involved = chart.get("columns_involved", [])

        try:
            plotly_json = serialize_chart_json(chart["figure"])
            chart_id = await push_chart(
                session_id=session_id,
                title=title,
                chart_type=chart_type,
                plotly_json=plotly_json,
            )
        except Exception as exc:
            chart_id = ""
            errors.append(f"Push chart '{title}' echoue : {exc}")
            logger.warning("[Viz] push_chart '%s' echoue : %s", title, exc)

        if chart_id:
            chart_ids_by_title[title] = chart_id

        chart_results.append(ChartResult(
            chart_id=chart_id,
            title=title,
            chart_type=chart_type,
            columns_involved=columns_involved,
        ))

    _log("push_charts", nb=len(chart_ids_by_title),
         duration_ms=round((time.monotonic() - t0) * 1000, 1))
    logger.info(
        "[Viz] %d/%d charts → Directus",
        len(chart_ids_by_title), len(charts_list),
    )

    # ── Etapes 9-10 : Rapport MDX → Directus ─────────────────────────────────
    eda_report_path: Optional[str] = None
    report_mdx_id: Optional[str] = None

    if request.generate_report:
        stem = dataset_path.stem

        # Extraire la hierarchie depuis le chemin ETL
        # data/processed/Donnees_Universitaires/mapping_tables/xxx.csv
        # → dataset_group = "Donnees_Universitaires"
        parts = dataset_path.parts
        dataset_group = None
        try:
            idx = list(parts).index("processed")
            candidate = parts[idx + 1]
            if candidate != stem:
                dataset_group = candidate
        except (ValueError, IndexError):
            pass

        if dataset_group:
            chart_output_dir = f"outputs/charts/{dataset_group}/{stem}"
            mdx_output = (
                f"outputs/rapport_eda/{dataset_group}/{stem}/"
                f"eda_report_{stem}.md"
            )
        else:
            chart_output_dir = f"outputs/charts/{stem}"
            mdx_output = f"outputs/rapport_eda/{stem}/eda_report_{stem}.md"
        t0 = time.monotonic()

        # Construire les stats pour le rapport
        numeric_stats: Dict[str, Any] = {}
        for col in colonnes.get("mesures", []):
            v = df[col].dropna()
            if len(v) < 2:
                continue
            numeric_stats[col] = {
                "mean":      round(float(v.mean()), 4),
                "std":       round(float(v.std()), 4),
                "min":       round(float(v.min()), 4),
                "q50":       round(float(v.median()), 4),
                "max":       round(float(v.max()), 4),
                "skewness":  round(float(v.skew()), 4),
                "null_count": int(df[col].isna().sum()),
                "null_pct":  round(df[col].isna().mean() * 100, 2),
            }

        categorical_stats: Dict[str, Any] = {}
        for col in colonnes.get("entites", []):
            n_unique   = int(df[col].nunique())
            null_count = int(df[col].isna().sum())
            null_pct   = round(df[col].isna().mean() * 100, 2)
            vc         = df[col].value_counts().head(5)
            categorical_stats[col] = {
                "n_unique":   n_unique,
                "null_count": null_count,
                "null_pct":   null_pct,
                "top_values": [
                    {"value": str(k), "count": int(v),
                     "pct": round(v / len(df) * 100, 2)}
                    for k, v in vc.items()
                ],
            }

        try:
            eda_report_path, content_mdx = generate_mdx_report(
                stats={
                    "numeric_stats":     numeric_stats,
                    "categorical_stats": categorical_stats,
                },
                charts_list=charts_list,
                gemini_comments=gemini_comments,
                gemini_summary=gemini_summary,
                output_path=mdx_output,
                chart_ids_by_title=chart_ids_by_title,
                target_analysis=None,
                high_corr_pairs=high_corr_pairs,
                dataset_info={
                    "n_rows":       len(df),
                    "n_cols":       df.shape[1],
                    "dataset_name": stem,
                },
                kpis_data=kpis_data,
            )
        except Exception as exc:
            errors.append(f"Generation MDX echouee : {exc}")
            logger.error("[Viz] generate_mdx_report echoue : %s", exc)
            content_mdx = ""

        _log("generate_mdx", path=eda_report_path,
             duration_ms=round((time.monotonic() - t0) * 1000, 1))

        if content_mdx:
            t0 = time.monotonic()
            try:
                report_mdx_id = await push_report_mdx(
                    session_id=session_id,
                    report_type="eda",
                    title=f"Rapport EDA — {stem}",
                    content_mdx=content_mdx,
                )
            except Exception as exc:
                errors.append(f"Push MDX echoue : {exc}")
                logger.warning("[Viz] push_report_mdx echoue : %s", exc)
            _log("push_mdx", report_mdx_id=report_mdx_id,
                 duration_ms=round((time.monotonic() - t0) * 1000, 1))

    # ── Etape 11 : Retourner ──────────────────────────────────────────────────
    total_ms = round((time.monotonic() - t_start) * 1000, 1)
    logger.info(
        "[Viz] Pipeline termine en %.1fms — %d charts — source=%s",
        total_ms, len(chart_results), source_plan,
    )

    stats_response = dict(kpis_data)
    stats_response["source_plan"] = source_plan
    stats_response["colonnes"] = {
        k: v for k, v in colonnes.items()
        if k in ("entites", "mesures", "temporelles")
    }

    return VisualizationResponse(
        session_id=session_id,
        status="success",
        charts=chart_results,
        stats=stats_response,
        eda_report_path=eda_report_path,
        report_mdx_id=report_mdx_id,
        charts_paths=charts_paths,
        gemini_comments=gemini_comments,
        errors=errors,
    )


def _load_dataset(path: Path) -> pd.DataFrame:
    """Charge un dataset depuis CSV, Excel, JSON ou Parquet."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, low_memory=False)
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if suffix == ".json":
        return pd.read_json(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    raise ValueError(f"Format non supporte : {suffix}")