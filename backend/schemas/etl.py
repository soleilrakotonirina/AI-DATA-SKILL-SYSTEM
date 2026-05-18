"""
backend/schemas/etl.py
Schemas Pydantic v2 pour le ETL Skill.

Definit le contrat strict entre Next.js, FastAPI et le moteur Python :
- ETLRequest  : parametres d'entree valides par FastAPI avant execution
- ETLResponse : structure de sortie garantie retournee a Next.js

Usage :
    from schemas.etl import ETLRequest, ETLResponse
"""

from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ETLRequest(BaseModel):
    """
    Parametres d'entree du ETL Skill.

    Recus depuis Next.js via POST /api/etl/run ou depuis
    executor.py (orchestrateur Gemini) via le plan JSON.

    Attributes:
        session_id      : Identifiant unique de session (cree dans Directus).
        input_path      : Chemin du fichier source relatif a la racine backend/.
    input_url: Optional[str] = None  # URL REST, CSV distant, OpenData
        missing_strategy: Strategie d'imputation des valeurs manquantes.
        fill_mode       : Mode de remplissage pour les imputations.
        outlier_action  : Action appliquee aux valeurs aberrantes detectees.
        outlier_method  : Methode de detection des outliers.
        encode_method   : Methode d'encodage des variables categorielles.
        scale_method    : Methode de normalisation des variables numeriques.
        generate_script : Generer un script ETL Python reproductible.
        dimensional_modeling : Construire un Star Schema depuis une table plate.
        target_column   : Colonne cible ML a proteger des transformations.
        columns_to_exclude  : Colonnes a exclure de toutes les transformations.
    """

    session_id: str = Field(
        ...,
        description="Identifiant unique de session cree dans Directus",
        min_length=1,
    )
    input_path: Optional[str] = Field(
        default=None,
        description="Chemin du fichier source local (CSV, Excel, JSON, Parquet) — optionnel si input_url",
    )
    input_url: Optional[str] = Field(
        default=None,
        description="URL REST distante (alternative a input_path)",
    )
    missing_strategy: Literal["auto", "constant", "drop"] = Field(
        default="auto",
        description="auto=mediane/mode, constant=N/D/0, drop=suppression lignes",
    )
    fill_mode: Literal["smart", "constant"] = Field(
        default="smart",
        description="smart=adapte au type, constant=valeurs fixes N/D ou 0",
    )
    outlier_action: Literal["cap", "remove", "flag"] = Field(
        default="cap",
        description="cap=capping bornes, remove=suppression ligne, flag=colonne indicateur",
    )
    outlier_method: Literal["iqr", "zscore"] = Field(
        default="iqr",
        description="iqr=1.5xIQR (asymetrique), zscore=|z|>3 (distribution normale)",
    )
    encode_method: Literal["auto", "label", "onehot"] = Field(
        default="auto",
        description="auto=label si cardinalite<=10 sinon onehot, label=LabelEncoder, onehot=OneHotEncoder",
    )
    scale_method: Literal["standard", "minmax"] = Field(
        default="standard",
        description="standard=StandardScaler (mu=0 sigma=1), minmax=MinMaxScaler [0,1]",
    )
    generate_script: bool = Field(
        default=True,
        description="Generer un script Python autonome reproduisant le pipeline",
    )
    dimensional_modeling: bool = Field(
        default=False,
        description="Construire un Star Schema (tables de faits + dimensions)",
    )
    target_column: Optional[str] = Field(
        default=None,
        description="Colonne cible ML exclue des encodages et scalings",
    )
    columns_to_exclude: List[str] = Field(
        default_factory=list,
        description="Colonnes a exclure de toutes les transformations",
    )

    @field_validator("input_path")
    @classmethod
    def input_path_not_empty(cls, v):
        """Verifie que le chemin n'est pas vide apres strip."""
        if v is not None and not v.strip():
            raise ValueError("input_path ne peut pas etre vide ou contenir uniquement des espaces")
        return v.strip() if v else v

    @field_validator("session_id")
    @classmethod
    def session_id_not_empty(cls, v: str) -> str:
        """Verifie que le session_id n'est pas vide apres strip."""
        if v is not None and not v.strip():
            raise ValueError("session_id ne peut pas etre vide")
        return v.strip() if v else v

    model_config = {
        "json_schema_extra": {
            "example": {
                "session_id": "user_42_2025-06-01_14-30-22",
                "input_path": "data/raw/customers.csv",
                "missing_strategy": "auto",
                "fill_mode": "smart",
                "outlier_action": "cap",
                "outlier_method": "iqr",
                "encode_method": "auto",
                "scale_method": "standard",
                "generate_script": True,
                "dimensional_modeling": False,
                "target_column": "churn",
                "columns_to_exclude": ["customer_id"],
            }
        }
    }


