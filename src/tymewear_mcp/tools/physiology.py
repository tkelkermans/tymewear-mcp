"""Read-only physiology metric tools."""

from __future__ import annotations

from typing import Any

import httpx

from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.tools._availability import unavailable_from_http_error


def _available(data: Any) -> dict[str, Any]:
    return {**data, "available": True} if isinstance(data, dict) else {"available": True, "data": data}


async def get_resting_max_values(client: TymeClient) -> dict[str, Any]:
    try:
        data = await client.get("/v2/api/resting-max-values/")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {403, 404}:
            return unavailable_from_http_error(exc, default_reason="feature_not_available")
        raise
    return _available(client.sanitize(data))
