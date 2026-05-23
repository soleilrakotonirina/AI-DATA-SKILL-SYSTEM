"""
backend/api/routes/visualization.py
Endpoint FastAPI du Visualization Skill.

Expose POST /api/visualization/eda — valide via Pydantic, execute
le pipeline de visualisation et retourne VisualizationResponse.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from schemas.visualization import VisualizationRequest, VisualizationResponse
from skills.visualization_skill.scripts.logic import run_visualization_pipeline

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/visualization/eda",
    response_model=VisualizationResponse,
    summary="Lancer l'analyse EDA et generer les graphiques",
    description=(
        "Execute le Visualization Skill complet : statistiques EDA, "
        "graphiques Plotly interactifs, commentaires Gemini, rapport MDX. "
        "Stocke les graphiques Plotly JSON dans Directus (collection charts) "
        "et le rapport EDA MDX dans Directus (collection reports_mdx)."
    ),
    tags=["Visualization Skill"],
)
async def run_visualization_skill(
    request: VisualizationRequest,
) -> VisualizationResponse:
    """
    Lance le Visualization Skill complet sur le dataset specifie.

    Args:
        request: VisualizationRequest valide via Pydantic.

    Returns:
        VisualizationResponse avec chart_ids Directus et report_mdx_id.

    Raises:
        HTTPException 404: Fichier dataset introuvable.
        HTTPException 422: Parametres invalides (gere par Pydantic).
        HTTPException 500: Erreur interne d'execution.
    """
    logger.info(
        "Visualization Skill demarre — session=%s — fichier=%s",
        request.session_id,
        request.dataset_path,
    )

    try:
        result = await run_visualization_pipeline(request)
        logger.info(
            "Visualization Skill termine — session=%s — %d graphiques — status=%s",
            request.session_id,
            len(result.charts),
            result.status,
        )
        return result

    except FileNotFoundError as exc:
        logger.error("Fichier non trouve : %s", exc)
        raise HTTPException(status_code=404, detail=str(exc))

    except ValueError as exc:
        logger.warning("Valeur invalide : %s", exc)
        raise HTTPException(status_code=422, detail=str(exc))

    except Exception as exc:
        logger.error("Erreur Visualization Skill : %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erreur interne du Visualization Skill",
        )