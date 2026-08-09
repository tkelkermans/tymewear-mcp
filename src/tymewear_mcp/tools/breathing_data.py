"""Breathing time-series data tools."""

from __future__ import annotations

from typing import Any

import httpx

from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.tools._availability import feature_available, unavailable_from_http_error

_RECORD_WRAPPERS = ("data", "results", "records", "samples")
_ELAPSED_TIME_FIELDS = ("time", "elapsed_time", "elapsed_seconds", "seconds", "second")
_CANONICAL_UNITS: dict[str, str | None] = {
    "br": "breaths/min",
    "breathing_rate": "breaths/min",
    "respiratory_rate": "breaths/min",
    "tv": "L",
    "tidal_volume": "L",
    "ve": "L/min",
    "ventilation": "L/min",
    "minute_ventilation": "L/min",
    "hr": "bpm",
    "heart_rate": "bpm",
    "power": "W",
    "bike_power": "W",
    "cadence": "rpm",
    "speed": "m/s",
    "zone": None,
}


def _normalize_records(data: Any) -> list[dict[str, Any]]:
    value = data
    for _ in range(3):
        if isinstance(value, list):
            return [record for record in value if isinstance(record, dict)]
        if not isinstance(value, dict):
            return []
        wrapped = next((value[key] for key in _RECORD_WRAPPERS if key in value), None)
        if wrapped is None:
            return []
        value = wrapped
    return []


def _channel_inventory(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    channels = sorted({str(key) for record in records for key in record if key not in _ELAPSED_TIME_FIELDS})
    total = len(records)
    return {
        channel: {
            "canonical_unit": _CANONICAL_UNITS.get(channel),
            "samples": (samples := sum(record.get(channel) is not None for record in records)),
            "coverage": round(samples / total, 4) if total else 0.0,
        }
        for channel in channels
    }


def _available_payload(records: list[dict[str, Any]], *, source: str) -> dict[str, Any]:
    return {
        **feature_available(source=source),
        "total_records": len(records),
        "channels": _channel_inventory(records),
    }


def _elapsed_seconds(record: dict[str, Any]) -> float | None:
    for field in _ELAPSED_TIME_FIELDS:
        value = record.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {"total_records": 0, "averages": {}, "peaks": {}}
    numeric_fields: dict[str, list[float]] = {}
    for record in records:
        for key, val in record.items():
            if isinstance(val, (int, float)) and not isinstance(val, bool) and key not in _ELAPSED_TIME_FIELDS:
                numeric_fields.setdefault(key, []).append(float(val))
    averages = {k: round(sum(v) / len(v), 2) for k, v in numeric_fields.items()}
    peaks = {k: round(max(v), 2) for k, v in numeric_fields.items()}
    mins = {k: round(min(v), 2) for k, v in numeric_fields.items()}
    return {
        "total_records": len(records),
        "duration_seconds": len(records),
        "averages": averages,
        "peaks": peaks,
        "mins": mins,
    }


async def get_processed_data(
    client: TymeClient, activity_id: str, mode: str = "summary",
    window_start: int | None = None, window_end: int | None = None,
) -> dict[str, Any]:
    try:
        data = await client.get(f"/v2/api/activities/{activity_id}/processed-data/")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {403, 404}:
            return unavailable_from_http_error(
                exc,
                default_reason="processed_data_not_available",
                source="processed_data",
            )
        raise
    records = _normalize_records(client.sanitize(data))
    base = _available_payload(records, source="processed_data")
    if mode == "summary":
        return {**base, **_summarize(records)}
    if mode == "window" and window_start is not None and window_end is not None:
        windowed = [
            record
            for record in records
            if (elapsed := _elapsed_seconds(record)) is not None and window_start <= elapsed <= window_end
        ]
        return {**base, "window": {"start": window_start, "end": window_end}, "data": windowed}
    return {**base, "data": records}


async def get_new_processed_data(client: TymeClient, activity_id: str) -> Any:
    try:
        data = await client.get(f"/v2/api/activities/{activity_id}/new-processed-data/")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {403, 404}:
            return unavailable_from_http_error(
                exc,
                default_reason="new_processed_data_not_available",
                source="new_processed_data",
            )
        raise
    records = _normalize_records(client.sanitize(data))
    return {**_available_payload(records, source="new_processed_data"), "data": records}
