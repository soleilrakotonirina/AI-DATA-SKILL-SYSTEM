"""
backend/skills/visualization_skill/scripts/main.py
Point d'entree du Visualization Skill.

Appele par executor.py (orchestrateur Gemini) via le plan JSON.
Peut aussi etre lance directement en CLI pour les tests.

Usage CLI :
    uv run --env-file .env python -m skills.visualization_skill.scripts.main \\
        --input data/processed/clean_data/core_data/clean_data.csv \\
        --session-id mysession

Usage orchestrateur (plan JSON) :
    result = run_visualization_skill({
        "step": 2,
        "skill": "Visualization",
        "endpoint": "/api/visualization/eda",
        "params": {
            "session_id": "user_42",
            "dataset_path": "data/processed/clean_data.csv",
            ...
        }
    })
"""

from __future__ import annotations

# Charger .env EN PREMIER avant tout import qui lit os.environ
from dotenv import load_dotenv
load_dotenv()

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

from pydantic import ValidationError

from schemas.visualization import VisualizationRequest, VisualizationResponse
from skills.visualization_skill.scripts.logic import run_visualization_pipeline

logger = logging.getLogger(__name__)


def run_visualization_skill(plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    Point d'entree synchrone pour executor.py (orchestrateur Gemini).

    Construit un VisualizationRequest depuis les params du plan JSON,
    execute le pipeline async et retourne le dict de sortie standard.

    Args:
        plan: Plan JSON de l'orchestrateur :
              {
                "step": 2,
                "skill": "Visualization",
                "endpoint": "/api/visualization/eda",
                "params": {VisualizationRequest fields}
              }

    Returns:
        Dict compatible VisualizationResponse (status, charts, report_mdx_id...).
        Ne leve jamais d'exception — en cas d'erreur : status='error'.
    """
    params = plan.get("params", {})
    session_id = params.get("session_id", "unknown")

    try:
        request = VisualizationRequest(**params)
    except ValidationError as exc:
        logger.error("[Viz Skill] Validation Pydantic echouee : %s", exc)
        return {
            "skill":           "Visualization",
            "session_id":      session_id,
            "status":          "error",
            "charts":          [],
            "stats":           {},
            "eda_report_path": None,
            "report_mdx_id":   None,
            "charts_paths":    {},
            "gemini_comments": {},
            "errors":          [f"Validation Pydantic : {exc}"],
            "error_message":   f"Validation Pydantic echouee : {exc}",
        }

    return asyncio.run(_run_async(request))


async def _run_async(request: VisualizationRequest) -> Dict[str, Any]:
    """Execute le pipeline asynchrone et convertit la reponse en dict."""
    try:
        response: VisualizationResponse = await run_visualization_pipeline(request)
        return response.model_dump()
    except Exception as exc:
        logger.error("[Viz Skill] Exception non capturee : %s", exc, exc_info=True)
        return {
            "skill":           "Visualization",
            "session_id":      request.session_id,
            "status":          "error",
            "charts":          [],
            "stats":           {},
            "eda_report_path": None,
            "report_mdx_id":   None,
            "charts_paths":    {},
            "gemini_comments": {},
            "errors":          [f"Erreur interne : {exc}"],
            "error_message":   f"Erreur interne : {exc}",
        }




def _resoudre_inputs(input_arg: str) -> list[str]:
    """
    Resout un argument --input en liste de fichiers a traiter.

    Cas supportes :
    - Fichier unique  : data/processed/xxx.csv
    - Dossier         : data/processed/Donnees_Universitaires/
    - Glob explicite  : data/processed/Donnees_Universitaires/*
    - Glob recursif   : data/processed/Donnees_Universitaires/**/*.csv

    Formats acceptes : .csv, .xlsx, .xls, .json, .parquet

    Args:
        input_arg: Valeur de l'argument --input.

    Returns:
        Liste triee de chemins absolus vers les fichiers a traiter.
    """
    import glob as _glob

    _EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".parquet"}
    p = Path(input_arg)

    # Cas 1 : fichier unique existant
    if p.is_file() and p.suffix.lower() in _EXTENSIONS:
        return [str(p)]

    # Cas 2 : dossier → tous les fichiers supportes (recursif)
    if p.is_dir():
        fichiers = sorted(
            str(f) for f in p.rglob("*")
            if f.is_file() and f.suffix.lower() in _EXTENSIONS
        )
        if fichiers:
            logger.info(
                "[Viz Skill] Dossier '%s' : %d fichier(s) detecte(s)",
                input_arg, len(fichiers),
            )
        return fichiers

    # Cas 3 : glob pattern (contient * ou ?)
    if "*" in input_arg or "?" in input_arg:
        matches = sorted(_glob.glob(input_arg, recursive=True))
        fichiers = [
            m for m in matches
            if Path(m).is_file() and Path(m).suffix.lower() in _EXTENSIONS
        ]
        if fichiers:
            logger.info(
                "[Viz Skill] Glob '%s' : %d fichier(s) detecte(s)",
                input_arg, len(fichiers),
            )
        return fichiers

    # Cas 4 : fichier inexistant
    logger.error("[Viz Skill] Chemin introuvable : %s", input_arg)
    return []

def main() -> int:
    """Point d'entree CLI pour les tests et le developpement."""
    parser = argparse.ArgumentParser(
        description="Visualization Skill — Analyse EDA et graphiques Plotly",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
    # EDA simple
    uv run --env-file .env python -m skills.visualization_skill.scripts.main \\
        --input data/processed/exportations_madagascar/core_data/exportations_dirty.csv \\
        --session-id mysession

    # EDA avec variable cible et question
    uv run --env-file .env python -m skills.visualization_skill.scripts.main \\
        --input data/processed/clean.csv \\
        --target churn \\
        --question "Quelles regions exportent le plus ?" \\
        --session-id mysession_churn
        """,
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        required=True,
        help=(
            "Chemin du dataset, d'un dossier, ou pattern glob. "
            "Exemples : "
            "data/processed/Donnees_Universitaires/mapping_tables/xxx.csv  "
            "data/processed/Donnees_Universitaires/  "
            "data/processed/Donnees_Universitaires/*"
        ),
    )
    parser.add_argument(
        "--session-id", "-s",
        type=str,
        default="cli_session",
        help="ID de session Directus",
    )
    parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Colonne cible pour analyse supervisee",
    )
    parser.add_argument(
        "--question",
        type=str,
        default=None,
        help="Question analytique en langage naturel",
    )
    parser.add_argument(
        "--no-gemini",
        action="store_true",
        help="Desactiver les commentaires Gemini",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Ne pas generer le rapport MDX",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Activer les logs DEBUG",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s : %(message)s",
    )

    # ── Resoudre les fichiers a traiter ──────────────────────────────────────
    fichiers = _resoudre_inputs(args.input)

    if not fichiers:
        logger.error(
            "[Viz Skill] Aucun fichier CSV/Excel/Parquet trouve pour : %s",
            args.input,
        )
        return 1

    logger.info("[Viz Skill] %d fichier(s) a traiter", len(fichiers))

    # ── Traiter chaque fichier ────────────────────────────────────────────────
    resultats = []
    code_retour = 0

    for i, fichier in enumerate(fichiers, start=1):
        session_id = (
            args.session_id
            if len(fichiers) == 1
            else f"{args.session_id}_{Path(fichier).stem}"
        )

        logger.info(
            "[Viz Skill] (%d/%d) Traitement : %s — session=%s",
            i, len(fichiers), Path(fichier).name, session_id,
        )

        plan = {
            "step":     2,
            "skill":    "Visualization",
            "endpoint": "/api/visualization/eda",
            "params": {
                "session_id":      session_id,
                "dataset_path":    fichier,
                "target_column":   args.target,
                "question":        args.question,
                "export_formats":  ["html", "png"],
                "output_dir":      "outputs/charts",
                "generate_report": not args.no_report,
                "gemini_comments": not args.no_gemini,
            },
        }

        result = run_visualization_skill(plan)
        resultats.append(result)

        status = result.get("status", "error")
        charts  = len(result.get("charts", []))
        mdx_id  = result.get("report_mdx_id") or "(non publie)"

        if status == "success":
            logger.info(
                "[Viz Skill] (%d/%d) OK — %s — %d charts — mdx=%s",
                i, len(fichiers), Path(fichier).name, charts, mdx_id,
            )
        else:
            logger.error(
                "[Viz Skill] (%d/%d) ECHEC — %s — %s",
                i, len(fichiers), Path(fichier).name,
                result.get("error_message", "erreur inconnue"),
            )
            code_retour = 1

    # ── Afficher le resume final ──────────────────────────────────────────────
    if len(fichiers) == 1:
        print(json.dumps(resultats[0], indent=2, default=str, ensure_ascii=False))
    else:
        resume = {
            "total":    len(fichiers),
            "succes":   sum(1 for r in resultats if r.get("status") == "success"),
            "echecs":   sum(1 for r in resultats if r.get("status") != "success"),
            "fichiers": [
                {
                    "fichier":  Path(f).name,
                    "status":   r.get("status"),
                    "charts":   len(r.get("charts", [])),
                    "mdx_id":   r.get("report_mdx_id"),
                }
                for f, r in zip(fichiers, resultats)
            ],
        }
        print(json.dumps(resume, indent=2, default=str, ensure_ascii=False))
        logger.info(
            "[Viz Skill] Resume : %d/%d succes",
            resume["succes"], resume["total"],
        )

    return code_retour


if __name__ == "__main__":
    sys.exit(main())