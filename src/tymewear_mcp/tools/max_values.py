from __future__ import annotations

from typing import Any

from tymewear_mcp.client.http import TymeClient


async def get_max_value_detections(client: TymeClient) -> Any:
    data = await client.get("/v2/api/max-value-detections/")
    if isinstance(data, list):
        return [client.sanitize(d) if isinstance(d, dict) else d for d in data]
    return client.sanitize(data)


async def respond_max_value(client: TymeClient, detection_id: int, accept: bool) -> dict[str, Any]:
    data = await client.post(f"/v2/api/max-value-detections/{detection_id}/respond/", json={"accept": accept})
    return client.sanitize(data)
