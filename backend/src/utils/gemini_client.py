"""
backend/src/utils/gemini_client.py
Client Gemini avec rotation automatique des cles API.

Lit toutes les cles GEMINI_API_KEY, GEMINI_API_KEY_2, ..., GEMINI_API_KEY_N
depuis les variables d'environnement. Si une cle depasse son quota (erreur 429),
bascule automatiquement sur la cle suivante.

Usage :
    from src.utils.gemini_client import generate_content

    response = generate_content(
        prompt="Analyse ce dataset...",
        temperature=0.2,
    )
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Delai en secondes entre les tentatives de rotation
_RETRY_DELAY = 1.0
# Nombre max de tentatives (toutes les cles confondues)
_MAX_ATTEMPTS = 3


def _load_api_keys() -> list[str]:
    """
    Charge toutes les cles Gemini disponibles depuis os.environ.

    Cherche : GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3, ...
    jusqu'a GEMINI_API_KEY_20. Ignore les cles vides.

    Returns:
        Liste des cles valides dans l'ordre de priorite.
    """
    keys: list[str] = []

    # Cle principale
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if k:
        keys.append(k)

    # Cles de rotation 2 a 20
    for i in range(2, 21):
        k = os.environ.get(f"GEMINI_API_KEY_{i}", "").strip()
        if k:
            keys.append(k)

    return keys


def generate_content(
    prompt: str,
    model: str = "gemini-2.5-flash",
    temperature: float = 0.2,
    max_tokens: int = 1000,
) -> Optional[str]:
    """
    Appelle l'API Gemini avec rotation automatique des cles en cas de quota depasse.

    Si GEMINI_API_KEY est en quota, bascule sur GEMINI_API_KEY_2, puis
    GEMINI_API_KEY_3, etc.

    Args:
        prompt:      Texte du prompt a envoyer.
        model:       Modele Gemini (defaut : gemini-2.5-flash).
        temperature: Temperature de generation (0.0 a 1.0).
        max_tokens:  Nombre max de tokens en sortie.

    Returns:
        Texte de la reponse Gemini, ou None si toutes les cles ont echoue.
    """
    keys = _load_api_keys()

    if not keys:
        logger.warning(
            "[Gemini] Aucune cle API configuree "
            "(GEMINI_API_KEY manquante dans .env)"
        )
        return None

    last_error: Optional[Exception] = None

    for attempt, key in enumerate(keys):
        key_label = "GEMINI_API_KEY" if attempt == 0 else f"GEMINI_API_KEY_{attempt + 1}"

        try:
            from google import genai

            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    temperature=temperature,
                ),
            )
            text = response.text.strip()
            if attempt > 0:
                logger.info(
                    "[Gemini] Succes avec %s (cle %d/%d)",
                    key_label, attempt + 1, len(keys),
                )
            return text

        except Exception as exc:
            last_error = exc
            exc_str = str(exc).lower()

            # Quota depasse ou rate limit
            is_quota = any(
                kw in exc_str
                for kw in ["quota", "429", "rate_limit", "resource_exhausted",
                           "too many requests", "rateerror"]
            )

            if is_quota:
                logger.warning(
                    "[Gemini] %s quota depasse (%s) — rotation vers la cle suivante",
                    key_label,
                    str(exc)[:80],
                )
                if attempt < len(keys) - 1:
                    time.sleep(_RETRY_DELAY)
                continue
            else:
                # Erreur non liee au quota (cle invalide, reseau, etc.)
                logger.error(
                    "[Gemini] Erreur non-quota sur %s : %s",
                    key_label,
                    str(exc)[:120],
                )
                # Essayer quand meme la cle suivante
                if attempt < len(keys) - 1:
                    time.sleep(_RETRY_DELAY)
                continue

    # Toutes les cles ont echoue
    logger.error(
        "[Gemini] Toutes les cles ont echoue (%d cle(s) testee(s)). "
        "Derniere erreur : %s",
        len(keys),
        str(last_error)[:120] if last_error else "inconnue",
    )
    return None


def get_available_keys_count() -> int:
    """Retourne le nombre de cles Gemini configurees."""
    return len(_load_api_keys())


def test_keys() -> dict[str, bool]:
    """
    Teste chaque cle Gemini avec un prompt minimal.

    Utile pour diagnostiquer les cles invalides ou en quota.

    Returns:
        Dict {key_label: ok} — True si la cle repond, False sinon.
    """
    keys = _load_api_keys()
    results: dict[str, bool] = {}

    for i, key in enumerate(keys):
        label = "GEMINI_API_KEY" if i == 0 else f"GEMINI_API_KEY_{i + 1}"
        try:
            from google import genai
            client = genai.Client(api_key=key)
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents="Reponds uniquement OK.",
                config=genai.types.GenerateContentConfig(temperature=0.0),
            )
            ok = bool(resp.text)
            results[label] = ok
            logger.info("[Gemini] %s : %s", label, "OK" if ok else "VIDE")
        except Exception as exc:
            results[label] = False
            logger.warning("[Gemini] %s : ECHEC (%s)", label, str(exc)[:60])

    return results
