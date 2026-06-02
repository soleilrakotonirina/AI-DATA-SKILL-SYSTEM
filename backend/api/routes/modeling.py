"""
backend/api/routes/modeling.py
Endpoint FastAPI du Modeling Skill.

Expose POST /api/modeling/train — valide via Pydantic, execute le pipeline
ML complet et retourne ModelingResponse avec chart_ids Directus.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from schemas.modeling import ModelingRequest, ModelingResponse
from skills.modeling_skill.scripts.logic import run_modeling_pipeline

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/modeling/train",
    response_model=ModelingResponse,
    summary="Lancer l'entrainement ML automatique",
    description=(
        "Execute le Modeling Skill complet : detection du type de probleme, "
        "feature engineering, recommandation Gemini, entrainement multi-algorithmes, "
        "cross-validation, hyperparameter tuning, sauvegarde pipeline joblib, "
        "push confusion matrix + ROC vers Directus (charts), "
        "generation Model Card MDX vers Directus (reports_mdx)."
    ),
    tags=["Modeling Skill"],
)
async def run_modeling_skill(
    request: ModelingRequest,
) -> ModelingResponse:
    """
    Lance le Modeling Skill complet.

    Args:
        request: ModelingRequest valide via Pydantic.

    Returns:
        ModelingResponse avec best_model_path, metriques,
        report_mdx_id, confusion_matrix_chart_id, roc_chart_id.

    Raises:
        HTTPException 404: Fichier dataset introuvable.
        HTTPException 422: Parametres invalides (gere par Pydantic).
        HTTPException 500: Erreur interne d'execution.
    """
    logger.info(
        "Modeling Skill demarre — session=%s — cible=%s — type=%s",
        request.session_id,
        request.target_column,
        request.problem_type,
    )

    try:
        result = await run_modeling_pipeline(request)

        logger.info(
            "Modeling Skill termine — session=%s — modele=%s — status=%s",
            request.session_id,
            result.best_model_name,
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
        logger.error("Erreur Modeling Skill : %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erreur interne du Modeling Skill",
        )