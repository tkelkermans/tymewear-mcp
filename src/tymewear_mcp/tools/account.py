"""Read-only account and subscription tools."""

from __future__ import annotations

from typing import Any

from tymewear_mcp.client.http import TymeClient


def _available(data: Any) -> dict[str, Any]:
    return {**data, "available": True} if isinstance(data, dict) else {"available": True, "data": data}


async def get_subscription_status(client: TymeClient) -> dict[str, Any]:
    data = await client.get("/v2/api/subscription/status/")
    return _available(client.sanitize(data))


async def get_subscription_plans(client: TymeClient) -> dict[str, Any]:
    data = await client.get("/v2/api/subscription/plans/")
    return _available(client.sanitize(data))
