
#!/bin/bash
# =============================================================================
# setup_backend_structure.sh
# Génère toute l'arborescence backend pour AI DATA SKILL SYSTEM.
# Lancement : bash setup_backend_structure.sh (depuis la racine du projet)
# =============================================================================

set -e

echo "Génération de la structure backend AI DATA SKILL SYSTEM..."

# ── Liste des 7 Skills ──────────────────────────────────────────────────
SKILLS=(
    "etl_skill"
    "visualization_skill"
    "modeling_skill"
    "prediction_skill"
    "analysis_skill"
    "ml_explanation_skill"
    "nextjs_builder_skill"
)

# ── Structure de chaque Skill ───────────────────────────────────────────
for skill in "${SKILLS[@]}"; do
    echo "  → Skill : $skill"
    mkdir -p "backend/skills/$skill/core"
    mkdir -p "backend/skills/$skill/scripts"
    mkdir -p "backend/skills/$skill/examples"

    # Fichiers obligatoires (vides au départ, remplis à chaque étape)
    touch "backend/skills/$skill/SKILL.md"
    touch "backend/skills/$skill/api-guide.md"
    touch "backend/skills/$skill/scripts/main.py"
    touch "backend/skills/$skill/scripts/logic.py"
    touch "backend/skills/$skill/scripts/helpers.py"
    touch "backend/skills/$skill/scripts/__init__.py"
    touch "backend/skills/$skill/core/__init__.py"
    touch "backend/skills/$skill/examples/example_usage.py"
    touch "backend/skills/$skill/examples/sample_config.json"
    touch "backend/skills/$skill/examples/expected_output.md"
    touch "backend/skills/$skill/__init__.py"
done

# ── API FastAPI ─────────────────────────────────────────────────────────
echo "  → API FastAPI"
mkdir -p backend/api/routes
touch backend/api/__init__.py
touch backend/api/routes/__init__.py

# ── Schemas Pydantic ────────────────────────────────────────────────────
echo "  → Schémas Pydantic"
mkdir -p backend/schemas
touch backend/schemas/__init__.py

# ── LLM Orchestrator ────────────────────────────────────────────────────
echo "  → LLM Orchestrator (Gemini)"
mkdir -p backend/llm_orchestrator
touch backend/llm_orchestrator/__init__.py
touch backend/llm_orchestrator/router.py
touch backend/llm_orchestrator/planner.py
touch backend/llm_orchestrator/executor.py
touch backend/llm_orchestrator/prompt_engine.py

# ── Utilitaires ─────────────────────────────────────────────────────────
echo "  → Utilitaires (src/utils)"
mkdir -p backend/src/utils
touch backend/src/__init__.py
touch backend/src/utils/__init__.py
touch backend/src/utils/logger.py
touch backend/src/utils/config.py
touch backend/src/utils/helpers.py
touch backend/src/utils/directus_client.py

# ── Données et sorties ──────────────────────────────────────────────────
echo "  → Dossiers de données et sorties"
mkdir -p backend/data/raw backend/data/processed backend/data/external
mkdir -p backend/models backend/outputs

touch backend/data/raw/.gitkeep
touch backend/data/processed/.gitkeep
touch backend/data/external/.gitkeep
touch backend/models/.gitkeep
touch backend/outputs/.gitkeep

# ── Tests ───────────────────────────────────────────────────────────────
echo "  → Tests unitaires"
mkdir -p backend/tests
touch backend/tests/__init__.py
touch backend/tests/test_etl.py
touch backend/tests/test_visualization.py
touch backend/tests/test_modeling.py
touch backend/tests/test_prediction.py
touch backend/tests/test_ml_explanation.py
touch backend/tests/test_analysis.py
touch backend/tests/test_endpoints.py
touch backend/tests/test_pydantic_schemas.py
touch backend/tests/test_directus_client.py

# ── Notebooks ───────────────────────────────────────────────────────────
echo "  → Notebooks Jupyter"
mkdir -p backend/notebooks
touch backend/notebooks/.gitkeep

echo ""
echo "Structure backend générée avec succès."

