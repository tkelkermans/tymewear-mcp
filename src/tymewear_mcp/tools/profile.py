"""tw_get_profile and tw_update_profile tools."""

from __future__ import annotations

from typing import Any

from tymewear_mcp.client.http import TymeClient


async def get_profile(client: TymeClient) -> dict[str, Any]:
    """Get the current user's profile."""
    data = await client.get("/v2/api/profile/")
    return client.sanitize(data)


async def update_profile(
    client: TymeClient,
    profile_id: int,
    weight: float | None = None,
    height: float | None = None,
    units: str | None = None,
) -> dict[str, Any]:
    """Update profile fields."""
    payload: dict[str, Any] = {}
    if weight is not None:
        payload["weight"] = weight
    if height is not None:
        payload["height"] = height
    if units is not None:
        payload["units"] = units
    data = await client.patch(f"/v2/api/profile/{profile_id}/", json=payload)
    return client.sanitize(data)
