"""Read-only Tymewear integration tools."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import httpx

from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.tools._availability import AvailabilityState, availability_envelope, unavailable_from_http_error
from tymewear_mcp.tools._safe_values import finite_number, safe_text

_SAFE_ERROR_CODE_PARTS = frozenset(
    {
        "auth",
        "connection",
        "denied",
        "error",
        "expired",
        "failed",
        "forbidden",
        "ingestion",
        "invalid",
        "limit",
        "not",
        "pending",
        "rate",
        "revoked",
        "sync",
        "timeout",
        "unauthorized",
        "unavailable",
    }
)


def _available(data: Any) -> dict[str, Any]:
    return {**data, "available": True} if isinstance(data, dict) else {"available": True, "data": data}


async def _get_available(client: TymeClient, path: str, *, not_found_reason: str) -> dict[str, Any]:
    try:
        data = await client.get(path)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            return unavailable_from_http_error(exc, default_reason="feature_not_available")
        if exc.response.status_code == 404:
            return unavailable_from_http_error(exc, default_reason=not_found_reason)
        raise
    return _available(client.sanitize(data))


async def get_integrations(client: TymeClient) -> dict[str, Any]:
    data = await client.get("/v2/api/integrations/")
    return _available(client.sanitize(data))


async def get_integration(client: TymeClient, integration_id: str) -> dict[str, Any]:
    return await _get_available(client, f"/v2/api/integrations/{integration_id}/", not_found_reason="not_found")


def _operational_capabilities() -> dict[str, dict[str, str]]:
    return {
        "sync_history": {
            "state": "unavailable",
            "reason": "sync_history_not_reported",
            "source": "integration_health",
        },
        "replay": {
            "state": "not_applicable",
            "reason": "replay_not_supported",
            "source": "integration_health",
        },
        "last_success_history": {
            "state": "unavailable",
            "reason": "last_success_history_not_reported",
            "source": "integration_health",
        },
        "cursor_watermark": {
            "state": "unavailable",
            "reason": "cursor_watermark_not_reported",
            "source": "integration_health",
        },
        "backlog": {
            "state": "unavailable",
            "reason": "backlog_not_reported",
            "source": "integration_health",
        },
        "failed_items": {
            "state": "unavailable",
            "reason": "failed_items_not_reported",
            "source": "integration_health",
        },
        "retries": {
            "state": "unavailable",
            "reason": "retries_not_reported",
            "source": "integration_health",
        },
        "next_retry": {
            "state": "unavailable",
            "reason": "next_retry_not_reported",
            "source": "integration_health",
        },
    }


def _state_from_bool(payload: dict[str, Any], key: str, *, yes: str, no: str) -> str | None:
    value = payload.get(key)
    return yes if value is True else no if value is False else None


def _normalized_text_state(value: Any, mapping: dict[str, str]) -> str | None:
    if not isinstance(value, str):
        return None
    return mapping.get(value.strip().casefold())


def _resolved_state(
    payload: dict[str, Any],
    *,
    bool_fields: tuple[tuple[str, str, str], ...],
    text_fields: tuple[str, ...],
    mapping: dict[str, str],
) -> str:
    """Resolve all recognized explicit state fields without precedence masking conflicts."""
    reported: set[str] = set()
    for key, yes, no in bool_fields:
        explicit = _state_from_bool(payload, key, yes=yes, no=no)
        if explicit is not None:
            reported.add(explicit)
    for key in text_fields:
        explicit = _normalized_text_state(payload.get(key), mapping)
        if explicit is not None:
            reported.add(explicit)
    if len(reported) > 1:
        return "conflicting"
    return next(iter(reported), "unknown")


def _connection_state(payload: dict[str, Any]) -> str:
    return _resolved_state(
        payload,
        bool_fields=(
            ("is_connected", "connected", "disconnected"),
            ("connected", "connected", "disconnected"),
        ),
        text_fields=("connection_state",),
        mapping={
            "connected": "connected",
            "disconnected": "disconnected",
            "connecting": "connecting",
            "error": "error",
            "failed": "error",
        },
    )


def _auth_state(payload: dict[str, Any]) -> str:
    return _resolved_state(
        payload,
        bool_fields=tuple(
            (key, "authenticated", "unauthenticated")
            for key in ("authenticated", "auth_valid", "token_valid")
        ),
        text_fields=("auth_state", "auth_status"),
        mapping={
            "authenticated": "authenticated",
            "valid": "authenticated",
            "active": "authenticated",
            "unauthenticated": "unauthenticated",
            "invalid": "unauthenticated",
            "expired": "expired",
            "revoked": "revoked",
            "error": "error",
            "failed": "error",
        },
    )


def _ingestion_state(payload: dict[str, Any]) -> str:
    return _resolved_state(
        payload,
        bool_fields=(("is_healthy", "healthy", "error"),),
        text_fields=("ingestion_state", "ingestion_status", "sync_status", "status"),
        mapping={
            "healthy": "healthy",
            "ok": "healthy",
            "active": "healthy",
            "idle": "idle",
            "pending": "sync_pending",
            "syncing": "sync_pending",
            "sync_pending": "sync_pending",
            "error": "error",
            "failed": "error",
            "unhealthy": "error",
        },
    )


def _checked(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("checked_at", "last_checked_at", "last_check_at"):
        value = payload.get(key)
        numeric = finite_number(value)
        valid = isinstance(numeric, (int, float))
        if isinstance(value, str):
            try:
                checked_text = safe_text(value, max_length=40)
                if checked_text is None:
                    raise ValueError
                parsed = datetime.fromisoformat(
                    checked_text[:-1] + "+00:00" if checked_text.endswith("Z") else checked_text
                )
                valid = parsed.tzinfo is not None
            except (OverflowError, ValueError):
                valid = False
        if valid:
            return {
                "availability": {
                    "state": "available",
                    "reason": "current_check_reported",
                    "source": f"integration_health.{key}",
                },
                "value": value,
            }
        if key in payload:
            return {
                "availability": {
                    "state": "unavailable",
                    "reason": "current_check_invalid",
                    "source": f"integration_health.{key}",
                }
            }
    return {
        "availability": {
            "state": "unavailable",
            "reason": "current_check_not_reported",
            "source": "integration_health",
        }
    }


def _error_value_present(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple)):
        return bool(value)
    return True


def _safe_error_code(value: Any) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z][A-Z0-9_.-]{0,63}", value):
        return None
    parts = frozenset(part for part in re.split(r"[^a-z0-9]+", value.casefold()) if part)
    if not parts or not parts <= _SAFE_ERROR_CODE_PARTS:
        return None
    return value


def _current_error(payload: dict[str, Any]) -> dict[str, Any]:
    reported = "error" in payload or any(key in payload for key in ("error_code", "last_error"))
    if not reported:
        return {
            "availability": {
                "state": "unavailable",
                "reason": "current_error_not_reported",
                "source": "integration_health",
            }
        }
    present = _error_value_present(payload.get("error")) or any(
        _error_value_present(payload.get(key)) for key in ("error_code", "last_error")
    )
    result: dict[str, Any] = {
        "availability": {
            "state": "available",
            "reason": "current_error_reported" if present else "no_current_error",
            "source": "integration_health.error",
        },
        "present": present,
    }
    code = _safe_error_code(payload.get("error_code"))
    if present and code is not None:
        result["code"] = code
    return result


def _integration_snapshot(
    integration_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    connection_state = _connection_state(payload)
    auth_state = _auth_state(payload)
    ingestion_state = _ingestion_state(payload)
    state_conflicts = sorted(
        name
        for name, value in {
            "connection_state": connection_state,
            "auth_state": auth_state,
            "ingestion_state": ingestion_state,
        }.items()
        if value == "conflicting"
    )
    checked = _checked(payload)
    error = _current_error(payload)
    incomplete = "unknown" in {connection_state, auth_state, ingestion_state}
    error_present = error.get("present") is True
    state: AvailabilityState = "partial" if state_conflicts or incomplete or error_present else "available"
    reason = (
        "current_snapshot_conflicting"
        if state_conflicts
        else "current_snapshot_incomplete"
        if incomplete
        else "current_snapshot_reports_error"
        if error_present
        else "current_snapshot_available"
    )
    result = {
        **availability_envelope(state=state, reason=reason, source="integration_health"),
        "integration_id": integration_id,
        "connection_state": connection_state,
        "auth_state": auth_state,
        "ingestion_state": ingestion_state,
        "checked": checked,
        "error": error,
        "capabilities": _operational_capabilities(),
    }
    if state_conflicts:
        result["state_conflicts"] = state_conflicts
    return result


def _failed_integration_snapshot(
    integration_id: str,
    *,
    reason: str,
    status_code: int | None = None,
) -> dict[str, Any]:
    return {
        **availability_envelope(
            state="permission_denied" if status_code == 403 else "unavailable",
            reason=reason,
            source="integration_health",
            http_status=status_code,
        ),
        "reason": reason,
        **({"status_code": status_code} if status_code is not None else {}),
        "integration_id": integration_id,
        "connection_state": "unknown",
        "auth_state": "unknown",
        "ingestion_state": "unknown",
        "checked": _checked({}),
        "error": _current_error({}),
        "capabilities": _operational_capabilities(),
    }


async def get_integration_health(client: TymeClient, integration_id: str) -> dict[str, Any]:
    try:
        data = await client.get(f"/v2/api/integrations/{integration_id}/health/")
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        reason = (
            "feature_not_available"
            if status_code == 403
            else "integration_not_configured"
            if status_code == 404
            else "integration_health_request_failed"
        )
        return _failed_integration_snapshot(integration_id, reason=reason, status_code=status_code)
    except Exception:
        return _failed_integration_snapshot(integration_id, reason="integration_health_request_failed")
    try:
        sanitized = client.sanitize(data)
    except Exception:
        return _failed_integration_snapshot(integration_id, reason="malformed_upstream_payload")
    if not isinstance(sanitized, dict) or not sanitized:
        return _failed_integration_snapshot(integration_id, reason="malformed_upstream_payload")
    return _integration_snapshot(integration_id, sanitized)
