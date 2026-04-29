from __future__ import annotations

from typing import Any, cast

from tymewear_mcp.client.http import TymeClient


async def get_zone_distribution(client: TymeClient, user_id: int) -> dict[str, Any]:
    data = await client.get(f"/v2/api/users/{user_id}/new-zone-distribution/")
    return cast(dict[str, Any], client.sanitize(data))
