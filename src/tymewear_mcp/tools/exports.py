from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import httpx
from httpx import Response

from tymewear_mcp.client.http import TymeClient

EXPORT_DIR = Path.home() / "Downloads" / "tymewear"


def _extract_filename(resp: Response) -> str | None:
    """Extract filename from Content-Disposition header if present."""
    cd = resp.headers.get("content-disposition", "")
    match = re.search(r'filename[*]?=["\']?([^"\';]+)', cd)
    return match.group(1).strip() if match else None


def _safe_export_filename(filename: str | None, fallback: str) -> str:
    if filename is not None:
        safe_name = Path(filename.replace("\\", "/")).name
        if safe_name not in {"", ".", ".."}:
            return safe_name
    return fallback


def _save_export(resp: Response, activity_id: str, extension: str) -> dict[str, Any]:
    """Save response content to file and return metadata."""
    content_type = resp.headers.get("content-type", "")

    if "application/json" in content_type:
        data = resp.json()
        return cast(dict[str, Any], TymeClient.sanitize(data))

    body_head = resp.content[:64].lstrip().lower()
    if "text/html" in content_type or body_head.startswith(b"<!doctype") or body_head.startswith(b"<html"):
        return {
            "available": False,
            "reason": "export_unavailable",
            "status_code": resp.status_code,
            "detail": "Export endpoint returned an HTML/error page instead of file data.",
        }

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    filename = _safe_export_filename(_extract_filename(resp), f"activity_{activity_id[:8]}.{extension}")
    filepath = EXPORT_DIR / filename

    filepath.write_bytes(resp.content)

    result: dict[str, Any] = {
        "file_path": str(filepath),
        "file_size_bytes": len(resp.content),
        "format": extension.upper(),
    }

    if extension in ("csv",):
        text = resp.text
        lines = text.splitlines()
        result["total_rows"] = max(0, len(lines) - 1)
        result["preview"] = "\n".join(lines[:10])

    return result


async def export_csv(client: TymeClient, activity_id: str) -> dict[str, Any]:
    resp = await client.post_raw("/v2/api/activities/export-csv/", json={"activity_id": activity_id})
    return _save_export(resp, activity_id, "csv")


async def export_csv_full(client: TymeClient, activity_id: str) -> dict[str, Any]:
    resp = await client.post_raw("/v2/api/activities/export-csv-full/", json={"activity_id": activity_id})
    return _save_export(resp, activity_id, "csv")


async def export_fit(client: TymeClient, activity_id: str) -> dict[str, Any]:
    try:
        resp = await client.post_raw("/v2/api/activities/export-fit/", json={"activity_id": activity_id})
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in {403, 404}:
            raise
        resp = await client.get_raw(f"/api/activities/{activity_id}/fit/")
    return _save_export(resp, activity_id, "fit")