class ETLResponse(BaseModel):
    """
    Structure de sortie du ETL Skill.

    Retournee par FastAPI a Next.js apres execution du pipeline.
    Contient les metriques avant/apres, les chemins des fichiers generes,
    et l'ID du rapport MDX publie dans Directus.

    Attributes:
        skill              : Toujours "ETL" — identifie le module source.
        session_id         : Identifiant de session Directus.
        status             : "success" si pipeline complet, "error" si echec critique.
        rows_before        : Nombre de lignes avant nettoyage.
        rows_after         : Nombre de lignes apres nettoyage.
        cols_before        : Nombre de colonnes avant nettoyage.
        cols_after         : Nombre de colonnes apres nettoyage.
        nulls_removed      : Nombre de valeurs manquantes traitees.
        duplicates_removed : Nombre de doublons supprimes.
        script_path        : Chemin du script ETL reproductible genere.
        report_md_path     : Chemin du rapport Markdown local genere.
        report_mdx_id      : ID du rapport MDX publie dans Directus.
        transformation_log : Journal de toutes les etapes executees.
        errors             : Liste des erreurs non bloquantes rencontrees.
        error_message      : Message d'erreur critique (si status='error').
    """

    skill: str = Field(default="ETL", description="Identifiant du Skill source")
    session_id: str = Field(..., description="Identifiant de session Directus")
    status: Literal["success", "error"] = Field(
        ..., description="success=pipeline complet, error=echec critique"
    )
    rows_before: int = Field(default=0, description="Lignes avant nettoyage", ge=0)
    rows_after: int = Field(default=0, description="Lignes apres nettoyage", ge=0)
    cols_before: int = Field(default=0, description="Colonnes avant nettoyage", ge=0)
    cols_after: int = Field(default=0, description="Colonnes apres nettoyage", ge=0)
    nulls_removed: int = Field(default=0, description="Valeurs manquantes traitees", ge=0)
    duplicates_removed: int = Field(default=0, description="Doublons supprimes", ge=0)
    script_path: Optional[str] = Field(
        default=None, description="Chemin du script ETL Python reproductible"
    )
    report_md_path: Optional[str] = Field(
        default=None, description="Chemin du rapport Markdown local"
    )
    report_mdx_id: Optional[str] = Field(
        default=None, description="ID du rapport MDX publie dans Directus"
    )
    transformation_log: List[Any] = Field(
        default_factory=list,
        description="Journal des etapes : {etape, fonction, params, rows_before, rows_after, duration_ms}",
    )
    errors: List[str] = Field(
        default_factory=list,
        description="Erreurs non bloquantes — pipeline continue malgre elles",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Message d'erreur critique (renseigne si status='error')",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "skill": "ETL",
                "session_id": "user_42_2025-06-01_14-30-22",
                "status": "success",
                "rows_before": 210,
                "rows_after": 190,
                "cols_before": 9,
                "cols_after": 9,
                "nulls_removed": 45,
                "duplicates_removed": 10,
                "script_path": "outputs/rapport_etl/customers/etl_script_customers.py",
                "report_md_path": "outputs/rapport_etl/customers/etl_report_customers.md",
                "report_mdx_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "transformation_log": [],
                "errors": [],
                "error_message": None,
            }
        }
    }