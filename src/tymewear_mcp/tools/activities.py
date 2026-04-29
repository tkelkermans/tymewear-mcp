"""Activity tools: list, detail, status, pin, delete."""

from __future__ import annotations

from typing import Any

from tymewear_mcp.client.http import TymeClient


async def get_activities(
    client: TymeClient,
    user_id: int,
    sport: int | None = None,
    limit: int = 50,
    cursor: str | None = None,
    sports: list[str] | None = None,
    activity_types: list[str] | None = None,
    search: str | None = None,
    requested_user_id: str | None = None,
    pro_team: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"user": requested_user_id or user_id, "limit": limit}
    sport_filters = sports or ([str(sport)] if sport is not None else None)
    if sport_filters:
        params["sport"] = sport_filters
    if activity_types:
        params["type"] = activity_types
    if search:
        params["search"] = search
    if cursor is not None:
        params["cursor"] = cursor
    if pro_team:
        params["pro_team"] = pro_team
    data = await client.get("/v2/api/activities-cursor/", params=params)
    return client.sanitize(data)


async def get_activity(client: TymeClient, activity_id: str) -> dict[str, Any]:
    data = await client.get(f"/v2/api/activities/{activity_id}/")
    return client.sanitize(data)


async def get_activity_status(client: TymeClient, activity_id: str) -> dict[str, Any]:
    data = await client.get(f"/v2/api/activities/{activity_id}/status/")
    return client.sanitize(data)


async def pin_activity(client: TymeClient, activity_id: str) -> dict[str, Any]:
    data = await client.post(f"/api/activities/{activity_id}/pin/")
    return client.sanitize(data)


async def get_pinned_activity(client: TymeClient, user_id: int) -> dict[str, Any]:
    data = await client.get(f"/api/users/{user_id}/pinned-activity/")
    return client.sanitize(data)


async def delete_activity(client: TymeClient, activity_id: str) -> dict[str, str]:
    await client.delete(f"/v2/api/activities/{activity_id}/")
    return {"status": "deleted", "activity_id": activity_id}
