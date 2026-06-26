from __future__ import annotations

from typing import Any, cast

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


def get_ve_targets(profile: dict[str, Any]) -> dict[str, Any]:
    """Assemble VE threshold targets from the profile.

    The dedicated /ve-targets/ endpoint returns an empty body and crashes JSON
    parsing, but the profile already carries every target per sport.
    """

    def _sport(prefix: str) -> dict[str, Any]:
        return {key: profile.get(f"{prefix}_ve_target_{key}") for key in ("vt1", "bp", "vt2", "vo2max")}

    return {"bike": _sport("bike"), "running": _sport("running")}


async def tag_threshold(client: TymeClient, threshold_type: str, activity_id: str) -> dict[str, Any]:
    endpoint = _THRESHOLD_ENDPOINTS[threshold_type]
    data = await client.post(endpoint, json={"activity_id": activity_id})
    return cast(dict[str, Any], client.sanitize(data))


async def tag_new_zone(client: TymeClient, zone_type: str, activity_id: str) -> dict[str, Any]:
    endpoint = _NEW_ZONE_ENDPOINTS[zone_type]
    data = await client.post(endpoint, json={"activity_id": activity_id})
    return cast(dict[str, Any], client.sanitize(data))
