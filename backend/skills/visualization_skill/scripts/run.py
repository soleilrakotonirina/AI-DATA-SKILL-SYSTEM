"""
skills/visualization_skill/scripts/run.py  v4.0
Orchestrateur synchrone Visualization.

Nouveautés v4 :
- create_combined_dashboard : dashboard HTML unique avec tous les graphiques
- Sortie toujours dans outputs/viz/{stem}/ (accessible par file_server)
- PNG activé par défaut
- IDs → libellés depuis dim_*.csv du Star Schema ETL
- Fix get_gemini_eda_summary

Utilise les fonctions RÉELLES du projet (pas de mock) pour :
- exporter.py   : export_all_charts, generate_mdx_report
- eda.py        : compute_descriptive_stats, compute_correlation_matrix, analyze_target_variable
- dashboard_builder.py : analyser_et_planifier, build_intelligent_charts,
                         get_gemini_chart_comment, get_gemini_eda_summary
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd

from skills.visualization_skill.core.dashboard_builder import (
    analyser_et_planifier,
    build_intelligent_charts,
    get_gemini_chart_comment,
    get_gemini_eda_summary,
)
from skills.visualization_skill.core.eda import (
    analyze_target_variable,
    compute_correlation_matrix,
    compute_descriptive_stats,
)
from skills.visualization_skill.core.exporter import (
    export_all_charts,
    generate_mdx_report,
)

logger = logging.getLogger(__name__)

_SUPPORTED = {".csv", ".xlsx", ".xls", ".xlsm", ".json", ".parquet"}
_BACKEND_ROOT = Path(__file__).resolve().parents[3]


# ─────────────────────────────────────────────────────────────────────────────
# Chargement
# ─────────────────────────────────────────────────────────────────────────────

def _load_dataset(input_path: str) -> Tuple[pd.DataFrame, str]:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {input_path}")

    ext = path.suffix.lower()
    if ext not in _SUPPORTED:
        raise ValueError(f"Format non supporté : '{ext}'")

    if ext in {".xlsx", ".xls", ".xlsm"}:
        df = pd.read_excel(path, sheet_name=0)
    elif ext == ".csv":
        for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
            try:
                df = pd.read_csv(path, encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            df = pd.read_csv(path, encoding="latin-1", errors="replace")
    elif ext == ".json":
        df = pd.read_json(path)
    elif ext == ".parquet":
        df = pd.read_parquet(path)
    else:
        raise ValueError(f"Format non géré : {ext}")

    return df, _clean_stem(path.stem)


# ─────────────────────────────────────────────────────────────────────────────
# Utilitaires
# ─────────────────────────────────────────────────────────────────────────────

def _clean_stem(stem: str) -> str:
    if "_" in stem:
        parts = stem.split("_", 1)
        candidate = parts[0].replace("-", "")
        if len(candidate) >= 16 and all(c in "0123456789abcdefABCDEF" for c in candidate):
            return parts[1] if len(parts) > 1 else stem
    return stem


def _resolve_output_dir(input_path: str, stem: str) -> Path:
    """Toujours outputs/viz/{stem}/ à la racine backend."""
    return _BACKEND_ROOT / "outputs" / "viz" / stem


def _adapter_plan_par_question(
    plan: List[Dict[str, Any]],
    question: str,
    col_names: List[str],
) -> List[Dict[str, Any]]:
    question_lower = question.lower()
    prioritized = []
    normal = []
    for item in plan:
        cols = item.get("columns", []) or item.get("cols", [])
        if any(c.lower() in question_lower for c in cols if isinstance(c, str)):
            prioritized.append(item)
        else:
            normal.append(item)
    return prioritized + normal


def _compute_chart_stats(
    df: pd.DataFrame,
    charts_list: List[Dict[str, Any]],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for chart in charts_list:
        title = chart.get("title", "")
        ctype = chart.get("chart_type", "")
        cols  = chart.get("columns_involved", []) or chart.get("columns", [])
        entry: Dict[str, Any] = {"type": ctype, "columns": cols}
        try:
            if ctype in ("bar", "donut", "pareto") and cols:
                col = cols[0]
                if col in df.columns:
                    vc = df[col].value_counts()
                    entry["top_valeurs"] = [
                        {"valeur": str(v), "count": int(c)}
                        for v, c in vc.head(5).items()
                    ]
                    entry["n_categories"] = int(df[col].nunique())
            elif ctype in ("boxplot", "boxplot_by_segment") and cols:
                col = cols[0]
                if col in df.columns:
                    s = df[col].dropna()
                    if len(s) and pd.api.types.is_numeric_dtype(s):
                        entry["par_groupe"] = {
                            "min":    round(float(s.min()), 2),
                            "q1":     round(float(s.quantile(0.25)), 2),
                            "median": round(float(s.median()), 2),
                            "q3":     round(float(s.quantile(0.75)), 2),
                            "max":    round(float(s.max()), 2),
                        }
            elif ctype == "histogram" and cols:
                col = cols[0]
                if col in df.columns:
                    s = df[col].dropna()
                    if len(s) and pd.api.types.is_numeric_dtype(s):
                        entry["moyenne"] = round(float(s.mean()), 2)
                        entry["mediane"] = round(float(s.median()), 2)
                        entry["std"]     = round(float(s.std()), 2) if len(s) > 1 else 0
            elif ctype == "correlation_heatmap":
                numeric_cols = [
                    c for c in cols
                    if c in df.columns and pd.api.types.is_numeric_dtype(df[c])
                ]
                if len(numeric_cols) >= 2:
                    corr = df[numeric_cols].corr(numeric_only=True)
                    pairs = []
                    for i, col_a in enumerate(corr.columns):
                        for col_b in corr.columns[i + 1:]:
                            r = corr.loc[col_a, col_b]
                            if not pd.isna(r):
                                pairs.append({
                                    "col_a": col_a,
                                    "col_b": col_b,
                                    "correlation": round(float(r), 4),
                                })
                    pairs.sort(key=lambda p: abs(p["correlation"]), reverse=True)
                    entry["top_correlations"] = pairs[:5]
        except Exception as exc:
            entry["_erreur"] = str(exc)
        result[title] = entry
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Substitution IDs → libellés depuis tables de dimensions
# ─────────────────────────────────────────────────────────────────────────────

def _load_dimension_mappings(input_path: str) -> Dict[str, Dict[Any, str]]:
    mappings: Dict[str, Dict[Any, str]] = {}
    p = Path(input_path)
    search_dirs = [p.parent]
    for parent in p.parents[:6]:
        candidate = parent / "mapping_tables"
        if candidate.exists():
            search_dirs.append(candidate)
            break

    for dim_dir in search_dirs:
        if not dim_dir.exists():
            continue
        for dim_file in sorted(dim_dir.glob("*dim_*.csv")):
            try:
                dim_df = pd.read_csv(dim_file)
                if dim_df.empty or len(dim_df.columns) < 2:
                    continue
                id_cols    = [c for c in dim_df.columns if c.lower().startswith("id_") or c.lower().endswith("_id")]
                label_cols = [c for c in dim_df.columns if c not in id_cols]
                if not id_cols or not label_cols:
                    continue
                id_col    = id_cols[0]
                label_col = label_cols[0]
                mapping: Dict[Any, str] = {}
                for _, row in dim_df.iterrows():
                    try:
                        key = row[id_col]
                        val = str(row[label_col])
                        mapping[key] = val
                        try:
                            mapping[int(key)]   = val
                            mapping[float(key)] = val
                        except (ValueError, TypeError):
                            pass
                    except Exception:
                        continue
                if mapping:
                    mappings[id_col] = mapping
                    logger.info("[VIZ labels] %s → %s : %d valeurs", id_col, label_col, len(dim_df))
            except Exception as exc:
                logger.debug("[VIZ labels] Erreur %s : %s", dim_file.name, exc)
    return mappings


def _apply_dim_labels(
    df: pd.DataFrame,
    dim_mappings: Dict[str, Dict[Any, str]],
) -> pd.DataFrame:
    df = df.copy()
    for id_col, mapping in dim_mappings.items():
        if id_col not in df.columns:
            continue
        try:
            df[id_col] = df[id_col].map(
                lambda v, m=mapping: m.get(v, m.get(int(v) if pd.notna(v) else v, v))
            )
            new_name = id_col
            if new_name.startswith("id_"):
                new_name = new_name[3:]
            elif new_name.endswith("_id"):
                new_name = new_name[:-3]
            if new_name and new_name not in df.columns and new_name != id_col:
                df.rename(columns={id_col: new_name}, inplace=True)
                logger.info("[VIZ labels] %s → %s", id_col, new_name)
        except Exception as exc:
            logger.warning("[VIZ labels] Erreur sur %s : %s", id_col, exc)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard HTML combiné
# ─────────────────────────────────────────────────────────────────────────────




def create_combined_dashboard(charts_paths, dataset_name, kpis, output_dir):
    from pathlib import Path as _P
    base_dir = _P(output_dir)
    dashboard_path = base_dir / "dashboard.html"

    # Embarquer le contenu HTML de chaque graphique directement (pas iframe)
    chart_sections = ""
    for title, paths in charts_paths.items():
        html_file = paths.get("html", "")
        if not html_file or not _P(html_file).exists():
            continue
        chart_content = _P(html_file).read_text(encoding="utf-8")
        # Extraire seulement le div Plotly (sans html/head/body)
        import re
        body_match = re.search(r"<body[^>]*>(.*?)</body>", chart_content, re.DOTALL)
        chart_body = body_match.group(1).strip() if body_match else chart_content
        chart_sections += f"""
        <div class="chart-card">
            <div class="chart-head"><h2>{title}</h2></div>
            <div class="chart-body">{chart_body}</div>
        </div>"""

    # KPIs
    kpi_cards = ""
    for k in (kpis or [])[:6]:
        val = k.get("valeur", "")
        kpi_cards += f'<div class="kpi-card"><span>{k.get("icone","")}</span><small>{k.get("label","")}</small><strong>{val}</strong></div>'

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Dashboard — {dataset_name}</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body{{font-family:system-ui;background:#f6f7f9;padding:20px}}
        .kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:24px}}
        .kpi-card{{background:#fff;border-radius:8px;padding:14px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.08)}}
        .kpi-card span{{font-size:1.4rem;display:block}}
        .kpi-card small{{color:#636b74;font-size:.75rem}}
        .kpi-card strong{{font-size:1.2rem;color:#0067b8;display:block;margin-top:4px}}
        .charts-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(500px,1fr));gap:16px}}
        .chart-card{{background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)}}
        .chart-head{{padding:10px 14px;border-bottom:1px solid #d9dde3}}
        .chart-head h2{{font-size:.9rem;color:#171717}}
        .chart-body{{padding:8px}}
    </style>
</head>
<body>
    <header style="text-align:center;padding:20px 0;border-bottom:1px solid #d9dde3;margin-bottom:20px">
        <h1 style="color:#0067b8">📊 {dataset_name}</h1>
    </header>
    <div class="kpi-grid">{kpi_cards}</div>
    <div class="charts-grid">{chart_sections}</div>
</body>
</html>"""

    dashboard_path.write_text(html, encoding="utf-8")
    return str(dashboard_path)
