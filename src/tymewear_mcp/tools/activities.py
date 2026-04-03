"""Activity tools: list, detail, status, pin, delete."""

from __future__ import annotations

from typing import Any

from tymewear_mcp.client.http import TymeClient


async def get_activities(
    client: TymeClient, user_id: int, sport: int | None = None,
    limit: int = 50, cursor: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"user": user_id, "limit": limit}
    if sport is not None:
        params["type"] = sport
    if cursor is not None:
        params["cursor"] = cursor
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
