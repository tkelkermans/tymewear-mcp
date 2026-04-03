from __future__ import annotations

from typing import Any

from tymewear_mcp.client.http import TymeClient


async def export_csv(client: TymeClient, activity_id: str) -> dict[str, Any]:
    data = await client.post("/v2/api/activities/export-csv/", json={"activity_id": activity_id})
    return client.sanitize(data)


async def export_csv_full(client: TymeClient, activity_id: str) -> dict[str, Any]:
    data = await client.post("/v2/api/activities/export-csv-full/", json={"activity_id": activity_id})
    return client.sanitize(data)


async def export_fit(client: TymeClient, activity_id: str) -> dict[str, Any]:
    data = await client.post("/v2/api/activities/export-fit/", json={"activity_id": activity_id})
    return client.sanitize(data)
