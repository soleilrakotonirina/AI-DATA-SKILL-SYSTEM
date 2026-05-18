"""
backend/skills/etl_skill/core/loader.py
Chargement de donnees depuis une URL — REST API, CSV, JSON, XML.

Equivalent du connecteur REST de PowerBI :
- Fetch automatique avec gestion de pagination
- Detection du format par Content-Type ou extension
- Aplatissement automatique du JSON imbrique
- Support des structures complexes (World Bank, OpenData, etc.)

Usage :
    from skills.etl_skill.core.loader import load_from_url
    df, meta = load_from_url("https://api.worldbank.org/v2/...")
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import urlparse, urlencode, urljoin, parse_qs, urlunparse

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# Timeout par requete HTTP (secondes)
_HTTP_TIMEOUT = 60
# Pause entre requetes de pagination (secondes)
_PAGINATION_DELAY = 0.3
# Nombre max de pages a recuperer
_MAX_PAGES = 5   # Limiter pour eviter les timeouts — augmenter si besoin


# ══════════════════════════════════════════════════════════════════════════════
# FONCTION PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════════

def load_from_url(
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    auth: tuple | None = None,
    max_pages: int = _MAX_PAGES,
) -> tuple[pd.DataFrame, dict]:
    """
    Charge des donnees depuis une URL et retourne un DataFrame propre.

    Gere automatiquement :
    - JSON simple, JSON imbrique, JSON pagine
    - CSV depuis URL
    - Structures World Bank, OpenData, GeoJSON features
    - Pagination par page/offset/cursor

    Args:
        url       : URL de l API ou du fichier distant
        params    : Parametres additionnels a ajouter a l URL
        headers   : Headers HTTP (Authorization, Accept, etc.)
        auth      : Tuple (username, password) pour l auth basique
        max_pages : Nombre maximum de pages a recuperer

    Returns:
        Tuple (DataFrame, metadata) ou metadata contient :
        {
          "source_url"   : str,
          "format"       : "json" | "csv" | "xml",
          "n_rows"       : int,
          "n_cols"       : int,
          "pages_fetched": int,
          "total_records": int | None,
          "columns"      : list[str],
        }
    """
    logger.info("[Loader] Chargement depuis URL : %s", url)

    # Detecter le format attendu
    fmt = _detect_format(url, headers or {})
    logger.info("[Loader] Format detecte : %s", fmt)

    if fmt == "csv":
        df = _load_csv(url, params, headers, auth)
        meta = _build_meta(url, "csv", df, pages_fetched=1)
        return df, meta

    # JSON : fetch avec pagination
    all_records, pages_fetched, total = _fetch_json_paginated(
        url, params or {}, headers or {}, auth, max_pages
    )

    df = _records_to_dataframe(all_records)
    meta = _build_meta(url, fmt, df, pages_fetched, total)

    logger.info(
        "[Loader] Resultat : %d lignes x %d colonnes (%d page(s))",
        len(df), df.shape[1], pages_fetched,
    )
    return df, meta


# ══════════════════════════════════════════════════════════════════════════════
# DETECTION DU FORMAT
# ══════════════════════════════════════════════════════════════════════════════

def _detect_format(url: str, headers: dict) -> str:
    """
    Detecte le format attendu par Content-Type ou extension URL.
    Defaut : json.
    """
    url_lower = url.lower().split("?")[0]
    accept = headers.get("Accept", "").lower()

    if url_lower.endswith(".csv") or "format=csv" in url.lower():
        return "csv"
    if url_lower.endswith(".xml") or "format=xml" in url.lower():
        return "xml"
    if "csv" in accept:
        return "csv"
    return "json"


# ══════════════════════════════════════════════════════════════════════════════
# CHARGEMENT CSV DISTANT
# ══════════════════════════════════════════════════════════════════════════════

def _load_csv(
    url: str,
    params: dict | None,
    headers: dict | None,
    auth: tuple | None,
) -> pd.DataFrame:
    """Charge un CSV depuis une URL en passant par requests pour gerer l auth."""
    resp = requests.get(
        url, params=params, headers=headers, auth=auth,
        timeout=_HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    from io import StringIO
    return pd.read_csv(StringIO(resp.text))


# ══════════════════════════════════════════════════════════════════════════════
# FETCH JSON AVEC PAGINATION AUTOMATIQUE
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_json_paginated(
    url: str,
    params: dict,
    headers: dict,
    auth: tuple | None,
    max_pages: int,
) -> tuple[list[dict], int, int | None]:
    """
    Recupere toutes les pages JSON d une API paginee.

    Detecte automatiquement le style de pagination :
    1. World Bank : ?page=N&per_page=N → response[0].pages
    2. per_page/page classique         → {"total_pages": N}
    3. offset/limit                    → {"count": N, "next": url}
    4. Cursor-based                    → {"next_cursor": str}
    5. Pas de pagination               → retourne directement

    Returns:
        (records, pages_fetched, total_records)
    """
    all_records: list[dict] = []
    pages_fetched = 0
    total_records = None

    # Forcer per_page=1000 pour les APIs qui supportent la pagination
    # (World Bank supporte jusqu a per_page=1000)
    # Extraire les params deja dans l URL pour eviter les doublons
    from urllib.parse import urlparse, parse_qs, urlunparse
    parsed = urlparse(url)
    url_params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    # Fusionner : params URL + params argument (argument prioritaire)
    merged_params = {**url_params, **params}
    # Nettoyer l URL (supprimer les params, ils sont dans merged_params)
    url = urlunparse(parsed._replace(query=""))
    params = merged_params

    if "worldbank.org" in url:
        params.setdefault("format", "json")
        params.setdefault("per_page", "100")

    if "skip" not in params and "offset" not in params:
        pass  # offset géré par _next_page_url

    current_url = url
    current_params = params.copy()

    while pages_fetched < max_pages:
        logger.info("[Loader] Requete page %d : %s", pages_fetched + 1, current_url)
        resp = requests.get(
            current_url, params=current_params if current_params else None,
            headers=headers, auth=auth, timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()

        # Verifier que la reponse contient du JSON
        ct = resp.headers.get("Content-Type", "")
        body = resp.text.strip()
        if not body:
            logger.warning("[Loader] Reponse vide (page %d)", pages_fetched + 1)
            break
        if "xml" in ct or body.startswith("<"):
            logger.info("[Loader] Reponse XML detectee — conversion forcee en JSON")
            # Refaire la requete avec format=json explicite
            resp2 = requests.get(
                current_url,
                params={**(current_params if pages_fetched == 1 else {}), "format": "json"},
                headers=headers, auth=auth, timeout=_HTTP_TIMEOUT,
            )
            resp2.raise_for_status()
            body = resp2.text.strip()
        try:
            raw = resp.json() if body == resp.text.strip() else __import__("json").loads(body)
        except Exception:
            import json as _json
            raw = _json.loads(body)
        pages_fetched += 1

        # Extraire les records et les infos de pagination
        records, pagination = _parse_json_response(raw, url)
        all_records.extend(records)

        if total_records is None and pagination.get("total"):
            total_records = pagination["total"]

        logger.info(
            "[Loader] Page %d : %d records (total cumule : %d)",
            pages_fetched, len(records), len(all_records),
        )

        # Determiner s il y a une page suivante
        next_url = _next_page_url(current_url, current_params, pagination, pages_fetched)
        if not next_url:
            break

        current_url = next_url
        current_params = {}  # params deja dans l URL pour les pages suivantes
        time.sleep(_PAGINATION_DELAY)

    return all_records, pages_fetched, total_records


def _next_page_url(
    current_url: str,
    params: dict,
    pagination: dict,
    pages_fetched: int,
) -> str | None:
    """
    Calcule l URL de la prochaine page selon le style de pagination detecte.
    Retourne None si on est sur la derniere page.
    """
    # Style World Bank : page N de total_pages
    if pagination.get("style") == "worldbank":
        current_page = pagination.get("page", 1)
        total_pages  = pagination.get("total_pages", 1)
        if current_page >= total_pages:
            return None
        # Reconstruire avec TOUS les params originaux + page suivante
        base_params = {k: v for k, v in params.items() if k != "page"}
        base_params["page"] = str(current_page + 1)
        new_query = urlencode(base_params)
        parsed = urlparse(current_url)
        return urlunparse(parsed._replace(query=new_query))

    # Style "next" URL directe
    if pagination.get("next_url"):
        return pagination["next_url"]

    # Style offset/limit
    if pagination.get("style") == "offset":
        offset = pagination.get("offset", 0)
        limit  = pagination.get("limit", 100)
        total  = pagination.get("total", 0)
        if offset + limit >= total:
            return None
        parsed = urlparse(current_url)
        qs = parse_qs(parsed.query)
        qs["offset"] = [str(offset + limit)]
        new_query = "&".join(f"{k}={v[0]}" for k, v in qs.items())
        return urlunparse(parsed._replace(query=new_query))

    return None


# ══════════════════════════════════════════════════════════════════════════════
# PARSING DU JSON
# ══════════════════════════════════════════════════════════════════════════════

def _parse_json_response(
    raw: Any,
    url: str,
) -> tuple[list[dict], dict]:
    """
    Parse une reponse JSON en liste de records et infos de pagination.

    Gere les structures courantes :
    1. World Bank : [metadata_dict, [records...]]
    2. Array direct : [{...}, {...}, ...]
    3. Enveloppe standard : {"data": [...], "meta": {...}}
    4. Enveloppe results : {"results": [...], "count": N, "next": url}
    5. GeoJSON : {"type": "FeatureCollection", "features": [...]}
    6. OData : {"value": [...], "@odata.nextLink": url}

    Returns:
        (records_list, pagination_info)
    """
    pagination: dict = {}

    # ── 1. World Bank : [meta_dict, [records]] ────────────────────────────────
    if (isinstance(raw, list) and len(raw) == 2
            and isinstance(raw[0], dict) and isinstance(raw[1], list)):
        meta    = raw[0]
        records = raw[1] or []
        pagination = {
            "style":       "worldbank",
            "page":        int(meta.get("page", 1)),
            "total_pages": int(meta.get("pages", 1)),
            "total":       int(meta.get("total", len(records))),
        }
        logger.info(
            "[Loader] Structure World Bank : page %d/%d, total=%d",
            pagination["page"], pagination["total_pages"], pagination["total"],
        )
        return _flatten_records(records), pagination

    # ── 2. Array direct ───────────────────────────────────────────────────────
    if isinstance(raw, list):
        return _flatten_records(raw), pagination

    # ── 3. GeoJSON FeatureCollection ──────────────────────────────────────────
    if isinstance(raw, dict) and raw.get("type") == "FeatureCollection":
        features = raw.get("features", [])
        records = []
        for f in features:
            rec = {}
            props = f.get("properties") or {}
            rec.update(props)
            geom = f.get("geometry") or {}
            if geom.get("coordinates"):
                coords = geom["coordinates"]
                if geom.get("type") == "Point" and len(coords) >= 2:
                    rec["longitude"] = coords[0]
                    rec["latitude"]  = coords[1]
            records.append(rec)
        return records, pagination

    # ── 4. OData ──────────────────────────────────────────────────────────────
    if isinstance(raw, dict) and "value" in raw and isinstance(raw["value"], list):
        next_link = raw.get("@odata.nextLink") or raw.get("odata.nextLink")
        if next_link:
            pagination["next_url"] = next_link
        pagination["total"] = raw.get("@odata.count", len(raw["value"]))
        return _flatten_records(raw["value"]), pagination

    # ── 5. Enveloppe "results" (DRF, OpenData, DummyJSON, …) ─────────────────
    if isinstance(raw, dict):
        # Clés connues en priorité
        known_keys = ("results", "data", "items", "records", "rows",
                      "features", "entries", "content", "payload")
        # Fallback générique : première clé dont la valeur est une liste de dicts
        _skip_keys = {"links", "meta", "errors", "warnings"}
        generic_key = next(
            (k for k, v in raw.items()
             if isinstance(v, list) and v and isinstance(v[0], dict)
             and k not in _skip_keys),
            None,
        )
        candidate_keys = [k for k in known_keys if k in raw]
        if generic_key and generic_key not in known_keys:
            candidate_keys.append(generic_key)
        for key in candidate_keys:
            if key in raw and isinstance(raw[key], list):
                count    = raw.get("count") or raw.get("total") or raw.get("totalCount")
                next_url = raw.get("next")
                offset   = raw.get("offset", raw.get("skip", 0))
                if next_url:
                    pagination["next_url"] = next_url
                elif count:
                    pagination["style"]  = "offset"
                    pagination["total"]  = int(count)
                    pagination["offset"] = int(offset)
                    pagination["limit"]  = len(raw[key])
                if count:
                    pagination["total"] = int(count)
                logger.info("[Loader] Enveloppe detectee : cle='%s', %d records", key, len(raw[key]))
                return _flatten_records(raw[key]), pagination

    # ── 6. Dict simple (un seul objet) → envelopper dans une liste ───────────
    if isinstance(raw, dict):
        return [raw], pagination

    return [], pagination


def _flatten_records(records: list[Any]) -> list[dict]:
    """
    Aplatit une liste de records JSON imbriques en liste de dicts plats.

    Exemple World Bank :
        {"indicator": {"id": "NY.GDP.MKTP.CD", "value": "GDP"},
         "country": {"id": "FR", "value": "France"},
         "date": "2022", "value": 2957879759870.0}
    devient :
        {"indicator_id": "NY.GDP.MKTP.CD", "indicator_value": "GDP",
         "country_id": "FR", "country_value": "France",
         "date": "2022", "value": 2957879759870.0}
    """
    if not records:
        return []

    flat = []
    for rec in records:
        if not isinstance(rec, dict):
            flat.append({"value": rec})
            continue
        flat.append(_flatten_dict(rec))
    return flat


def _flatten_dict(d: dict, parent_key: str = "", sep: str = "_") -> dict:
    """
    Aplatit recursivement un dictionnaire imbrique.
    {"a": {"b": 1, "c": 2}} → {"a_b": 1, "a_c": 2}
    """
    items: dict = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(_flatten_dict(v, new_key, sep))
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            # Sous-liste de dicts : prendre le premier element ou stringifier
            if len(v) == 1:
                items.update(_flatten_dict(v[0], new_key, sep))
            else:
                items[new_key] = str(v)
        else:
            items[new_key] = v
    return items


# ══════════════════════════════════════════════════════════════════════════════
# CONVERSION EN DATAFRAME
# ══════════════════════════════════════════════════════════════════════════════

def _records_to_dataframe(records: list[dict]) -> pd.DataFrame:
    """
    Convertit une liste de dicts plats en DataFrame pandas.
    Infere les types automatiquement.
    """
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # Inference des types numeriques
    for col in df.columns:
        try:
            df[col] = pd.to_numeric(df[col], errors="ignore")
        except Exception:
            pass

    # Inference des dates
    for col in df.columns:
        if df[col].dtype == object:
            sample = df[col].dropna().head(10).astype(str)
            looks_like_date = sample.str.match(
                r"^\d{4}-\d{2}-\d{2}|^\d{4}/\d{2}/\d{2}"
            ).mean() > 0.5
            if looks_like_date:
                try:
                    df[col] = pd.to_datetime(df[col], errors="coerce")
                except Exception:
                    pass

    return df


def _build_meta(
    url: str, fmt: str, df: pd.DataFrame,
    pages_fetched: int = 1, total: int | None = None,
) -> dict:
    return {
        "source_url":    url,
        "format":        fmt,
        "n_rows":        len(df),
        "n_cols":        df.shape[1],
        "pages_fetched": pages_fetched,
        "total_records": total,
        "columns":       list(df.columns),
    }