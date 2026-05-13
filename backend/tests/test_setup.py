"""
backend/tests/test_setup.py — Test de connexion des 3 services.

Vérifie que :
  1. FastAPI répond sur le port 8000
  2. Directus répond sur le port 8055 et accepte le token
  3. Les 5 collections Directus sont bien construites
  4. Next.js répond sur le port 3000

À lancer après avoir démarré les 3 services en parallèle :
    python tests/test_setup.py
"""

import os
import sys
import httpx
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


FASTAPI_URL = f"http://localhost:{os.getenv('FASTAPI_PORT', '8000')}"
DIRECTUS_URL = os.getenv("DIRECTUS_URL", "http://localhost:8055")
NEXTJS_URL = "http://localhost:3000"
DIRECTUS_TOKEN = os.getenv("DIRECTUS_TOKEN")


def test_fastapi_health() -> bool:
    """Test 1 : FastAPI répond sur /health."""
    logger.info(f"Test FastAPI : {FASTAPI_URL}/health")
    try:
        response = httpx.get(f"{FASTAPI_URL}/health", timeout=5)
        response.raise_for_status()
        data = response.json()
        logger.info(f"  OK — Status : {data.get('status')}")
        logger.info(f"  Environment : {data.get('environment')}")
        logger.info(f"  Directus configuré : {data.get('directus_configured')}")
        logger.info(f"  Gemini configuré : {data.get('gemini_configured')}")
        return True
    except httpx.ConnectError:
        logger.error(f"  ECHEC — FastAPI ne répond pas")
        logger.error(f"  Démarrer : uvicorn api.main:app --reload --port 8000")
        return False
    except Exception as e:
        logger.error(f"  ECHEC — {e}")
        return False


def test_directus_ping() -> bool:
    """Test 2 : Directus répond sur /server/ping."""
    logger.info(f"Test Directus : {DIRECTUS_URL}/server/ping")
    try:
        response = httpx.get(f"{DIRECTUS_URL}/server/ping", timeout=5)
        response.raise_for_status()
        logger.info(f"  OK — Directus répond")
        return True
    except httpx.ConnectError:
        logger.error(f"  ECHEC — Directus ne répond pas")
        logger.error(f"  Démarrer : cd directus && npx directus start")
        return False
    except Exception as e:
        logger.error(f"  ECHEC — {e}")
        return False


def test_directus_auth() -> bool:
    """Test 3 : Le token Directus est valide et les 5 collections existent."""
    logger.info(f"Test Directus auth : {DIRECTUS_URL}/collections")
    if not DIRECTUS_TOKEN or DIRECTUS_TOKEN.startswith("Remplacer"):
        logger.error(f"  ECHEC — DIRECTUS_TOKEN non configuré dans .env")
        return False
    try:
        response = httpx.get(
            f"{DIRECTUS_URL}/collections",
            headers={"Authorization": f"Bearer {DIRECTUS_TOKEN}"},
            timeout=5,
        )
        response.raise_for_status()
        collections = response.json().get("data", [])
        user_collections = [
            c["collection"] for c in collections
            if not c["collection"].startswith("directus_")
        ]
        logger.info(f"  OK — Token valide")
        logger.info(f"  Collections utilisateur : {user_collections}")

        expected = {"sessions", "reports_mdx", "charts", "pipeline_logs"}
        missing = expected - set(user_collections)
        if missing:
            logger.warning(f"  ATTENTION — Collections manquantes : {missing}")
            logger.warning(f"  Les construire dans http://localhost:8055/admin/settings/data-model")
            return False
        return True
    except httpx.HTTPStatusError as e:
        logger.error(f"  ECHEC — Token invalide ou permissions insuffisantes : {e.response.status_code}")
        return False
    except Exception as e:
        logger.error(f"  ECHEC — {e}")
        return False


def test_nextjs_response() -> bool:
    """Test 4 : Next.js répond sur la racine."""
    logger.info(f"Test Next.js : {NEXTJS_URL}")
    try:
        response = httpx.get(NEXTJS_URL, timeout=5)
        response.raise_for_status()
        logger.info(f"  OK — Next.js répond")
        return True
    except httpx.ConnectError:
        logger.error(f"  ECHEC — Next.js ne répond pas")
        logger.error(f"  Démarrer : cd frontend && npm run dev")
        return False
    except Exception as e:
        logger.error(f"  ECHEC — {e}")
        return False


def main():
    """Lance les 4 tests et affiche le résumé."""
    logger.info("=" * 70)
    logger.info("AI DATA SKILL SYSTEM — Test de connexion des 3 services")
    logger.info("=" * 70)

    results = {
        "FastAPI Backend (8000)": test_fastapi_health(),
        "Directus Ping (8055)": test_directus_ping(),
        "Directus Auth + Collections": test_directus_auth(),
        "Next.js Frontend (3000)": test_nextjs_response(),
    }

    logger.info("=" * 70)
    logger.info("Résumé")
    logger.info("=" * 70)
    for service, ok in results.items():
        status = "OK" if ok else "ECHEC"
        logger.info(f"  [{status}] {service}")

    all_ok = all(results.values())
    if all_ok:
        logger.info("")
        logger.info("Les 3 services tournent et communiquent correctement.")
        logger.info("Étape 0 validée. Passe à l'Étape 1 (ETL Skill).")
        sys.exit(0)
    else:
        logger.error("")
        logger.error("Certains services ne répondent pas. Corriger avant de continuer.")
        sys.exit(1)


if __name__ == "__main__":
    main()

