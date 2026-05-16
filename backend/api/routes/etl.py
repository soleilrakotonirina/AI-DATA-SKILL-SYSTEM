"""
backend/api/routes/etl.py
Endpoint FastAPI du ETL Skill : POST /api/etl/run.

Recoit un ETLRequest valide par Pydantic, lance le pipeline ETL
de bout en bout, et retourne un ETLResponse contenant les metriques
avant/apres et le report_mdx_id du rapport publie dans Directus.

Enregistrement dans api/main.py :
    from api.routes import etl
    app.include_router(etl.router, prefix="/api", tags=["ETL"])
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from schemas.etl import ETLRequest, ETLResponse
from skills.etl_skill.scripts.logic import run_etl_pipeline

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/etl/run",
    response_model=ETLResponse,
    summary="Execute le pipeline ETL complet",
    description=(
        "Charge un dataset, le nettoie, le transforme, genere un rapport "
        "MDX et le publie dans Directus. Retourne les metriques avant/apres "
        "et l'ID du rapport publie."
    ),
    responses={
        200: {"description": "Pipeline ETL execute avec succes"},
        404: {"description": "Fichier dataset introuvable"},
        422: {"description": "Parametres ETLRequest invalides"},
        500: {"description": "Erreur interne du Skill"},
    },
)
async def run_etl_endpoint(request: ETLRequest) -> ETLResponse:
    """
    Lance le ETL Skill complet sur le dataset specifie.

    Args:
        request: ETLRequest Pydantic — schema valide automatiquement.

    Returns:
        ETLResponse avec statistiques avant/apres et report_mdx_id Directus.

    Raises:
        HTTPException 404: Fichier dataset introuvable.
        HTTPException 422: Parametres invalides (gere par Pydantic en amont).
        HTTPException 500: Erreur interne d'execution.
    """
    logger.info(
        "ETL Skill demarre — session=%s, input=%s",
        request.session_id,
        request.input_path,
    )

    try:
        result = await run_etl_pipeline(request)
        logger.info(
            "ETL Skill termine — session=%s, status=%s, rows=%d→%d",
            request.session_id,
            result.status,
            result.rows_before,
            result.rows_after,
        )
        return result

    except FileNotFoundError as exc:
        logger.error("Fichier introuvable : %s", exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    except ValueError as exc:
        logger.warning("Parametres invalides : %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except Exception as exc:
        logger.exception("Erreur interne ETL Skill")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur interne du ETL Skill : {exc}",
        ) from exc