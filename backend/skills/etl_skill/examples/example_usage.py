"""
ETL Skill — Exemple d'utilisation complet.

Cree un DataFrame synthetique avec nullites, doublons, outliers
et types incorrects, puis execute le pipeline ETL complet via
l'API Pydantic ETLRequest et la fonction async run_etl_pipeline.

Verifie que :
- La reponse ETLResponse est bien valide
- Les metriques avant/apres sont coherentes
- Le rapport MDX est genere (mocke si pas de serveur Directus)
- Le script ETL reproductible est cree

Execution :
    python -m skills.etl_skill.examples.example_usage
"""

from __future__ import annotations

import asyncio
import logging
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np
import pandas as pd

# Ajout de backend/ au path Python
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from schemas.etl import ETLRequest, ETLResponse
from skills.etl_skill.scripts.logic import run_etl_pipeline


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s : %(message)s",
)
logger = logging.getLogger("etl_example")


def create_synthetic_dataset(output_path: Path) -> Path:
    """
    Cree un dataset synthetique avec tous les problemes de qualite courants.

    Problemes intentionnels injectes :
    - 10% de valeurs manquantes aleatoires
    - 5% de doublons
    - Outliers dans la colonne 'salary'
    - Colonne 'age' stockee comme string
    - Colonne 'city' avec variantes de casse

    Args:
        output_path: Chemin du CSV de sortie.

    Returns:
        Chemin du fichier cree.
    """
    np.random.seed(42)
    n = 200

    data = {
        "customer_id": range(1, n + 1),
        "name": [f"Customer_{i}" for i in range(1, n + 1)],
        "age": [str(np.random.randint(18, 65)) for _ in range(n)],
        "city": np.random.choice(
            ["paris", "Paris", "PARIS", "Lyon", "lyon", "marseille"], n,
        ),
        "category": np.random.choice(["Premium", "Standard", "Basic"], n),
        "salary": np.concatenate([
            np.random.normal(45000, 10000, n - 5),
            [500000, 600000, 700000, -5000, -10000],
        ]),
        "score": np.random.uniform(0, 100, n),
        "signup_date": pd.date_range("2020-01-01", periods=n, freq="3D").astype(str),
        "churn": np.random.choice([0, 1], n, p=[0.8, 0.2]),
    }

    df = pd.DataFrame(data)

    # Injecter 10% de valeurs manquantes
    for col in ["age", "city", "salary", "score"]:
        null_mask = np.random.random(n) < 0.10
        df.loc[null_mask, col] = None

    # Injecter 5% de doublons
    n_dup = int(n * 0.05)
    duplicate_rows = df.sample(n_dup, random_state=42)
    df = pd.concat([df, duplicate_rows], ignore_index=True)

    df.to_csv(output_path, index=False)
    logger.info(
        "Dataset synthetique cree : %s (%d lignes × %d colonnes)",
        output_path, *df.shape,
    )
    return output_path


async def run_example() -> None:
    """Execute l'exemple complet ETL Skill."""
    print("\n" + "=" * 70)
    print("  ETL SKILL — EXEMPLE COMPLET")
    print("=" * 70 + "\n")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        data_dir = tmp_path / "data" / "raw"
        data_dir.mkdir(parents=True)

        # Etape 1 : Creer le dataset synthetique
        print("Creation du dataset synthetique...")
        csv_path = data_dir / "synthetic_customers.csv"
        create_synthetic_dataset(csv_path)

        # Etape 2 : Afficher l'etat initial
        df_raw = pd.read_csv(csv_path)
        print(f"\nDataset AVANT nettoyage :")
        print(f"  Shape         : {df_raw.shape[0]} lignes x {df_raw.shape[1]} colonnes")
        print(f"  Nulls         : {df_raw.isnull().sum().sum()} valeurs manquantes")
        print(f"  Doublons      : {df_raw.duplicated().sum()}")
        print(f"  Type 'age'    : {df_raw['age'].dtype} (devrait etre int)")
        print(f"  Max salary    : {df_raw['salary'].max():,.0f} (outlier probable)")

        # Etape 3 : Construire l'ETLRequest Pydantic
        request = ETLRequest(
            session_id="example_session_001",
            input_path=str(csv_path),
            missing_strategy="auto",
            fill_mode="smart",
            outlier_action="cap",
            outlier_method="iqr",
            encode_method="auto",
            scale_method="standard",
            generate_script=True,
            dimensional_modeling=False,
            target_column="churn",
            columns_to_exclude=["customer_id"],
        )

        print(f"\nETLRequest construit et valide par Pydantic :")
        print(f"  session_id     : {request.session_id}")
        print(f"  target_column  : {request.target_column}")
        print(f"  excludes       : {request.columns_to_exclude}")

        # Etape 4 : Mocker Directus (pas de serveur necessaire pour la demo)
        print("\nExecution du pipeline ETL (Directus mocke)...")
        with patch(
            "src.utils.directus_client.push_report_mdx",
            new_callable=AsyncMock,
            return_value="mock_mdx_id_a1b2c3d4",
        ), patch(
            "src.utils.directus_client.append_pipeline_log",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response: ETLResponse = await run_etl_pipeline(request)

        # Etape 5 : Verifier les resultats
        print(f"\nStatut final : {response.status.upper()}")

        if response.status == "error":
            print(f"\nErreur critique : {response.error_message}")
            return

        # Affichage comparatif avant/apres
        print(f"\nDataset APRES nettoyage :")
        print(f"  Shape         : {response.rows_after} lignes x {response.cols_after} colonnes")
        print(f"  Variation     : {response.rows_before} -> {response.rows_after} lignes")
        print(f"  Nulls supp.   : {response.nulls_removed} valeurs manquantes traitees")
        print(f"  Doublons supp.: {response.duplicates_removed} lignes dupliquees")

        # Fichiers generes
        print(f"\nFichiers generes :")
        if response.script_path:
            print(f"  Script ETL : {Path(response.script_path).name}")
        if response.report_md_path:
            print(f"  Rapport MD : {Path(response.report_md_path).name}")
        if response.report_mdx_id:
            print(f"  MDX Directus : {response.report_mdx_id}")

        # Journal des transformations
        print(f"\nTransformations appliquees : {len(response.transformation_log)}")
        for i, entry in enumerate(response.transformation_log[:5], 1):
            etape = entry.get("etape", "unknown")
            duration = entry.get("duration_ms", 0)
            print(f"  {i}. {etape} ({duration:.0f}ms)")
        if len(response.transformation_log) > 5:
            print(f"  ... et {len(response.transformation_log) - 5} autres etapes")

        # Erreurs non bloquantes
        if response.errors:
            print(f"\nAvertissements ({len(response.errors)}) :")
            for e in response.errors[:3]:
                print(f"  - {e}")

        # Verifications finales
        print(f"\nVerifications :")
        assert response.skill == "ETL", "Le champ skill doit etre 'ETL'"
        assert response.status in ("success", "error"), "Status doit etre success ou error"
        assert response.session_id == request.session_id, "session_id doit etre preserve"
        assert response.rows_before > 0, "rows_before doit etre > 0"
        assert response.report_mdx_id is not None, "report_mdx_id doit etre defini (Directus mocke)"
        print("  Toutes les verifications passent !")

    print("\n" + "=" * 70)
    print("  EXEMPLE TERMINE AVEC SUCCES")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(run_example())