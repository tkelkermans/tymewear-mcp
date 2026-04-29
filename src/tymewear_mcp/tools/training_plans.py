"""Read-only training plan and workout recommendation tools."""

from __future__ import annotations

from typing import Any

import httpx

from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.tools._availability import unavailable_from_http_error


def _available(data: Any) -> dict[str, Any]:
    return {**data, "available": True} if isinstance(data, dict) else {"available": True, "data": data}


async def _get_available(client: TymeClient, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        data = await client.get(path, params=params) if params is not None else await client.get(path)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {403, 404}:
            reason = "subscription_required" if exc.response.status_code == 403 else "not_found"
            return unavailable_from_http_error(exc, default_reason=reason)
        raise
    return _available(client.sanitize(data))


async def get_training_plan(client: TymeClient, user_uuid: str) -> dict[str, Any]:
    return await _get_available(client, f"/v2/api/users/{user_uuid}/training-plan/")


async def get_training_plan_by_date(client: TymeClient, user_uuid: str, date: str) -> dict[str, Any]:
    return await _get_available(client, f"/v2/api/users/{user_uuid}/training-plan/", params={"date": date})


async def get_training_plan_by_week(client: TymeClient, user_uuid: str, week: str) -> dict[str, Any]:
    return await _get_available(client, f"/v2/api/users/{user_uuid}/training-plan/", params={"week": week})


async def get_training_plan_history(client: TymeClient, user_uuid: str) -> dict[str, Any]:
    return await _get_available(client, f"/v2/api/users/{user_uuid}/training-plans/history/")


async def get_training_plan_config(client: TymeClient, user_uuid: str) -> dict[str, Any]:
    return await _get_available(client, f"/v2/api/users/{user_uuid}/training-plan-config/")


async def get_training_plan_preview(client: TymeClient, user_uuid: str) -> dict[str, Any]:
    return await _get_available(client, f"/v2/api/users/{user_uuid}/training-plan-preview/")


async def get_workout_recommendation(client: TymeClient, user_id: int) -> dict[str, Any]:
    return await _get_available(client, f"/api/users/{user_id}/workout-recommendation/")
