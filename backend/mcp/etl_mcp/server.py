"""
mcp/etl_mcp/server.py
Serveur MCP FastMCP — ETL Skill

6 tools exposés à Open WebUI :
  - etl_auto          : pipeline ETL complet (trouve le fichier + exécute)
  - run_etl           : pipeline ETL avec chemin explicite
  - list_uploads      : liste les fichiers uploadés
  - get_download_links: liens de téléchargement après ETL
  - list_all_results  : tous les datasets disponibles
  - read_report       : lit le rapport Markdown
  - read_dataset      : aperçu du dataset nettoyé

Démarrer :
    uv run --env-file .env python mcp/etl_mcp/server.py
    → http://localhost:8001/mcp
"""

from __future__ import annotations

import json
import logging
import os
import sys
from argparse import Namespace
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Charger .env
load_dotenv(ROOT / ".env")

# Configuration
_upload_env = os.environ.get("UPLOAD_DIR", "")
if _upload_env:
    UPLOAD_DIR = Path(_upload_env)
    if not UPLOAD_DIR.is_absolute():
        UPLOAD_DIR = (ROOT / UPLOAD_DIR).resolve()
else:
    UPLOAD_DIR = ROOT / "data" / "uploads"

FILE_SERVER_URL = os.environ.get("FILE_SERVER_URL", "http://localhost:8090")

from skills.etl_skill.scripts.run import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s : %(message)s",
)
logger = logging.getLogger("etl_mcp")

mcp = FastMCP(name="etl-skill")


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 1 — etl_auto : outil principal (un seul appel)
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def etl_auto(
    target_column: str = "",
    missing_strategy: str = "auto",
    fill_mode: str = "smart",
    outlier_action: str = "cap",
    outlier_method: str = "iqr",
    encode_method: str = "auto",
    scale_method: str = "standard",
    columns_to_exclude: str = "",
    feature_operations: str = "",
) -> str:
    """
    [OUTIL PRINCIPAL] Trouve automatiquement le fichier uploadé le plus récent
    et exécute le pipeline ETL complet en un seul appel.

    Utilise cet outil EN PREMIER dès que l'utilisateur demande de nettoyer,
    transformer, préparer ou traiter un dataset uploadé dans Open WebUI.

    Retourne le rapport Markdown complet avec toutes les métriques.
    Après cet outil, appelle get_download_links(dataset_name) pour les liens.

    Paramètres optionnels :
    - target_column      : colonne ML à protéger (jamais encodée/scalée)
    - missing_strategy   : auto | constant | drop
    - fill_mode          : smart | constant
    - outlier_action     : cap | remove | flag
    - outlier_method     : iqr | zscore
    - encode_method      : auto | label | onehot
    - scale_method       : standard | minmax
    - columns_to_exclude : noms séparés par virgule
    - feature_operations : JSON list d'opérations dérivées
    """
    # Trouver le fichier le plus récent dans uploads/
    EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".parquet"}
    files = sorted(
        [f for f in UPLOAD_DIR.rglob("*") if f.is_file() and f.suffix.lower() in EXTENSIONS],
        key=os.path.getmtime,
        reverse=True,
    )
    if not files:
        return json.dumps({
            "status": "error",
            "error_message": f"Aucun fichier trouvé dans {UPLOAD_DIR}.",
        })

    input_path = str(files[0])
    logger.info("[etl_auto] Fichier : %s", input_path)

    args = Namespace(
        input_path=input_path,
        target_column=target_column,
        missing_strategy=missing_strategy,
        fill_mode=fill_mode,
        outlier_action=outlier_action,
        outlier_method=outlier_method,
        encode_method=encode_method,
        scale_method=scale_method,
        columns_to_exclude=columns_to_exclude,
        feature_operations=feature_operations,
        output_dir="",
    )

    try:
        result = run_pipeline(args)
        dataset_name = result.get("dataset_name", "")

        # ── Résumé ETL ────────────────────────────────────────────────────
        summary = {
            "dataset_name": dataset_name,
            "status":       result.get("status"),
            "rows_before":  result.get("rows_before"),
            "rows_after":   result.get("rows_after"),
            "cols_before":  result.get("cols_before"),
            "cols_after":   result.get("cols_after"),
            "duration_s":   result.get("duration_s"),
            "pipeline":     result.get("pipeline", ""),
            "clean_path":   result.get("clean_path"),
            "report_path":  result.get("report_path"),
            "errors":       result.get("errors", []),
        }

        # ── Liens de téléchargement (appelés en interne) ──────────────────
        download_section = ""
        try:
            import httpx
            r = httpx.get(f"{FILE_SERVER_URL}/results/{dataset_name}", timeout=5)
            data = r.json()

            if data["total_files"] > 0:
                lines = [f"\n## 📁 Fichiers téléchargeables — {dataset_name}\n"]

                if data["core_data"]:
                    lines.append("### Données propres")
                    for f in data["core_data"]:
                        lines.append(
                            f"- [{f['name']}]({f['download_url']}) — {f['size_kb']} KB"
                        )

                if data["mapping_tables"]:
                    lines.append("\n### Star Schema")
                    for f in data["mapping_tables"]:
                        lines.append(
                            f"- [{f['name']}]({f['download_url']}) — {f['size_kb']} KB — {f['description']}"
                        )

                if data["rapports"]:
                    lines.append("\n### Rapports")
                    for f in data["rapports"]:
                        lines.append(
                            f"- [{f['name']}]({f['download_url']}) — {f['size_kb']} KB — {f['description']}"
                        )

                lines.append(f"\n**{data['total_files']} fichiers disponibles**")
                download_section = "\n".join(lines)
        except Exception as exc:
            download_section = (
                f"\n⚠️ File server inaccessible : {exc}\n"
                f"Lance : `uv run --env-file .env python file_server.py`"
            )

        # ── Retour combiné : JSON métriques + Markdown liens ──────────────
        return json.dumps(summary, ensure_ascii=False, default=str) + "\n\n" + download_section

    except Exception as exc:
        import traceback
        logger.error("[etl_auto] EXCEPTION:\n%s", traceback.format_exc())
        return json.dumps({"status": "error", "error_message": str(exc)}) 
