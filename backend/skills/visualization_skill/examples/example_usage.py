"""
backend/skills/visualization_skill/examples/example_usage.py
Exemple d'utilisation standalone du Visualization Skill.

Peut etre execute directement sans passer par FastAPI.
Directus est mocke si DIRECTUS_TOKEN n'est pas configure.

Usage :
    cd backend
    uv run --env-file .env python skills/visualization_skill/examples/example_usage.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Ajouter le backend au path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s : %(message)s",
)
logger = logging.getLogger(__name__)


async def run_example() -> None:
    """Execute un exemple complet du Visualization Skill."""
    from schemas.visualization import VisualizationRequest
    from skills.visualization_skill.scripts.logic import run_visualization_pipeline

    # ── Trouver un dataset disponible ─────────────────────────────────────────
    candidates = [
        "data/processed/exportations_madagascar/core_data/exportations_dirty.csv",
        "data/processed/Donnees_Universitaires_4Tables_SALE/core_data/Etudiants.csv",
        "data/raw/exportations_madagascar.xlsx",
    ]
    dataset_path = None
    for c in candidates:
        if Path(c).exists():
            dataset_path = c
            break

    if dataset_path is None:
        # Creer un dataset synthetique pour la demo
        import numpy as np
        import pandas as pd

        logger.info("Aucun dataset disponible — creation d'un dataset synthetique")
        np.random.seed(42)
        n = 300
        df = pd.DataFrame({
            "age":      np.random.normal(35, 10, n).clip(18, 80),
            "salaire":  np.random.normal(50000, 15000, n).clip(20000, 100000),
            "region":   np.random.choice(["Analamanga", "SAVA", "Diana", "Boeny", "Itasy"], n),
            "sexe":     np.random.choice(["M", "F"], n),
            "churn":    np.random.choice([0, 1], n, p=[0.8, 0.2]),
        })
        Path("data/raw").mkdir(parents=True, exist_ok=True)
        dataset_path = "data/raw/synthetic_demo.csv"
        df.to_csv(dataset_path, index=False)
        logger.info("Dataset synthetique cree : %s", dataset_path)

    # ── Construire la requete ──────────────────────────────────────────────────
    request = VisualizationRequest(
        session_id="example_session_viz",
        dataset_path=dataset_path,
        target_column=None,
        question=None,
        export_formats=["html"],       # Pas de PNG pour eviter kaleido
        output_dir="outputs/charts/example",
        generate_report=True,
        gemini_comments=bool(os.getenv("GEMINI_API_KEY")),  # Gemini si cle disponible
    )

    logger.info("VisualizationRequest construit :")
    logger.info("  dataset_path  : %s", request.dataset_path)
    logger.info("  session_id    : %s", request.session_id)
    logger.info("  gemini        : %s", request.gemini_comments)

    # ── Executer le pipeline (Directus mocke si pas de token) ──────────────────
    directus_configured = bool(os.getenv("DIRECTUS_TOKEN"))

    if directus_configured:
        logger.info("Directus configure — push reel")
        response = await run_visualization_pipeline(request)
    else:
        logger.info("Directus non configure — simulation avec mocks")
        with (
            patch(
                "skills.visualization_skill.scripts.logic.push_chart",
                new_callable=AsyncMock,
                return_value="mock-chart-id-001",
            ),
            patch(
                "skills.visualization_skill.scripts.logic.push_report_mdx",
                new_callable=AsyncMock,
                return_value="mock-report-id-001",
            ),
        ):
            response = await run_visualization_pipeline(request)

    # ── Afficher les resultats ─────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("VISUALIZATION SKILL — Resultats")
    print("=" * 60)
    print(f"Status       : {response.status}")
    print(f"Session      : {response.session_id}")
    print(f"Charts       : {len(response.charts)} graphiques generes")
    print(f"report_mdx_id: {response.report_mdx_id or '(non publie)'}")
    print(f"eda_report   : {response.eda_report_path or '(non genere)'}")
    print(f"Erreurs      : {len(response.errors)}")

    if response.charts:
        print("\nGraphiques :")
        for chart in response.charts:
            cid = chart.chart_id or "(mock)"
            print(f"  [{chart.chart_type:12s}] {chart.title[:40]:40s} chart_id={cid}")

    if response.gemini_comments:
        print("\nCommentaires Gemini (extrait) :")
        for title, comment in list(response.gemini_comments.items())[:2]:
            print(f"\n  {title} :")
            print(f"  {comment[:150]}...")

    if response.errors:
        print("\nErreurs non bloquantes :")
        for err in response.errors:
            print(f"  - {err}")

    print("\n" + "=" * 60)

    # Afficher les stats EDA
    numeric_stats = response.stats.get("numeric_stats", {})
    if numeric_stats:
        print("\nStatistiques EDA (premieres colonnes numeriques) :")
        for col, s in list(numeric_stats.items())[:3]:
            if s.get("mean") is not None:
                print(
                    f"  {col:20s} : mean={s['mean']:.2f}, "
                    f"std={s['std']:.2f}, "
                    f"min={s['min']:.2f}, max={s['max']:.2f}"
                )

    if response.status == "success":
        print("\nVisualization Skill : SUCCES")
        print("Prochaine etape → Modeling Skill (session 2.3)")
    else:
        print(f"\nVisualization Skill : ERREUR — {response.error_message}")


if __name__ == "__main__":
    asyncio.run(run_example())