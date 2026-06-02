"""

backend/file_server.py

Serveur de téléchargement des fichiers .

Supporte ETL (data/processed + outputs/rapport_etl) 
ET Visualization (outputs/viz).

L'utilisateur Open WebUI clique sur les liens pour télécharger.


Nouveautés v3 :
- Route /results/viz/{dataset} : dashboard.html + graphiques HTML/PNG + rapports
- Dashboard.html dans outputs/viz/{dataset}/
- PNG dans outputs/viz/{dataset}/charts/

Démarrer :

    uv run --env-file .env python file_server.py

    → http://localhost:8090

Routes :

    GET /health                 → santé du serveur

    GET /files/{bucket}/{path}  → téléchargement direct

    GET /list/{bucket}          → liste des fichiers disponibles

    GET /results/{dataset_name} → tous les fichiers d'un dataset avec URLs
    
    GET /results/viz/{dataset_name} → fichiers Visualization d'un dataset

"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

SERVED_DIRS = {
    "processed": ROOT / "data" / "processed",
    "outputs":   ROOT / "outputs",
    "uploads":   ROOT / "data" / "uploads",
    "viz":       ROOT / "outputs" / "viz",
}

BASE_URL = os.getenv("FILE_SERVER_URL", "http://localhost:8090")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s : %(message)s",
)
logger = logging.getLogger("file_server")

app = FastAPI(
    title="AI DATA SKILL — File Server",
    description="Téléchargement des fichiers ETL et Visualization",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status":   "ok",
        "base_url": BASE_URL,
        "version":  "3.0.0",
        "dirs":     {k: str(v) for k, v in SERVED_DIRS.items()},
    }


@app.get("/files/{bucket}/{file_path:path}")
def download_file(bucket: str, file_path: str) -> FileResponse:
    """Télécharge un fichier depuis un bucket."""
    if bucket not in SERVED_DIRS:
        raise HTTPException(status_code=404, detail=f"Bucket inconnu : {bucket}")

    full_path = SERVED_DIRS[bucket] / file_path

    try:
        full_path.resolve().relative_to(SERVED_DIRS[bucket].resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Accès interdit")

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Fichier introuvable : {bucket}/{file_path}",
        )

    logger.info("[download] %s/%s", bucket, file_path)

    # Déterminer le media_type selon l'extension
    ext = full_path.suffix.lower()
    if ext == ".html":
        media_type = "text/html"
    elif ext == ".png":
        media_type = "image/png"
    elif ext == ".md":
        media_type = "text/markdown"
    elif ext == ".py":
        media_type = "text/x-python"
    else:
        media_type = "application/octet-stream"

    return FileResponse(
        path=str(full_path),
        filename=full_path.name,
        media_type=media_type,
    )


@app.get("/list/{bucket}")
def list_bucket(bucket: str, subfolder: str = "") -> JSONResponse:
    """Liste les fichiers disponibles dans un bucket."""
    if bucket not in SERVED_DIRS:
        raise HTTPException(status_code=404, detail=f"Bucket inconnu : {bucket}")

    base = SERVED_DIRS[bucket]
    if subfolder:
        base = base / subfolder

    if not base.exists():
        return JSONResponse({"files": [], "count": 0})

    EXTENSIONS = {".csv", ".md", ".py", ".json", ".parquet", ".xlsx", ".html", ".png"}
    files = []
    for f in sorted(base.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in EXTENSIONS:
            continue
        rel = f.relative_to(SERVED_DIRS[bucket])
        files.append({
            "name":         f.name,
            "path":         str(rel),
            "bucket":       bucket,
            "size_kb":      round(f.stat().st_size / 1024, 1),
            "download_url": f"{BASE_URL}/files/{bucket}/{rel}",
        })

    return JSONResponse({"files": files, "count": len(files)})


@app.get("/results/{dataset_name}")
def get_results_etl(dataset_name: str) -> JSONResponse:
    """Fichiers ETL d'un dataset : core_data, mapping_tables, rapports."""
    results = {
        "dataset_name":   dataset_name,
        "core_data":      [],
        "mapping_tables": [],
        "rapports":       [],
        "total_files":    0,
    }

    # core_data
    core_dir = SERVED_DIRS["processed"] / dataset_name / "core_data"
    if core_dir.exists():
        for f in sorted(core_dir.glob("*.csv")):
            rel = f.relative_to(SERVED_DIRS["processed"])
            results["core_data"].append({
                "name":         f.name,
                "size_kb":      round(f.stat().st_size / 1024, 1),
                "download_url": f"{BASE_URL}/files/processed/{rel}",
                "description":  "Dataset propre (nettoyé, lisible)",
            })

    # mapping_tables
    mapping_dir = SERVED_DIRS["processed"] / dataset_name / "mapping_tables"
    if mapping_dir.exists():
        for f in sorted(mapping_dir.glob("*.csv")):
            rel = f.relative_to(SERVED_DIRS["processed"])
            if "_JOINTE" in f.name:
                desc = "Table jointe complète"
            elif "_dim_" in f.name:
                desc = "Dimension"
            elif "_fact_" in f.name:
                desc = "Table de faits"
            else:
                desc = "Star Schema"
            results["mapping_tables"].append({
                "name":         f.name,
                "size_kb":      round(f.stat().st_size / 1024, 1),
                "download_url": f"{BASE_URL}/files/processed/{rel}",
                "description":  desc,
            })

    # rapports ETL
    rapport_dir = SERVED_DIRS["outputs"] / "rapport_etl" / dataset_name
    if rapport_dir.exists():
        for f in sorted(rapport_dir.iterdir()):
            if not f.is_file():
                continue
            rel = f.relative_to(SERVED_DIRS["outputs"])
            if "etl_report" in f.name:
                desc = "Rapport ETL comparatif"
            elif "etl_script" in f.name:
                desc = "Script Python reproductible"
            elif "quality_report" in f.name:
                desc = "Rapport qualité"
            else:
                desc = "Fichier rapport"
            results["rapports"].append({
                "name":         f.name,
                "size_kb":      round(f.stat().st_size / 1024, 1),
                "download_url": f"{BASE_URL}/files/outputs/{rel}",
                "description":  desc,
            })

    results["total_files"] = (
        len(results["core_data"]) +
        len(results["mapping_tables"]) +
        len(results["rapports"])
    )
    return JSONResponse(results)


