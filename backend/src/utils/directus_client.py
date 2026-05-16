"""
backend/src/utils/directus_client.py
Client HTTP asynchrone pour Directus.

Les variables DIRECTUS_URL et DIRECTUS_TOKEN sont lues depuis os.environ
a chaque appel. Passer --env-file .env a uv run pour les charger.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 30.0
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _url() -> str:
    return os.environ.get("DIRECTUS_URL", "http://localhost:8055")


def _token() -> str:
    return os.environ.get("DIRECTUS_TOKEN", "")


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}"}


def _is_uuid(s: str | None) -> bool:
    return bool(s and _UUID_RE.match(str(s)))


def _safe_sid(session_id: str | None) -> str | None:
    return session_id if _is_uuid(session_id) else None


def _log_err(exc: httpx.HTTPStatusError, ctx: str) -> None:
    body = exc.response.text[:500] if exc.response else ""
    logger.error("[Directus] %s HTTP %d — %s", ctx, exc.response.status_code, body)


async def push_report_mdx(
    session_id: str | None,
    report_type: str,
    title: str,
    content_mdx: str,
) -> str:
    if not _token():
        logger.warning("[Directus] DIRECTUS_TOKEN manquant — rapport MDX non publie")
        return ""
    payload: dict[str, Any] = {
        "type": report_type,
        "title": title,
        "content_mdx": content_mdx,
    }
    sid = _safe_sid(session_id)
    if sid:
        payload["session_id"] = sid
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_url()}/items/reports_mdx",
                headers=_headers(),
                json=payload,
            )
            r.raise_for_status()
            rid: str = r.json()["data"]["id"]
            logger.info("[Directus] Rapport MDX publie — %s ID=%s", title, rid)
            return rid
    except httpx.HTTPStatusError as e:
        _log_err(e, f"push_report_mdx({report_type})")
        return ""
    except httpx.RequestError as e:
        logger.error("[Directus] Connexion impossible : %s", e)
        return ""


async def push_chart(
    session_id: str | None,
    title: str,
    chart_type: str,
    plotly_json: dict,
) -> str:
    if not _token():
        return ""
    payload: dict[str, Any] = {
        "title": title,
        "chart_type": chart_type,
        "plotly_json": plotly_json,
    }
    sid = _safe_sid(session_id)
    if sid:
        payload["session_id"] = sid
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_url()}/items/charts",
                headers=_headers(),
                json=payload,
            )
            r.raise_for_status()
            cid: str = r.json()["data"]["id"]
            logger.info("[Directus] Chart publie — %s ID=%s", title, cid)
            return cid
    except httpx.HTTPStatusError as e:
        _log_err(e, f"push_chart({chart_type})")
        return ""
    except httpx.RequestError as e:
        logger.error("[Directus] Connexion impossible : %s", e)
        return ""


async def create_session(
    user_id: str,
    dataset_name: str,
    skills_used: Optional[list[str]] = None,
) -> str:
    if not _token():
        return ""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_url()}/items/sessions",
                headers=_headers(),
                json={
                    "user_id": user_id,
                    "dataset_name": dataset_name,
                    "skills_used": skills_used or [],
                    "status": "running",
                },
            )
            r.raise_for_status()
            sid: str = r.json()["data"]["id"]
            logger.info("[Directus] Session creee — ID=%s", sid)
            return sid
    except httpx.HTTPStatusError as e:
        _log_err(e, "create_session")
        return ""
    except httpx.RequestError as e:
        logger.error("[Directus] Connexion impossible : %s", e)
        return ""


async def close_session(
    session_id: str | None,
    status: str = "success",
    duration_ms: Optional[int] = None,
) -> None:
    if not _token() or not _is_uuid(session_id):
        return
    payload: dict[str, Any] = {"status": status}
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.patch(
                f"{_url()}/items/sessions/{session_id}",
                headers=_headers(),
                json=payload,
            )
            r.raise_for_status()
    except httpx.HTTPStatusError as e:
        _log_err(e, f"close_session({session_id})")
    except httpx.RequestError as e:
        logger.error("[Directus] Connexion impossible : %s", e)


async def append_pipeline_log(
    session_id: str | None,
    skill: str,
    action: str,
    status: str,
    message: str,
) -> None:
    if not _token():
        return
    payload: dict[str, Any] = {
        "skill": skill,
        "action": action,
        "status": status,
        "message": message,
    }
    sid = _safe_sid(session_id)
    if sid:
        payload["session_id"] = sid
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_url()}/items/pipeline_logs",
                headers=_headers(),
                json=payload,
            )
            r.raise_for_status()
    except httpx.HTTPError:
        pass  # logs non bloquants
