"""
backend/schemas/visualization.py
Schemas Pydantic pour le Visualization Skill.

Contrat d'entree/sortie entre Next.js, FastAPI et le Visualization Skill.
Valide automatiquement chaque requete via FastAPI + Pydantic v2.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ChartResult(BaseModel):
    """Metadata d'un graphique stocke dans Directus."""

    chart_id: str = Field(..., description="ID du graphique dans Directus (collection charts)")
    title: str = Field(..., description="Titre du graphique")
    chart_type: str = Field(
        ...,
        description=(
            "Type de graphique : histogram, boxplot, heatmap, "
            "bar_chart, line_chart, scatter, pairplot"
        ),
    )
    columns_involved: List[str] = Field(
        default_factory=list,
        description="Colonnes du dataset utilisees pour ce graphique",
    )


class VisualizationRequest(BaseModel):
    """
    Parametres d'entree du Visualization Skill.

    Recus depuis Next.js via POST /api/visualization/eda ou depuis
    executor.py (orchestrateur Gemini) via le plan JSON.

    Attributes:
        session_id        : Identifiant de session (cree dans Directus a l'Etape 1 ETL).
        dataset_path      : Chemin du dataset propre produit par ETL Skill.
        target_column     : Colonne cible pour l'analyse supervisee (optionnel).
        question          : Question analytique en langage naturel (optionnel).
        export_formats    : Formats d'export des graphiques ['html', 'png'].
        output_dir        : Dossier de sortie des graphiques exportes.
        generate_report   : Generer le rapport EDA MDX et le pousser vers Directus.
        gemini_comments   : Activer les commentaires narratifs Gemini sur chaque graphique.
        columns_to_include: Liste de colonnes a analyser. None = toutes les colonnes.
    """

    session_id: str = Field(..., min_length=1, description="ID de session Directus")
    dataset_path: str = Field(
        ...,
        min_length=1,
        description="Chemin du dataset propre (output ETL Skill)",
    )
    target_column: Optional[str] = Field(
        default=None,
        description="Colonne cible pour analyse supervisee",
    )
    question: Optional[str] = Field(
        default=None,
        description="Question analytique en langage naturel",
    )
    export_formats: List[str] = Field(
        default=["html", "png"],
        description="Formats d'export : html et/ou png",
    )
    output_dir: str = Field(
        default="outputs/charts",
        description="Dossier de sortie pour les graphiques exportes",
    )
    generate_report: bool = Field(
        default=True,
        description="Generer et pousser le rapport EDA MDX vers Directus",
    )
    gemini_comments: bool = Field(
        default=True,
        description="Activer les commentaires Gemini sur chaque graphique",
    )
    columns_to_include: Optional[List[str]] = Field(
        default=None,
        description="Colonnes a analyser. None = toutes les colonnes.",
    )

    @field_validator("session_id")
    @classmethod
    def session_id_not_empty(cls, v: str) -> str:
        """Verifie que session_id n'est pas vide."""
        if not v.strip():
            raise ValueError("session_id ne peut pas etre vide")
        return v.strip()

    @field_validator("dataset_path")
    @classmethod
    def dataset_path_not_empty(cls, v: str) -> str:
        """Verifie que dataset_path n'est pas vide."""
        if not v.strip():
            raise ValueError("dataset_path ne peut pas etre vide")
        return v.strip()

    @field_validator("export_formats")
    @classmethod
    def validate_export_formats(cls, v: List[str]) -> List[str]:
        """Verifie que les formats d'export sont valides."""
        valid = {"html", "png"}
        for fmt in v:
            if fmt not in valid:
                raise ValueError(f"Format invalide : {fmt!r}. Valeurs acceptees : {valid}")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "session_id": "user_42_2025-06-01_14-30-22",
                "dataset_path": "data/processed/exportations_madagascar/core_data/exportations_dirty.csv",
                "target_column": "churn",
                "question": "Quelles regions exportent le plus ?",
                "export_formats": ["html", "png"],
                "output_dir": "outputs/charts",
                "generate_report": True,
                "gemini_comments": True,
                "columns_to_include": None,
            }
        }
    }


class VisualizationResponse(BaseModel):
    """
    Sortie du Visualization Skill.

    Retournee par POST /api/visualization/eda et par run_visualization_pipeline().
    Contient les chart_ids Directus et le report_mdx_id pour lecture depuis Next.js.

    Attributes:
        skill           : Nom du Skill (toujours "Visualization").
        session_id      : ID de session.
        status          : "success" ou "error".
        charts          : Liste des graphiques avec leurs chart_ids Directus.
        stats           : Statistiques EDA calculees.
        eda_report_path : Chemin local du rapport MDX genere.
        report_mdx_id   : ID du rapport MDX dans Directus (collection reports_mdx).
        charts_paths    : {chart_title: {html: path, png: path}} — chemins locaux.
        gemini_comments : {chart_title: commentaire_gemini} — commentaires narratifs.
        errors          : Liste des erreurs non bloquantes.
        error_message   : Message d'erreur principal si status='error'.
    """

    skill: str = Field(default="Visualization", description="Nom du Skill")
    session_id: str = Field(..., description="ID de session")
    status: Literal["success", "error"] = Field(
        ..., description="Statut d'execution"
    )
    charts: List[ChartResult] = Field(
        default_factory=list,
        description="Liste des graphiques avec leurs chart_ids Directus",
    )
    stats: Dict[str, Any] = Field(
        default_factory=dict,
        description="Statistiques EDA calculees",
    )
    eda_report_path: Optional[str] = Field(
        default=None,
        description="Chemin local du rapport MDX genere",
    )
    report_mdx_id: Optional[str] = Field(
        default=None,
        description="ID du rapport MDX dans Directus (collection reports_mdx)",
    )
    charts_paths: Dict[str, Any] = Field(
        default_factory=dict,
        description="{chart_title: {html: path, png: path}}",
    )
    gemini_comments: Dict[str, str] = Field(
        default_factory=dict,
        description="{chart_title: commentaire_gemini}",
    )
    errors: List[str] = Field(
        default_factory=list,
        description="Erreurs non bloquantes",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Message d'erreur principal",
    )