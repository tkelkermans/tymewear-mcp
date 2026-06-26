"""Breathing time-series data tools."""

from __future__ import annotations

from typing import Any

import httpx

from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.tools._availability import unavailable_from_http_error


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {"total_records": 0, "averages": {}, "peaks": {}}
    numeric_fields: dict[str, list[float]] = {}
    for record in records:
        for key, val in record.items():
            if isinstance(val, (int, float)) and key != "time":
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
            return unavailable_from_http_error(exc, default_reason="processed_data_not_available")
        raise
    records = data if isinstance(data, list) else []
    if mode == "summary":
        return _summarize(records)
    if mode == "window" and window_start is not None and window_end is not None:
        windowed = records[window_start:window_end + 1]
        return {"total_records": len(records), "window": {"start": window_start, "end": window_end}, "data": windowed}
    return {"total_records": len(records), "data": records}


async def get_new_processed_data(client: TymeClient, activity_id: str) -> Any:
    try:
        data = await client.get(f"/v2/api/activities/{activity_id}/new-processed-data/")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {403, 404}:
            return unavailable_from_http_error(exc, default_reason="new_processed_data_not_available")
        raise
    return client.sanitize(data) if isinstance(data, dict) else data