@app.get("/results/viz/{dataset_name}")
def get_results_viz(dataset_name: str) -> JSONResponse:
    """Fichiers Visualization : dashboard.html + graphiques HTML/PNG + rapports EDA."""
    results: dict = {
        "dataset_name": dataset_name,
        "dashboard":    [],
        "charts":       [],
        "rapports":     [],
        "total_files":  0,
    }

    viz_dir = SERVED_DIRS["viz"] / dataset_name

    # Dashboard HTML combiné (priorité absolue)
    dashboard_file = viz_dir / "dashboard.html"
    if dashboard_file.exists():
        rel = dashboard_file.relative_to(SERVED_DIRS["viz"])
        results["dashboard"].append({
            "name":         dashboard_file.name,
            "size_kb":      round(dashboard_file.stat().st_size / 1024, 1),
            "download_url": f"{BASE_URL}/files/viz/{rel}",
            "description":  "Dashboard interactif complet (tous les graphiques)",
        })

    # Graphiques HTML puis PNG
    charts_dir = viz_dir / "charts"
    if charts_dir.exists():
        for f in sorted(charts_dir.glob("*.html")):
            rel = f.relative_to(SERVED_DIRS["viz"])
            results["charts"].append({
                "name":         f.name,
                "size_kb":      round(f.stat().st_size / 1024, 1),
                "download_url": f"{BASE_URL}/files/viz/{rel}",
                "description":  "Graphique interactif (HTML)",
            })
        for f in sorted(charts_dir.glob("*.png")):
            rel = f.relative_to(SERVED_DIRS["viz"])
            results["charts"].append({
                "name":         f.name,
                "size_kb":      round(f.stat().st_size / 1024, 1),
                "download_url": f"{BASE_URL}/files/viz/{rel}",
                "description":  "Image graphique (PNG)",
            })

    # Rapports Markdown EDA
    reports_dir = viz_dir / "rapports"
    if reports_dir.exists():
        for f in sorted(reports_dir.glob("*.md")):
            rel = f.relative_to(SERVED_DIRS["viz"])
            results["rapports"].append({
                "name":         f.name,
                "size_kb":      round(f.stat().st_size / 1024, 1),
                "download_url": f"{BASE_URL}/files/viz/{rel}",
                "description":  "Rapport EDA Markdown",
            })

    results["total_files"] = (
        len(results["dashboard"]) +
        len(results["charts"]) +
        len(results["rapports"])
    )
    return JSONResponse(results)


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint /etl — appelé par le Pipe Open WebUI
# ─────────────────────────────────────────────────────────────────────────────

class ETLRequest(BaseModel):
    input_path:     Optional[str] = ""
    file_content:   Optional[str] = ""
    filename:       Optional[str] = "uploaded_data.csv"
    target_column:  Optional[str] = ""
    missing_strategy: str = "auto"
    outlier_action: str = "cap"
    encode_method:  str = "auto"
    scale_method:   str = "standard"


