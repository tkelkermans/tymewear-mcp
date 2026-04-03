from __future__ import annotations

from typing import Any

from tymewear_mcp.client.http import TymeClient

_THRESHOLD_ENDPOINTS = {
    "vt1": "/api/tag-vt1/",
    "vt2": "/api/tag-vt2/",
    "bp": "/api/tag-bp/",
    "vo2max": "/api/tag-v02max/",
}
_NEW_ZONE_ENDPOINTS = {
    "fatmax": "/api/tag-new-zone-fatmax/",
    "vt1": "/api/tag-new-zone-vt1/",
    "vt2": "/api/tag-new-zone-vt2/",
    "vo2max": "/api/tag-new-zone-vo2max/",
}


async def get_ve_targets(client: TymeClient, user_id: int) -> dict[str, Any]:
    data = await client.get(f"/api/users/{user_id}/ve-targets/")
    return client.sanitize(data)


async def tag_threshold(client: TymeClient, threshold_type: str, activity_id: str) -> dict[str, Any]:
    endpoint = _THRESHOLD_ENDPOINTS[threshold_type]
    data = await client.post(endpoint, json={"activity_id": activity_id})
    return client.sanitize(data)


async def tag_new_zone(client: TymeClient, zone_type: str, activity_id: str) -> dict[str, Any]:
    endpoint = _NEW_ZONE_ENDPOINTS[zone_type]
    data = await client.post(endpoint, json={"activity_id": activity_id})
    return client.sanitize(data)
