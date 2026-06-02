"""
backend/schemas/modeling.py
Schemas Pydantic v2 pour le Modeling Skill.

Definit le contrat strict entre Next.js, FastAPI et le moteur Python :
- ModelingRequest  : parametres d'entree valides par FastAPI avant execution
- ModelingResponse : structure de sortie garantie retournee a Next.js
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ModelingRequest(BaseModel):
    """
    Parametres d'entree du Modeling Skill.

    Recus depuis Next.js via POST /api/modeling/train ou depuis
    executor.py (orchestrateur Gemini) via le plan JSON.

    Attributes:
        session_id       : Identifiant unique de session Directus.
        dataset_path     : Chemin du dataset propre (output ETL Skill).
        target_column    : Colonne cible a predire.
        problem_type     : Type de probleme ML (auto-detecte si 'auto').
        cv_folds         : Nombre de folds pour la cross-validation.
        test_size        : Proportion du jeu de test (0.0 < test_size < 1.0).
        tune_best_model  : Activer le tuning hyperparametrique du meilleur modele.
        handle_imbalance : Strategie de gestion du desequilibre de classes.
        output_dir       : Dossier de sauvegarde du pipeline serialise.
        encoders         : Encodeurs du ETL Skill (evite data leakage).
        scalers          : Scalers du ETL Skill (evite data leakage).
    """

    session_id: str = Field(
        ...,
        min_length=1,
        description="Identifiant unique de session Directus",
    )
    dataset_path: str = Field(
        ...,
        min_length=1,
        description="Chemin du dataset propre (output ETL Skill)",
    )
    target_column: str = Field(
        ...,
        min_length=1,
        description="Colonne cible a predire",
    )
    problem_type: Literal[
        "auto",
        "binary_classification",
        "multiclass_classification",
        "regression",
        "clustering",
    ] = Field(
        default="auto",
        description="Type de probleme ML — auto = detection automatique",
    )
    cv_folds: int = Field(
        default=5,
        ge=2,
        le=20,
        description="Nombre de folds cross-validation",
    )
    test_size: float = Field(
        default=0.2,
        gt=0.0,
        lt=1.0,
        description="Proportion du jeu de test (0.05 a 0.5)",
    )
    tune_best_model: bool = Field(
        default=True,
        description="Activer RandomizedSearchCV sur le meilleur modele",
    )
    handle_imbalance: Literal["auto", "smote", "class_weight", "none"] = Field(
        default="auto",
        description="Strategie desequilibre : auto=SMOTE si ratio>3, class_weight, none",
    )
    output_dir: str = Field(
        default="models/",
        description="Dossier de sauvegarde du pipeline serialise (.pkl)",
    )
    encoders: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Encodeurs du ETL Skill a reutiliser (evite data leakage)",
    )
    scalers: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Scalers du ETL Skill a reutiliser (evite data leakage)",
    )

    @field_validator("session_id", "dataset_path", "target_column")
    @classmethod
    def not_empty(cls, v: str) -> str:
        """Verifie que les champs obligatoires ne sont pas vides."""
        if not v.strip():
            raise ValueError("Ce champ ne peut pas etre vide ou uniquement des espaces")
        return v.strip()

    model_config = {
        "json_schema_extra": {
            "example": {
                "session_id":      "user_42_2025-06-01_14-30-22",
                "dataset_path":    "data/processed/clients/core_data/clients.csv",
                "target_column":   "churn",
                "problem_type":    "auto",
                "cv_folds":        5,
                "test_size":       0.2,
                "tune_best_model": True,
                "handle_imbalance": "auto",
                "output_dir":      "models/",
                "encoders":        None,
                "scalers":         None,
            }
        }
    }


class ModelingResponse(BaseModel):
    """
    Structure de sortie du Modeling Skill.

    Retournee par FastAPI a Next.js apres execution du pipeline.
    Contient le meilleur modele, les metriques, les IDs Directus
    des graphiques d'evaluation et de la Model Card MDX.

    Attributes:
        skill                      : Toujours "Modeling".
        session_id                 : ID de session Directus.
        status                     : "success" si pipeline complet, "error" si echec.
        problem_type               : Type de probleme detecte.
        best_model_name            : Nom du meilleur algorithme.
        best_model_path            : Chemin du pipeline .pkl serialise.
        metrics                    : Metriques du meilleur modele.
        all_models_results         : Resultats de tous les modeles evalues.
        model_card_path            : Chemin local de la Model Card MDX.
        report_mdx_id              : ID de la Model Card MDX dans Directus.
        confusion_matrix_chart_id  : ID du chart confusion matrix dans Directus.
        roc_chart_id               : ID du chart ROC dans Directus (binary seulement).
        feature_importance         : Importance des features du meilleur modele.
        errors                     : Erreurs non bloquantes rencontrees.
        error_message              : Message d'erreur critique si status='error'.
    """

    skill: str = Field(default="Modeling", description="Identifiant du Skill")
    session_id: str = Field(..., description="ID de session Directus")
    status: Literal["success", "error"] = Field(
        ..., description="success=pipeline complet, error=echec critique"
    )
    problem_type: Optional[str] = Field(
        default=None, description="Type de probleme ML detecte"
    )
    best_model_name: Optional[str] = Field(
        default=None, description="Nom du meilleur algorithme"
    )
    best_model_path: Optional[str] = Field(
        default=None, description="Chemin du pipeline .pkl serialise"
    )
    metrics: Dict[str, Any] = Field(
        default_factory=dict, description="Metriques du meilleur modele"
    )
    all_models_results: List[Dict[str, Any]] = Field(
        default_factory=list, description="Resultats de tous les modeles evalues"
    )
    model_card_path: Optional[str] = Field(
        default=None, description="Chemin local de la Model Card MDX"
    )
    report_mdx_id: Optional[str] = Field(
        default=None, description="ID de la Model Card MDX dans Directus (reports_mdx)"
    )
    confusion_matrix_chart_id: Optional[str] = Field(
        default=None,
        description="ID du chart confusion matrix dans Directus (charts)",
    )
    roc_chart_id: Optional[str] = Field(
        default=None,
        description="ID du chart ROC dans Directus (charts) — binary classification uniquement",
    )
    feature_importance: Dict[str, Any] = Field(
        default_factory=dict, description="Importance des features du meilleur modele"
    )
    errors: List[str] = Field(
        default_factory=list, description="Erreurs non bloquantes"
    )
    error_message: Optional[str] = Field(
        default=None, description="Message d'erreur critique si status='error'"
    )