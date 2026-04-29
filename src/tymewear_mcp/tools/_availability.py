"""Helpers for read-only features that may be unavailable for an account."""

from __future__ import annotations

from typing import Any

import httpx


def feature_unavailable(reason: str, status_code: int, detail: str) -> dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        "status_code": status_code,
        "detail": detail,
    }


def _response_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text or response.reason_phrase
    if isinstance(data, dict):
        detail = data.get("detail") or data.get("error") or data.get("message")
        if detail is not None:
            return str(detail)
    return response.reason_phrase


def unavailable_from_http_error(
    error: httpx.HTTPStatusError,
    *,
    default_reason: str = "feature_not_available",
) -> dict[str, Any]:
    status_code = error.response.status_code
    return feature_unavailable(
        reason=default_reason,
        status_code=status_code,
        detail=_response_detail(error.response),
    )
