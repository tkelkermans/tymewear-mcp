"""Read-only Tymewear integration tools."""

from __future__ import annotations

from typing import Any

import httpx

from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.tools._availability import unavailable_from_http_error


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


async def get_integration_health(client: TymeClient, integration_id: str) -> dict[str, Any]:
    return await _get_available(
        client,
        f"/v2/api/integrations/{integration_id}/health/",
        not_found_reason="integration_not_configured",
    )