# ─────────────────────────────────────────────────────────────────────────────
# TOOL 2 — run_etl : pipeline avec chemin explicite
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool() 
def run_etl(
    input_path: str,
    target_column: str = "",
    missing_strategy: str = "auto",
    fill_mode: str = "smart",
    outlier_action: str = "cap",
    outlier_method: str = "iqr",
    encode_method: str = "auto",
    scale_method: str = "standard",
    columns_to_exclude: str = "",
    feature_operations: str = "",
    output_dir: str = "",
) -> str:
    """
    Execute le pipeline ETL complet sur un dataset (CSV, Excel, JSON, Parquet).

    Utiliser quand le chemin du fichier est connu.
    Pour les uploads Open WebUI, préférer etl_auto() qui trouve le fichier automatiquement.

    Retourne un JSON avec :
    - status        : success | success_with_warnings | error
    - dataset_name  : nom du dataset (à passer à get_download_links)
    - rows_before   : lignes avant nettoyage
    - rows_after    : lignes après nettoyage
    - clean_path    : chemin CSV propre
    - report_path   : chemin rapport Markdown
    - pipeline      : résumé des transformations
    - errors        : avertissements non bloquants

    Paramètres :
    - input_path          : chemin absolu ou relatif du fichier
    - target_column       : colonne ML à protéger
    - missing_strategy    : auto | constant | drop
    - fill_mode           : smart | constant
    - outlier_action      : cap | remove | flag
    - outlier_method      : iqr | zscore
    - encode_method       : auto | label | onehot
    - scale_method        : standard | minmax
    - columns_to_exclude  : noms séparés par virgule
    - feature_operations  : JSON list d'opérations dérivées
    - output_dir          : dossier de sortie custom (vide = auto)
    """
    logger.info("[run_etl] Démarrage — input=%s", input_path)

    args = Namespace(
        input_path=input_path,
        target_column=target_column,
        missing_strategy=missing_strategy,
        fill_mode=fill_mode,
        outlier_action=outlier_action,
        outlier_method=outlier_method,
        encode_method=encode_method,
        scale_method=scale_method,
        columns_to_exclude=columns_to_exclude,
        feature_operations=feature_operations,
        output_dir=output_dir,
    )

    try:
        result = run_pipeline(args)
        logger.info(
            "[run_etl] Terminé — status=%s — %d→%d lignes — %.2fs",
            result.get("status"),
            result.get("rows_before", 0),
            result.get("rows_after", 0),
            result.get("duration_s", 0),
        )
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as exc:
        import traceback
        logger.error("[run_etl] EXCEPTION:\n%s", traceback.format_exc())
        return json.dumps({"status": "error", "error_message": str(exc)})


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 3 — list_uploads : liste les fichiers uploadés
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_uploads(upload_dir: str = "") -> str:
    """
    Liste les fichiers uploadés dans Open WebUI, du plus récent au plus ancien.

    Paramètres :
    - upload_dir : dossier custom (vide = dossier uploads par défaut)
    """
    EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".parquet"}
    p = Path(upload_dir) if upload_dir else UPLOAD_DIR

    if not p.exists():
        return json.dumps({"error": f"Dossier introuvable : {p}", "files": []})

    files = sorted(
        [f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in EXTENSIONS],
        key=os.path.getmtime,
        reverse=True,
    )

    return json.dumps({
        "upload_dir": str(p),
        "count": len(files),
        "files": [
            {
                "path":     str(f),
                "name":     f.name,
                "size_kb":  round(f.stat().st_size / 1024, 1),
            }
            for f in files[:10]
        ],
    }, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 4 — get_download_links : liens de téléchargement
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_download_links(dataset_name: str) -> str:
    """
    Retourne les liens de téléchargement de tous les fichiers générés par ETL.

    Appelle cet outil APRÈS etl_auto ou run_etl pour obtenir les liens cliquables.
    Les liens s'ouvrent directement dans le navigateur pour télécharger les fichiers.

    Paramètres :
    - dataset_name : nom du dataset (champ dataset_name dans le JSON de etl_auto/run_etl)
    """
    import httpx

    try:
        r = httpx.get(f"{FILE_SERVER_URL}/results/{dataset_name}", timeout=5)
        data = r.json()
    except Exception as exc:
        return (
            f"❌ File server inaccessible : {exc}\n\n"
            f"Lance le file server dans un terminal :\n"
            f"```bash\n"
            f"cd ~/Formations/AI_DATA_SKILL_SYSTEM/backend\n"
            f"uv run --env-file .env python file_server.py\n"
            f"```"
        )

    if data["total_files"] == 0:
        return f"Aucun fichier trouvé pour le dataset : **{dataset_name}**"

    lines = [f"## 📁 Fichiers disponibles — {dataset_name}\n"]

    if data["core_data"]:
        lines.append("### Données propres (nettoyées, lisibles)")
        for f in data["core_data"]:
            lines.append(
                f"- [{f['name']}]({f['download_url']}) "
                f"— {f['size_kb']} KB — *{f['description']}*"
            )

    if data["mapping_tables"]:
        lines.append("\n### Star Schema (dimensions + faits)")
        for f in data["mapping_tables"]:
            lines.append(
                f"- [{f['name']}]({f['download_url']}) "
                f"— {f['size_kb']} KB — *{f['description']}*"
            )

    if data["rapports"]:
        lines.append("\n### Rapports et scripts")
        for f in data["rapports"]:
            lines.append(
                f"- [{f['name']}]({f['download_url']}) "
                f"— {f['size_kb']} KB — *{f['description']}*"
            )

    lines.append(f"\n**{data['total_files']} fichiers disponibles** — clique sur un lien pour télécharger")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 5 — list_all_results : tous les datasets disponibles
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_all_results() -> str:
    """
    Liste tous les datasets traités disponibles au téléchargement.

    Utilise cet outil quand l'utilisateur demande :
    - "quels fichiers sont disponibles ?"
    - "montre-moi mes datasets traités"
    - "qu'est-ce que j'ai déjà traité ?"
    """
    import httpx

    processed_dir = ROOT / "data" / "processed"
    if not processed_dir.exists():
        return "Aucun dataset traité trouvé dans `data/processed/`."

    datasets = [d.name for d in sorted(processed_dir.iterdir()) if d.is_dir()]
    if not datasets:
        return "Aucun dataset disponible. Lance d'abord `etl_auto()` sur un fichier."

    lines = ["## 📦 Datasets disponibles au téléchargement\n"]

    for ds in datasets:
        try:
            r = httpx.get(f"{FILE_SERVER_URL}/results/{ds}", timeout=3)
            data = r.json()
            total = data["total_files"]
            lines.append(f"### {ds} — {total} fichier(s)")

            all_files = data["core_data"] + data["mapping_tables"] + data["rapports"]
            for f in all_files[:6]:
                lines.append(
                    f"  - [{f['name']}]({f['download_url']}) — {f['size_kb']} KB"
                )
            if total > 6:
                lines.append(f"  - *... et {total - 6} autres fichiers*")
            lines.append("")

        except Exception:
            lines.append(f"### {ds}")
            lines.append("  *File server indisponible — lance `python file_server.py`*\n")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 6 — read_report : lit le rapport Markdown
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def read_report(report_path: str) -> str:
    """
    Lit et retourne le contenu complet du rapport Markdown ETL.

    Utilise report_path retourné par run_etl (pas par etl_auto — etl_auto
    retourne déjà le contenu du rapport directement).

    Paramètres :
    - report_path : chemin .md retourné dans le JSON de run_etl
    """
    p = Path(report_path)
    if not p.exists():
        return json.dumps({"error": f"Rapport introuvable : {report_path}"})
    return p.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 7 — read_dataset : aperçu du dataset nettoyé
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def read_dataset(dataset_path: str, n_rows: int = 10) -> str:
    """
    Retourne les premières lignes du dataset nettoyé.

    Utilise clean_path retourné par run_etl ou etl_auto.

    Paramètres :
    - dataset_path : chemin CSV propre (clean_path)
    - n_rows       : nombre de lignes à afficher (défaut 10)
    """
    p = Path(dataset_path)
    if not p.exists():
        return json.dumps({"error": f"Dataset introuvable : {dataset_path}"})
    try:
        import pandas as pd
        df = pd.read_csv(p, nrows=n_rows)
        return json.dumps(
            {
                "dataset":    dataset_path,
                "rows_shown": len(df),
                "total_cols": df.shape[1],
                "columns":    df.columns.tolist(),
                "dtypes":     df.dtypes.astype(str).to_dict(),
                "preview":    df.to_dict(orient="records"),
            },
            ensure_ascii=False,
            default=str,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)})


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8001)