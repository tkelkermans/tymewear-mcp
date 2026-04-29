"""Read-only activity logs, strap files, and workout-zone detection tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.tools._availability import unavailable_from_http_error
from tymewear_mcp.tools.exports import _extract_filename, _safe_export_filename

EXPORT_DIR = Path.home() / "Downloads" / "tymewear"


def _save_binary(resp: httpx.Response, activity_id: str, extension: str) -> dict[str, Any]:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    filename = _safe_export_filename(
        _extract_filename(resp),
        f"activity_{activity_id[:8]}_strap_files.{extension}",
    )
    filepath = EXPORT_DIR / filename
    filepath.write_bytes(resp.content)
    return {
        "file_path": str(filepath),
        "file_size_bytes": len(resp.content),
        "format": extension.upper(),
        "content_type": resp.headers.get("content-type", ""),
    }


async def get_activity_logs(client: TymeClient, activity_id: str) -> Any:
    data = await client.get(f"/v2/api/activities/{activity_id}/logs/")
    return client.sanitize(data)


async def get_activity_strap_files(client: TymeClient, activity_id: str) -> dict[str, Any]:
    try:
        data = await client.get(f"/v2/api/activities/{activity_id}/strap-files/")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {403, 404}:
            reason = "raw_data_access_disabled" if exc.response.status_code == 403 else "not_found"
            return unavailable_from_http_error(exc, default_reason=reason)
        raise
    sanitized = client.sanitize(data)
    return {**sanitized, "available": True} if isinstance(sanitized, dict) else {"available": True, "data": sanitized}


async def export_activity_strap_files(client: TymeClient, activity_id: str) -> dict[str, Any]:
    try:
        resp = await client.get_raw(f"/v2/api/activities/{activity_id}/strap-files/")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {403, 404}:
            reason = "raw_data_access_disabled" if exc.response.status_code == 403 else "not_found"
            return unavailable_from_http_error(exc, default_reason=reason)
        raise
    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        data = TymeClient.sanitize(resp.json())
        return {**data, "available": True} if isinstance(data, dict) else {"available": True, "data": data}
    extension = "zip" if "zip" in content_type else "bin"
    return _save_binary(resp, activity_id, extension)


async def get_activity_workout_zone_detection(client: TymeClient, activity_id: str) -> dict[str, Any]:
    try:
        data = await client.get(f"/v2/api/activities/{activity_id}/workout-zone-detection/")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {403, 404}:
            return unavailable_from_http_error(exc, default_reason="feature_not_available")
        raise
    sanitized = client.sanitize(data)
    return {**sanitized, "available": True} if isinstance(sanitized, dict) else {"available": True, "data": sanitized}
