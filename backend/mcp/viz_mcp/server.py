"""
mcp/viz_mcp/server.py — version finale
7 tools + dashboard HTML combiné + liens cliquables
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

_upload_env = os.environ.get("UPLOAD_DIR", "")
if _upload_env:
    UPLOAD_DIR = Path(_upload_env)
    if not UPLOAD_DIR.is_absolute():
        UPLOAD_DIR = (ROOT / UPLOAD_DIR).resolve()
else:
    UPLOAD_DIR = ROOT / "data" / "uploads"

FILE_SERVER_URL = os.environ.get("FILE_SERVER_URL", "http://localhost:8090")

from skills.visualization_skill.scripts.run import run_viz_pipeline  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s : %(message)s",
)
logger = logging.getLogger("viz_mcp")

mcp = FastMCP(name="visualization-skill")

_EXTENSIONS = {".csv", ".xlsx", ".xls", ".xlsm", ".json", ".parquet"}


# ─────────────────────────────────────────────────────────────────────────────
# Utilitaires partagés
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_download_links(dataset_name: str) -> str:
    """
    Retourne le lien dashboard + images PNG inline + graphiques HTML.
    Les PNG s'affichent directement dans Open WebUI via syntaxe ![](url).
    """
    import httpx

    for url in [
        f"{FILE_SERVER_URL}/results/viz/{dataset_name}",
        f"{FILE_SERVER_URL}/results/{dataset_name}",
    ]:
        try:
            r = httpx.get(url, timeout=5)
            data = r.json()
            if data.get("total_files", 0) == 0:
                continue

            lines = [f"\n## 📊 {dataset_name}\n"]

            # Dashboard principal
            dashboard_files = data.get("dashboard", [])
            if dashboard_files:
                for f in dashboard_files:
                    lines.append(
                        f"### 🎯 Dashboard complet\n"
                        f"**[➡ Ouvrir dashboard.html]({f['download_url']})**"
                        f"  — {f['size_kb']} KB\n"
                    )

            # PNG inline — s'affichent directement dans Open WebUI
            all_charts = data.get("charts", [])
            png_charts  = [f for f in all_charts if f["name"].endswith(".png")]
            html_charts = [f for f in all_charts if f["name"].endswith(".html")]

            if png_charts:
                lines.append("### Graphiques\n")
                for f in png_charts:
                    title = (
                        f["name"]
                        .replace(".png", "")
                        .replace("_", " ")
                        .title()
                        .strip()
                    )
                    # Syntaxe image inline — Open WebUI affiche l'image directement
                    lines.append(f"![{title}]({f['download_url']})")
                    lines.append("")

            elif html_charts:
                # Fallback si pas de PNG
                lines.append(f"### Graphiques ({len(html_charts)})\n")
                for i, f in enumerate(html_charts, 1):
                    lines.append(
                        f"{i}. [{f['name']}]({f['download_url']}) — {f['size_kb']} KB"
                    )

            # Rapport EDA
            if data.get("rapports"):
                lines.append("\n### Rapport EDA")
                for f in data["rapports"]:
                    lines.append(f"- [{f['name']}]({f['download_url']}) — {f['size_kb']} KB")

            # Hint pour affichage inline
            lines.append(
                f"\n---\n"
                f"💡 **Afficher le dashboard directement ici** → "
                f"appelle `show_dashboard(dataset_name=\"{dataset_name}\")`"
            )

            return "\n".join(lines)

        except Exception as exc:
            return (
                f"\n⚠️ File server inaccessible : {exc}\n"
                f"Lance : `uv run --env-file .env python file_server.py`"
            )

    return "\n⚠️ Aucun fichier trouvé pour ce dataset."


def _build_summary(result: dict) -> str:
    """JSON résumé compact pour le LLM."""
    return json.dumps({
        "dataset_name":      result.get("dataset_name"),
        "status":            result.get("status"),
        "n_rows":            result.get("n_rows"),
        "n_cols":            result.get("n_cols"),
        "n_charts":          result.get("n_charts"),
        "chart_type_counts": result.get("chart_type_counts", {}),
        "kpis":              result.get("kpis", [])[:4],
        "labels_applied":    result.get("labels_applied", []),
        "dashboard_path":    result.get("dashboard_path"),
        "report_path":       result.get("report_path"),
        "duration_s":        result.get("duration_s"),
        "errors":            result.get("errors", []),
    }, ensure_ascii=False, default=str)



# ─────────────────────────────────────────────────────────────────────────────
# Utilitaire : convertir tableau Markdown → CSV
# ─────────────────────────────────────────────────────────────────────────────

def _md_to_csv(text: str) -> str:
    """Convertit un tableau Markdown en CSV propre si détecté."""
    import re as _re
    lines = text.strip().split("\n")
    if not lines or not lines[0].strip().startswith("|"):
        return text
    csv_lines = []
    for line in lines:
        line = line.strip()
        if _re.match(r"^\|[-| ]+\|$", line):
            continue
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line[1:-1].split("|")]
            csv_lines.append(",".join(f'"{c}"' for c in cells))
    return "\n".join(csv_lines) if csv_lines else text


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 1 — viz_auto
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def viz_auto(
    input_path: str = "",
    target_column: str = "",
    question: str = "",
    export_png: bool = True,
) -> str:
    """
    [OUTIL PRINCIPAL] Analyse un dataset et génère le dashboard EDA complet.

    Accepte un chemin de fichier OU trouve automatiquement le dernier fichier uploadé.

    Génère automatiquement :
    - Graphiques Plotly interactifs (HTML)
    - Dashboard HTML unique avec tous les graphiques
    - Rapport Markdown EDA avec KPIs et statistiques

    Retourne un résumé JSON + liens de téléchargement directs.
    Après cet outil, l'utilisateur peut télécharger le dashboard.

    Paramètres :
    - target_column : colonne cible ML à analyser séparément
    - question      : question analytique — adapte les graphiques
    - export_png    : exporter aussi en PNG
    """
    # Si input_path fourni → l'utiliser directement
    if input_path:
        resolved = Path(input_path)
        if not resolved.is_absolute():
            resolved = ROOT / input_path
        if resolved.exists():
            input_path = str(resolved)
            logger.info("[viz_auto] Fichier fourni : %s", input_path)
        else:
            logger.warning("[viz_auto] Fichier introuvable : %s", input_path)
            input_path = ""

    # Sinon → meilleur fichier disponible
    if not input_path:
        EXTENSIONS = {".csv", ".xlsx", ".xls", ".xlsm", ".json", ".parquet"}

        # Collecter TOUS les fichiers dans uploads/
        all_files = sorted(
            [f for f in UPLOAD_DIR.rglob("*")
             if f.is_file() and f.suffix.lower() in EXTENSIONS],
            key=os.path.getmtime,
            reverse=True,
        )

        # Trier : fichiers avec UUID (vrais uploads) > fichiers sans UUID
        def _n_cols(f):
            try:
                line1 = f.read_text(encoding="utf-8", errors="replace").split("\n")[0]
                return line1.count(",") + 1
            except Exception:
                return 0

        def _has_uuid(f):
            # Fichier Open WebUI original : UUID_nom.csv
            import re
            return bool(re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-", f.name))

        # Prioriser les fichiers UUID avec le plus de colonnes
        uuid_files = [f for f in all_files if _has_uuid(f)]
        other_files = [f for f in all_files if not _has_uuid(f)]

        best = None
        for candidate in uuid_files + other_files:
            n = _n_cols(candidate)
            if n >= 5:
                best = candidate
                logger.info("[viz_auto] Fichier valide : %s (%d cols)", candidate.name, n)
                break

        if not best:
            return json.dumps({
                "status":        "error",
                "error_message": "Aucun fichier valide trouvé. Upload un CSV avec au moins 5 colonnes.",
            })

        input_path = str(best)

    try:
        result = run_viz_pipeline(
            input_path=input_path,
            target_column=target_column or None,
            export_png=export_png,
            question=question or None,
        )
    except Exception as exc:
        import traceback
        logger.error("[viz_auto] EXCEPTION:\n%s", traceback.format_exc())
        return json.dumps({"status": "error", "error_message": str(exc)})

    dataset_name = result.get("dataset_name", "")
    kpis = result.get("kpis", [])[:4]
    kpi_lines = "\n".join(
        f"- {k.get('icone','')} **{k.get('label','')}** : {k.get('valeur','')}"
        for k in kpis
    )
    types_str = ", ".join(
        f"{v} {k}" for k, v in result.get("chart_type_counts", {}).items()
    )
    # ── Retourner markdown formaté — même style que le template ─────────────
    dashboard_url  = f"{FILE_SERVER_URL}/files/viz/{dataset_name}/dashboard.html"
    charts_paths   = result.get("charts_paths", {})
    chart_type_map = result.get("chart_stats", {})

    # Liste numérotée des graphiques
    chart_lines = []
    for i, (title, _) in enumerate(charts_paths.items(), 1):
        chart_lines.append(f"{i}. {title}")
    charts_section = "\n".join(chart_lines) if chart_lines else ""

    # Images PNG inline (si disponibles)
    charts_dir = ROOT / "outputs" / "viz" / dataset_name / "charts"
    png_files  = sorted(charts_dir.glob("*.png")) if charts_dir.exists() else []
    png_section = ""
    if png_files:
        png_lines = []
        for png in png_files:
            url   = f"{FILE_SERVER_URL}/files/viz/{dataset_name}/charts/{png.name}"
            title = png.stem.replace("_", " ").title()
            png_lines.append(f"![{title}]({url})")
        png_section = "\n\n" + "\n".join(png_lines)

    return (
        f"📊 **{dataset_name}**\n"
        f"{result.get('n_rows'):,} lignes · "
        f"{result.get('n_cols')} colonnes · "
        f"{result.get('n_charts')} graphiques\n\n"
        f"**Résumé des Données**\n\n"
        f"{kpi_lines}\n\n"
        f"**📈 Graphiques Disponibles**\n\n"
        f"{charts_section}"
        f"{png_section}\n\n"
        f"**Accès au Dashboard** : "
        f"🔗 [Visualisation interactive]({dashboard_url})"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 2 — run_visualization
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def run_visualization(
    input_path: str = "",
    file_content: str = "",
    filename: str = "",
    target_column: str = "",
    question: str = "",
    export_png: bool = True,
    output_dir: str = "",
) -> str:
    """
    Visualise un dataset : graphiques Plotly + dashboard + rapport EDA.

    TROIS modes d'appel :

    Mode 1 — Fichier uploadé via le chat (contenu CSV dans le message) :
      run_visualization(file_content="col1,col2\nval1,val2", filename="data.csv")

    Mode 2 — Fichier existant sur le serveur :
      run_visualization(input_path="data/raw/ventes.csv")

    Mode 3 — Dernier fichier uploadé (automatique) :
      run_visualization()

    Quand l'utilisateur uploade un fichier dans le chat :
    → Utiliser file_content + filename (le contenu est visible dans le contexte)
    → Ne jamais inventer un chemin

    Paramètres :
    - file_content  : contenu brut du fichier (CSV, JSON) — copier EXACTEMENT depuis le contexte
    - filename      : nom du fichier avec extension
    - input_path    : chemin serveur si pas de file_content
    - target_column : colonne cible ML
    - question      : question analytique
    """
    logger.info("[run_visualization] input=%s file_content=%d chars", input_path, len(file_content))

    # ── Validation file_content : rejeter si ce n'est pas du CSV/JSON ────────
    if file_content:
        stripped = file_content.strip()
        is_csv = (
            # Commence par une ligne avec des virgules → CSV
            "," in stripped.split("\n")[0]
            # Ou commence par { ou [ → JSON
            or stripped.startswith(("{", "["))
        )
        is_markdown = stripped.startswith(("#", "-", "*", ">", "✅", "📊", "##"))
        if is_markdown or not is_csv:
            logger.warning("[run_visualization] file_content ignoré (contenu non-CSV) : %s",
                           stripped[:80])
            file_content = ""

    # ── Mode 1 : file_content fourni → sauvegarder ──────────────────────────
    if file_content and not input_path:
        upload_dir = ROOT / "data" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        fname = filename or "uploaded_data.csv"
        # Convertir xlsx/parquet → csv si nécessaire
        if Path(fname).suffix.lower() in {".xlsx", ".xls", ".xlsm", ".parquet"}:
            fname = Path(fname).stem + ".csv"
        # Nettoyer le contenu (table Markdown → CSV)
        clean_content = _md_to_csv(file_content)
        save_path = upload_dir / fname
        save_path.write_text(clean_content, encoding="utf-8")
        input_path = str(save_path)
        logger.info("[run_visualization] file_content sauvegardé : %s (%d chars)", save_path, len(clean_content))

    # ── Mode 3 : rien fourni → dernier upload ───────────────────────────────
    if not input_path:
        EXTENSIONS = {".csv", ".xlsx", ".xls", ".xlsm", ".json", ".parquet"}
        upload_dir = ROOT / "data" / "uploads"
        files = sorted(
            [f for f in upload_dir.rglob("*")
             if f.is_file() and f.suffix.lower() in EXTENSIONS],
            key=os.path.getmtime, reverse=True,
        )
        if files:
            input_path = str(files[0])
            logger.info("[run_visualization] Dernier upload : %s", input_path)

    # ── Résolution du chemin ─────────────────────────────────────────────────
    path = Path(input_path)
    if not path.is_absolute():
        path = ROOT / input_path

    # Chercher dans les dossiers connus si non trouvé
    if not path.exists():
        stem_name = Path(input_path).name
        candidates = [
            ROOT / "data" / "raw"       / stem_name,
            ROOT / "data" / "uploads"   / stem_name,
            ROOT / "data" / "processed" / stem_name,
            ROOT / "data"               / stem_name,
        ]
        candidates += list((ROOT / "data" / "processed").rglob(stem_name))

        for candidate in candidates:
            if Path(candidate).exists():
                path = Path(candidate)
                logger.info("[run_visualization] Fichier trouvé : %s", path)
                break

    if not path.exists():
        return json.dumps({
            "status":        "error",
            "error_message": f"Fichier introuvable : {input_path}",
            "hint":          "Utilise list_datasets() pour voir les fichiers disponibles.",
        })

    try:
        result = run_viz_pipeline(
            input_path=str(path),
            output_dir=output_dir or None,
            target_column=target_column or None,
            export_png=export_png,
            question=question or None,
        )

        logger.info(
            "[run_visualization] Terminé — status=%s — %d charts — %.2fs",
            result.get("status"),
            result.get("n_charts", 0),
            result.get("duration_s", 0),
        )

        dataset_name   = result.get("dataset_name", "")
        dashboard_path = result.get("dashboard_path", "")

        from pathlib import Path as _P
        db_path = _P(dashboard_path) if dashboard_path else (
            ROOT / "outputs" / "viz" / dataset_name / "dashboard.html"
        )

        kpis = result.get("kpis", [])[:4]
        kpi_lines = "\n".join(
            f"- {k.get('icone','')} **{k.get('label','')}** : {k.get('valeur','')}"
            for k in kpis
        )
        return (
            f"## ✅ Dashboard prêt — {dataset_name}\n\n"
            f"**{result.get('n_rows')} lignes · "
            f"{result.get('n_cols')} colonnes · "
            f"{result.get('n_charts')} graphiques**\n\n"
            f"### KPIs\n{kpi_lines}\n\n"
            "Tape **montre le dashboard** pour l'afficher."
        )

    except Exception as exc:
        import traceback
        logger.error("[run_visualization] EXCEPTION:\n%s", traceback.format_exc())
        return json.dumps({"status": "error", "error_message": str(exc)})


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 3 — read_viz_report
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def read_viz_report(report_path: str) -> str:
    """
    Lit le rapport Markdown EDA généré par viz_auto ou run_visualization.

    Contient : KPIs, statistiques, corrélations, liste des graphiques.

    Paramètres :
    - report_path : champ report_path du résultat
    """
    p = Path(report_path)
    if not p.is_absolute():
        p = ROOT / report_path

    if not p.exists():
        return json.dumps({"error": f"Rapport introuvable : {report_path}"})

    return p.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 4 — list_charts
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_charts(charts_dir: str) -> str:
    """
    Liste les graphiques HTML et PNG générés.

    Paramètres :
    - charts_dir : champ charts_dir du résultat
    """
    p = Path(charts_dir)
    if not p.is_absolute():
        p = ROOT / charts_dir

    if not p.exists():
        return json.dumps({"error": f"Dossier introuvable : {charts_dir}", "charts": []})

    charts = []
    for ext in ("*.html", "*.png"):
        for f in sorted(p.glob(ext)):
            charts.append({
                "name":    f.name,
                "path":    str(f),
                "size_kb": round(f.stat().st_size / 1024, 1),
            })

    return json.dumps(
        {"n_charts": len(charts), "charts_dir": str(p), "charts": charts},
        ensure_ascii=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 5 — get_download_links
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_download_links(dataset_name: str) -> str:
    """
    Retourne les liens Markdown cliquables pour télécharger les fichiers EDA.

    Inclut le lien dashboard.html principal et les graphiques individuels.

    Paramètres :
    - dataset_name : champ dataset_name du résultat
    """
    return _fetch_download_links(dataset_name)


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 6 — list_all_results
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_all_results() -> str:
    """
    Liste tous les datasets visualisés disponibles au téléchargement.

    Utiliser quand l'utilisateur demande ses analyses disponibles :
    "quels graphiques j'ai", "mes analyses", "datasets visualisés"
    """
    viz_dir = ROOT / "outputs" / "viz"
    if not viz_dir.exists():
        return "Aucune visualisation trouvée dans `outputs/viz/`."

    datasets = [d.name for d in sorted(viz_dir.iterdir()) if d.is_dir()]
    if not datasets:
        return "Aucune visualisation disponible. Lance d'abord `viz_auto()` sur un fichier."

    lines = ["## 📊 Analyses disponibles\n"]
    for ds in datasets:
        links = _fetch_download_links(ds)
        lines.append(f"### {ds}")
        lines.append(links)
        lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 7 — list_datasets
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_datasets(subdirectory: str = "") -> str:
    """
    Liste les fichiers de données disponibles sur le serveur.

    Utiliser quand run_visualization retourne "fichier introuvable".

    Paramètres :
    - subdirectory : sous-dossier à explorer (défaut : data/raw, data/processed, uploads)
    """
    search_dirs = (
        [ROOT / subdirectory]
        if subdirectory
        else [
            ROOT / "data" / "raw",
            ROOT / "data" / "uploads",
            ROOT / "data" / "processed",
        ]
    )

    datasets = []
    seen: set = set()
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for f in search_dir.rglob("*"):
            if f.is_file() and f.suffix.lower() in _EXTENSIONS and str(f) not in seen:
                seen.add(str(f))
                datasets.append({
                    "name":    f.name,
                    "path":    str(f),
                    "size_kb": round(f.stat().st_size / 1024, 1),
                })

    return json.dumps({
        "n_datasets": len(datasets),
        "datasets":   datasets[:20],
        "hint":       "Utiliser 'path' comme input_path pour run_visualization.",
    }, indent=2, ensure_ascii=False)




# ─────────────────────────────────────────────────────────────────────────────
# TOOL 8 — show_dashboard : affiche le dashboard inline dans Open WebUI
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def show_dashboard(dataset_name: str = "") -> str:
    """Affiche le dashboard dans Open WebUI."""
    if not dataset_name:
        viz_dir = ROOT / "outputs" / "viz"
        if viz_dir.exists():
            datasets = sorted(
                [d for d in viz_dir.iterdir() if d.is_dir()],
                key=lambda d: d.stat().st_mtime,
                reverse=True,
            )
            if datasets:
                dataset_name = datasets[0].name

    if not dataset_name:
        return "Lance viz_auto() d'abord."

    dashboard_path = ROOT / "outputs" / "viz" / dataset_name / "dashboard.html"

    if not dashboard_path.exists():
        return f"Dashboard introuvable pour : {dataset_name}. Lance viz_auto() d'abord."

    html = dashboard_path.read_text(encoding="utf-8")
    size_kb = round(dashboard_path.stat().st_size / 1024, 1)
    logger.info("[show_dashboard] %s — %.1f KB", dataset_name, size_kb)
    # Dashboard 7.6KB avec iframes relatifs — Mistral peut le copier
    return f"```html\n{html}\n```"


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8002)