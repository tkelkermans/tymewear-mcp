from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast
from urllib.parse import urljoin, urlsplit

import httpx
from httpx import Response

from tymewear_mcp.client.http import TymeClient

EXPORT_DIR = Path.home() / "Downloads" / "tymewear"
MAX_FIT_RESPONSE_BYTES = 16 * 1024 * 1024
FIT_DOWNLOAD_HOSTS = frozenset({"tymewear-production-files.s3.amazonaws.com"})


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


async def _fetch_fit_response(client: TymeClient, activity_id: str) -> Response:
    try:
        return await client.post_raw("/v2/api/activities/export-fit/", json={"activity_id": activity_id})
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in {403, 404}:
            raise
        return await client.get_raw(f"/api/activities/{activity_id}/fit/")


def _validate_fit_download_url(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("FIT download URL is missing or invalid")
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("FIT download URL has an invalid port") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname not in FIT_DOWNLOAD_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in {None, 443}
    ):
        raise ValueError("FIT download URL is not an allowlisted HTTPS URL")
    return value


def _fit_download_url(resp: Response) -> str:
    try:
        payload = resp.json()
    except ValueError as exc:
        raise ValueError("FIT export returned malformed JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("FIT download URL is missing or invalid")
    url = next((payload.get(key) for key in ("url", "download_url", "file_url") if key in payload), None)
    return _validate_fit_download_url(url)


def _check_response_size(resp: Response) -> None:
    content_length = resp.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError as exc:
            raise ValueError("FIT response has an invalid size") from exc
        if declared_size > MAX_FIT_RESPONSE_BYTES:
            raise ValueError("FIT response exceeds the size limit")


async def _read_signed_fit(url: str, download_client: httpx.AsyncClient) -> bytes:
    current_url = url
    for redirect_count in range(2):
        async with download_client.stream("GET", current_url, follow_redirects=False) as resp:
            if 300 <= resp.status_code < 400:
                if redirect_count == 1:
                    raise ValueError("FIT download followed more than one redirect")
                location = resp.headers.get("location")
                current_url = _validate_fit_download_url(urljoin(current_url, location or ""))
                continue

            resp.raise_for_status()
            _check_response_size(resp)
            content = bytearray()
            async for chunk in resp.aiter_bytes():
                content.extend(chunk)
                if len(content) > MAX_FIT_RESPONSE_BYTES:
                    raise ValueError("FIT response exceeds the size limit")
            return bytes(content)
    raise ValueError("FIT download followed more than one redirect")


async def _read_limited_response(resp: Response) -> bytes:
    _check_response_size(resp)
    content = bytearray()
    async for chunk in resp.aiter_bytes():
        content.extend(chunk)
        if len(content) > MAX_FIT_RESPONSE_BYTES:
            raise ValueError("FIT response exceeds the size limit")
    return bytes(content)


async def _stream_fit_response(client: TymeClient, activity_id: str) -> tuple[str, bytes]:
    try:
        async with client.stream_raw(
            "POST",
            "/v2/api/activities/export-fit/",
            json={"activity_id": activity_id},
        ) as resp:
            return resp.headers.get("content-type", ""), await _read_limited_response(resp)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in {403, 404}:
            raise
    async with client.stream_raw("GET", f"/api/activities/{activity_id}/fit/") as resp:
        return resp.headers.get("content-type", ""), await _read_limited_response(resp)


async def fetch_fit_bytes(
    client: TymeClient,
    activity_id: str,
    *,
    download_client: httpx.AsyncClient | None = None,
) -> bytes:
    """Fetch an activity FIT export into memory without exposing its URL or path."""
    if isinstance(client, TymeClient):
        content_type, content = await _stream_fit_response(client, activity_id)
        if "application/json" in content_type:
            url = _fit_download_url(Response(200, content=content, headers={"content-type": content_type}))
            if download_client is not None:
                return await _read_signed_fit(url, download_client)
            async with httpx.AsyncClient(timeout=30.0) as owned_client:
                return await _read_signed_fit(url, owned_client)
        return content

    resp = await _fetch_fit_response(client, activity_id)
    _check_response_size(resp)
    if "application/json" in resp.headers.get("content-type", ""):
        url = _fit_download_url(resp)
        if download_client is not None:
            return await _read_signed_fit(url, download_client)
        async with httpx.AsyncClient(timeout=30.0) as owned_client:
            return await _read_signed_fit(url, owned_client)
    if len(resp.content) > MAX_FIT_RESPONSE_BYTES:
        raise ValueError("FIT response exceeds the size limit")
    return resp.content


async def export_fit(client: TymeClient, activity_id: str) -> dict[str, Any]:
    resp = await _fetch_fit_response(client, activity_id)
    return _save_export(resp, activity_id, "fit")
