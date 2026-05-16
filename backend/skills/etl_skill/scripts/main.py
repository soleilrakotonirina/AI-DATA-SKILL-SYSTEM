"""
backend/skills/etl_skill/scripts/main.py
Point d'entree du ETL Skill pour l'orchestrateur Gemini (executor.py).

Recoit un plan JSON depuis executor.py, construit un ETLRequest Pydantic,
appelle le pipeline async, et retourne un dict de sortie standard.

Aucune exception n'est propagee — en cas d'erreur :
    status='error', message dans errors[]

Plan JSON attendu :
{
    "step": 1,
    "skill": "ETL",
    "endpoint": "/api/etl/run",
    "params": {
        "session_id": "user_42_2025-06-01_14-30-22",
        "input_path": "data/raw/data.csv",
        "missing_strategy": "auto",
        ...
    }
}

Utilisation CLI :
    python -m skills.etl_skill.scripts.main --plan path/to/plan.json
    python -m skills.etl_skill.scripts.main --input data/raw/dataset.csv --session-id mysession
"""

from __future__ import annotations

# Charger .env EN PREMIER, avant tout import qui lit os.environ au niveau module
# (directus_client.py, etc.). Si load_dotenv est appelé après, DIRECTUS_TOKEN
# reste vide car la variable globale a déjà été évaluée.
from dotenv import load_dotenv
load_dotenv()

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from schemas.etl import ETLRequest, ETLResponse
from skills.etl_skill.scripts.logic import run_etl_pipeline

logger = logging.getLogger(__name__)


def _error_dict(session_id: str, message: str) -> dict[str, Any]:
    """Construit un dict de sortie standard pour les erreurs critiques."""
    logger.error("[ETL Skill] Erreur critique : %s", message)
    return {
        "skill": "ETL",
        "session_id": session_id,
        "status": "error",
        "rows_before": 0,
        "rows_after": 0,
        "cols_before": 0,
        "cols_after": 0,
        "nulls_removed": 0,
        "duplicates_removed": 0,
        "script_path": None,
        "report_md_path": None,
        "report_mdx_id": None,
        "transformation_log": [],
        "encoders": {},
        "scalers": {},
        "dimensional_schema": None,
        "errors": [message],
        "error_message": message,
    }


async def run_etl_skill_async(plan: dict[str, Any]) -> dict[str, Any]:
    """
    Execute le ETL Skill depuis un plan JSON (orchestrateur async).

    Args:
        plan: Plan JSON recu de executor.py.
              Format : {"step", "skill", "endpoint", "params": {...}}

    Returns:
        Dict de sortie standard compatible avec ETLResponse Pydantic.
        Jamais d'exception propagee.
    """
    params = plan.get("params", {}) if isinstance(plan, dict) else {}
    session_id = params.get("session_id", "unknown_session")

    # ── Validation Pydantic des parametres ────────────────────────────────────
    try:
        request = ETLRequest(**params)
    except ValidationError as exc:
        return _error_dict(
            session_id,
            f"Validation Pydantic echouee : {exc.errors()}",
        )
    except TypeError as exc:
        return _error_dict(
            session_id,
            f"Parametres invalides : {exc}",
        )

    # ── Execution du pipeline ────────────────────────────────────────────────
    try:
        response: ETLResponse = await run_etl_pipeline(request)
        # Convertir ETLResponse en dict serialisable
        result = response.model_dump()
        logger.info(
            "[ETL Skill] Pipeline termine — session=%s, status=%s",
            session_id,
            result["status"],
        )
        return result
    except FileNotFoundError as exc:
        return _error_dict(session_id, f"Fichier introuvable : {exc}")
    except ValueError as exc:
        return _error_dict(session_id, f"Valeur invalide : {exc}")
    except Exception as exc:
        # Capturer toute exception non prevue pour ne jamais crasher
        logger.exception("[ETL Skill] Exception non capturee")
        return _error_dict(session_id, f"Erreur interne : {exc}")


def run_etl_skill(plan: dict[str, Any]) -> dict[str, Any]:
    """
    Wrapper synchrone autour de run_etl_skill_async.

    Permet d'appeler le Skill depuis du code synchrone (CLI, scripts,
    tests). Utilise asyncio.run() pour gerer la boucle asynchrone.

    Args:
        plan: Plan JSON recu de l'orchestrateur.

    Returns:
        Dict de sortie standard.
    """
    return asyncio.run(run_etl_skill_async(plan))


def main() -> int:
    """
    Point d'entree CLI.

    Usage :
        python -m skills.etl_skill.scripts.main --plan plan.json
        python -m skills.etl_skill.scripts.main --input data.csv

    Returns:
        Code de sortie 0 (success) ou 1 (error).
    """
    parser = argparse.ArgumentParser(
        description="ETL Skill — Pipeline de nettoyage et transformation",
    )
    parser.add_argument(
        "--plan", "-p",
        type=str,
        help="Chemin vers le plan JSON complet",
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        help="Chemin du dataset (mode simple, sans plan JSON)",
    )
    parser.add_argument(
        "--session-id", "-s",
        type=str,
        default="cli_session",
        help="ID de session Directus (mode --input)",
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

    # ── Construire le plan ────────────────────────────────────────────────────
    if args.plan:
        plan_path = Path(args.plan)
        if not plan_path.exists():
            logger.error("Plan JSON introuvable : %s", plan_path)
            return 1
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
    elif args.input:
        plan = {
            "step": 1,
            "skill": "ETL",
            "endpoint": "/api/etl/run",
            "params": {
                "session_id": args.session_id,
                "input_path": args.input,
            },
        }
    else:
        parser.error("Specifier --plan ou --input")
        return 1

    # ── Executer le Skill ─────────────────────────────────────────────────────
    result = run_etl_skill(plan)

    # ── Afficher le resultat ──────────────────────────────────────────────────
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())