def run_viz_pipeline(
    input_path: str,
    output_dir: Optional[str] = None,
    target_column: Optional[str] = None,
    export_png: bool = True,
    question: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Pipeline EDA complet — synchrone.

    v4 :
    - Dashboard HTML unique (dashboard.html) avec tous les graphiques embarqués
    - Sortie dans outputs/viz/{stem}/ accessible par file_server
    - PNG activé par défaut
    - IDs → libellés depuis dim_*.csv du Star Schema ETL
    """
    errors: List[str] = []
    t_start = time.monotonic()

    # ── 1. Chargement ──────────────────────────────────────────────────────────
    try:
        df, stem = _load_dataset(input_path)
    except Exception as exc:
        return {
            "status":        "error",
            "error_message": str(exc),
            "input_path":    input_path,
            "errors":        [str(exc)],
        }

    n_rows, n_cols = df.shape
    logger.info("[VIZ] Dataset : %s — %d × %d", stem, n_rows, n_cols)

    # ── 1b. IDs → libellés depuis tables de dimensions ─────────────────────────
    labels_applied: List[str] = []
    try:
        dim_mappings = _load_dimension_mappings(input_path)
        if dim_mappings:
            df = _apply_dim_labels(df, dim_mappings)
            labels_applied = list(dim_mappings.keys())
            n_rows, n_cols = df.shape
    except Exception as exc:
        errors.append(f"Substitution IDs→libellés : {exc}")

    # ── 2. Répertoires de sortie ───────────────────────────────────────────────
    base_dir    = Path(output_dir) if output_dir else _resolve_output_dir(input_path, stem)
    charts_dir  = base_dir / "charts"
    reports_dir = base_dir / "rapports"
    for d in (charts_dir, reports_dir):
        d.mkdir(parents=True, exist_ok=True)

    logger.info("[VIZ] Sortie → %s", base_dir)

    # ── 3. Analyse et planification ────────────────────────────────────────────
    try:
        analyse         = analyser_et_planifier(df, question=question)
        colonnes        = analyse.get("colonnes", {})
        plan_graphiques = analyse.get("plan_graphiques", [])
        kpis_data       = analyse.get("kpis_data", {})
        mappings_id     = analyse.get("mappings_id", {})
    except Exception as exc:
        errors.append(f"Analyse : {exc}")
        colonnes, plan_graphiques, kpis_data, mappings_id = {}, [], {}, {}

    if question and plan_graphiques:
        try:
            plan_graphiques = _adapter_plan_par_question(
                plan_graphiques, question, df.columns.tolist()
            )
        except Exception as exc:
            errors.append(f"Adaptation plan : {exc}")

    # ── 4. Statistiques EDA ───────────────────────────────────────────────────
    try:
        stats = compute_descriptive_stats(df)
    except Exception as exc:
        errors.append(f"Statistiques : {exc}")
        stats = {"numeric_stats": {}, "categorical_stats": {}}

    high_corr_pairs: List[Dict[str, Any]] = []
    try:
        _, high_corr_pairs = compute_correlation_matrix(df)
    except Exception as exc:
        errors.append(f"Corrélations : {exc}")

    target_analysis = None
    if target_column and target_column in df.columns:
        try:
            target_analysis = analyze_target_variable(df, target_column)
        except Exception as exc:
            errors.append(f"Analyse cible '{target_column}' : {exc}")

    # ── 5. Construction graphiques Plotly ─────────────────────────────────────
    charts_list: List[Dict[str, Any]] = []
    try:
        charts_list = build_intelligent_charts(df, plan_graphiques, mappings_id)
    except Exception as exc:
        errors.append(f"Construction graphiques : {exc}")
    logger.info("[VIZ] %d graphiques construits", len(charts_list))

    # ── 5b. Commentaires Gemini ────────────────────────────────────────────────
    gemini_comments: Dict[str, str] = {}
    for chart in charts_list:
        title = chart.get("title", "")
        try:
            comment = get_gemini_chart_comment(
                chart_title=title,
                chart_type=chart.get("chart_type", ""),
                columns=chart.get("columns_involved", []),
                df=df,
            )
            if comment:
                gemini_comments[title] = comment
        except Exception:
            pass

    # ── 5c. Résumé Gemini ─────────────────────────────────────────────────────
    gemini_summary: List[str] = []
    try:
        gemini_summary = get_gemini_eda_summary(
            stats=stats,
            kpis_data=kpis_data,
            high_corr_pairs=high_corr_pairs,
        )
    except TypeError:
        try:
            gemini_summary = get_gemini_eda_summary(stats, kpis_data, high_corr_pairs)
        except Exception as exc2:
            errors.append(f"Résumé Gemini : {exc2}")
    except Exception as exc:
        errors.append(f"Résumé Gemini : {exc}")

    # ── 5d. Chart stats ────────────────────────────────────────────────────────
    chart_stats: Dict[str, Any] = {}
    try:
        chart_stats = _compute_chart_stats(df, charts_list)
    except Exception as exc:
        errors.append(f"Chart stats : {exc}")

    # ── 6. Export graphiques HTML + PNG ───────────────────────────────────────
    if export_png:
        try:
            import kaleido  # noqa: F401
            export_formats: tuple = ("html", "png")
        except ImportError:
            errors.append("kaleido non installé — PNG désactivé")
            export_formats = ("html",)
    else:
        export_formats = ("html",)

    charts_paths: Dict[str, Dict[str, str]] = {}
    try:
        charts_paths = export_all_charts(
            charts_list, str(charts_dir), formats=export_formats
        )
        logger.info("[VIZ] %d graphiques exportés → %s", len(charts_paths), export_formats)
    except Exception as exc:
        errors.append(f"Export graphiques : {exc}")

    # ── 6b. Fallback PNG direct si export_all_charts ne génère pas de PNG ─────
    if export_png and charts_paths:
        has_png = any("png" in paths for paths in charts_paths.values())
        if not has_png:
            logger.info("[VIZ] Génération PNG directe (fallback kaleido 1.x)")
            for chart in charts_list:
                title = chart.get("title", "")
                fig   = chart.get("fig")
                if fig is None:
                    continue
                html_path = charts_paths.get(title, {}).get("html", "")
                if not html_path:
                    continue
                png_path = html_path.replace(".html", ".png")
                try:
                    # kaleido 1.x — sans paramètre engine (déprécié)
                    fig.write_image(png_path, width=1000, height=500, scale=1.5)
                    charts_paths[title]["png"] = png_path
                    logger.info("[VIZ] PNG OK : %s", Path(png_path).name)
                except Exception as exc:
                    errors.append(f"PNG '{title}' : {exc}")

    # ── 6c. Dashboard HTML combiné ────────────────────────────────────────────
    dashboard_path: Optional[str] = None
    try:
        dashboard_path = create_combined_dashboard(
            charts_paths=charts_paths,
            dataset_name=stem,
            kpis=kpis_data.get("kpis_principaux", []),
            output_dir=str(base_dir),
        )
    except Exception as exc:
        errors.append(f"Dashboard combiné : {exc}")

    # ── 7. Rapport Markdown ────────────────────────────────────────────────────
    report_path: Optional[str] = None
    try:
        report_file = reports_dir / f"viz_report_{stem}.md"
        rp, _ = generate_mdx_report(
            stats=stats,
            charts_list=charts_list,
            gemini_comments=gemini_comments,
            gemini_summary=gemini_summary,
            output_path=str(report_file),
            target_analysis=target_analysis,
            high_corr_pairs=high_corr_pairs or None,
            dataset_info={"dataset_name": stem, "n_rows": n_rows, "n_cols": n_cols},
            kpis_data=kpis_data,
        )
        report_path = str(rp) if rp else None
    except Exception as exc:
        errors.append(f"Rapport Markdown : {exc}")

    duration_s = round(time.monotonic() - t_start, 2)

    chart_type_counts: Dict[str, int] = {}
    for chart in charts_list:
        ct = chart.get("chart_type", "chart")
        chart_type_counts[ct] = chart_type_counts.get(ct, 0) + 1

    return {
        "status":            "success" if not errors else "partial",
        "dataset_name":      stem,
        "n_rows":            n_rows,
        "n_cols":            n_cols,
        "n_charts":          len(charts_list),
        "labels_applied":    labels_applied,
        "question":          question,
        "charts_dir":        str(charts_dir),
        "dashboard_path":    dashboard_path,
        "report_path":       report_path,
        "charts_paths":      charts_paths,
        "chart_type_counts": chart_type_counts,
        "chart_stats":       chart_stats,
        "kpis":              kpis_data.get("kpis_principaux", []),
        "high_corr_pairs":   high_corr_pairs,
        "colonnes":          colonnes,
        "errors":            errors,
        "duration_s":        duration_s,
    }