@app.post("/etl")
def run_etl_endpoint(req: ETLRequest) -> JSONResponse:
    """Lance le pipeline ETL. Appelé par le Pipe Open WebUI."""
    try:
        from argparse import Namespace
        from skills.etl_skill.scripts.run import run_pipeline

        input_path = req.input_path or ""

        # Sauvegarder le contenu uploadé si fourni
        if req.file_content and not input_path:
            upload_dir = ROOT / "data" / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            fname = req.filename or "uploaded_data.csv"
            path  = upload_dir / fname
            path.write_text(req.file_content, encoding="utf-8")
            input_path = str(path)

        # Trouver le dernier fichier si aucun chemin
        if not input_path:
            EXTENSIONS = {".csv", ".xlsx", ".xls", ".xlsm", ".json", ".parquet"}
            upload_dir = ROOT / "data" / "uploads"
            files = sorted(
                [f for f in upload_dir.rglob("*")
                 if f.is_file() and f.suffix.lower() in EXTENSIONS],
                key=os.path.getmtime,
                reverse=True,
            )
            if not files:
                return JSONResponse(
                    {"status": "error", "error_message": "Aucun fichier trouvé."},
                    status_code=400,
                )
            input_path = str(files[0])

        args = Namespace(
            input_path=input_path,
            target_column=req.target_column or "",
            missing_strategy=req.missing_strategy,
            fill_mode="smart",
            outlier_action=req.outlier_action,
            outlier_method="iqr",
            encode_method=req.encode_method,
            scale_method=req.scale_method,
            columns_to_exclude="",
            feature_operations="",
            output_dir="",
        )

        result = run_pipeline(args)
        return JSONResponse(result)

    except Exception as exc:
        import traceback
        logger.error("[/etl] EXCEPTION:\n%s", traceback.format_exc())
        return JSONResponse(
            {"status": "error", "error_message": str(exc)},
            status_code=500,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint /visualize — appelé par le Pipe Open WebUI
# ─────────────────────────────────────────────────────────────────────────────

class VizRequest(BaseModel):
    input_path:    Optional[str] = ""
    file_content:  Optional[str] = ""
    filename:      Optional[str] = "uploaded_data.csv"
    target_column: Optional[str] = ""
    question:      Optional[str] = ""
    export_png:    bool = True


@app.post("/visualize")
def visualize(req: VizRequest) -> JSONResponse:
    """
    Lance le pipeline de visualisation EDA.
    Appelé par le Pipe Open WebUI (openwebui_viz_pipe.py).
    """
    try:
        from skills.visualization_skill.scripts.run import run_viz_pipeline

        input_path = req.input_path or ""

        # Sauvegarder le contenu uploadé si fourni
        if req.file_content and not input_path:
            upload_dir = ROOT / "data" / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            fname = req.filename or "uploaded_data.csv"
            path  = upload_dir / fname
            path.write_text(req.file_content, encoding="utf-8")
            input_path = str(path)

        # Trouver le dernier fichier si aucun chemin fourni
        if not input_path:
            EXTENSIONS = {".csv", ".xlsx", ".xls", ".xlsm", ".json", ".parquet"}
            upload_dir = ROOT / "data" / "uploads"
            files = sorted(
                [f for f in upload_dir.rglob("*")
                 if f.is_file() and f.suffix.lower() in EXTENSIONS],
                key=os.path.getmtime,
                reverse=True,
            )
            if not files:
                return JSONResponse(
                    {"status": "error", "error_message": "Aucun fichier trouvé."},
                    status_code=400,
                )
            input_path = str(files[0])

        result = run_viz_pipeline(
            input_path=input_path,
            target_column=req.target_column or None,
            export_png=req.export_png,
            question=req.question or None,
        )

        # Ajouter l'URL du dashboard
        dataset_name = result.get("dataset_name", "")
        dashboard_path = ROOT / "outputs" / "viz" / dataset_name / "dashboard.html"
        if dashboard_path.exists():
            result["dashboard_url"] = (
                f"{BASE_URL}/files/viz/{dataset_name}/dashboard.html"
            )

        return JSONResponse(result)

    except Exception as exc:
        import traceback
        logger.error("[/visualize] EXCEPTION:\n%s", traceback.format_exc())
        return JSONResponse(
            {"status": "error", "error_message": str(exc)},
            status_code=500,
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("FILE_SERVER_PORT", "8090"))
    logger.info("File Server v3 démarré → %s", BASE_URL)
    uvicorn.run(app, host="0.0.0.0", port=port)