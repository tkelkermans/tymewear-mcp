"""Helpers for read-only features that may be unavailable for an account."""

from __future__ import annotations

from typing import Any, Literal

import httpx

AvailabilityState = Literal[
    "available",
    "partial",
    "not_applicable",
    "not_computed",
    "sync_pending",
    "unavailable",
    "permission_denied",
]


def availability_envelope(
    *,
    state: AvailabilityState,
    reason: str,
    source: str,
    http_status: int | None = None,
) -> dict[str, Any]:
    availability: dict[str, Any] = {
        "state": state,
        "reason": reason,
        "source": source,
    }
    if http_status is not None:
        availability["http_status"] = http_status
    return {
        "availability": availability,
        "available": state in {"available", "partial"},
    }


def feature_available(*, source: str) -> dict[str, Any]:
    return availability_envelope(state="available", reason="data_available", source=source)


def feature_unavailable(
    reason: str,
    status_code: int,
    detail: str | None = None,
    *,
    source: str = "tymewear_api",
) -> dict[str, Any]:
    state: AvailabilityState = "permission_denied" if status_code == 403 else "unavailable"
    return {
        **availability_envelope(
            state=state,
            reason=reason,
            source=source,
            http_status=status_code,
        ),
        "reason": reason,
        "status_code": status_code,
    }


def unavailable_from_http_error(
    error: httpx.HTTPStatusError,
    *,
    default_reason: str = "feature_not_available",
    source: str = "tymewear_api",
) -> dict[str, Any]:
    status_code = error.response.status_code
    return feature_unavailable(
        reason=default_reason,
        status_code=status_code,
        source=source,
    )
