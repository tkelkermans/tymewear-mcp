from __future__ import annotations

from unittest.mock import AsyncMock

import httpx

from tymewear_mcp.tools._validation import IntegrationInput
from tymewear_mcp.tools.integrations import get_integration, get_integration_health, get_integrations


def test_integration_input_accepts_slug():
    params = IntegrationInput.model_validate({"integration_id": "garmin"})
    assert params.integration_id == "garmin"


async def test_get_integrations():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=[{"slug": "garmin", "token": "secret"}])
    mock_client.sanitize = lambda data: [{"slug": item["slug"]} for item in data]

    result = await get_integrations(mock_client)

    mock_client.get.assert_called_once_with("/v2/api/integrations/")
    assert result == {"available": True, "data": [{"slug": "garmin"}]}


async def test_get_integrations_payload_cannot_override_availability():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value={"available": False, "slug": "garmin"})
    mock_client.sanitize = lambda data: data

    result = await get_integrations(mock_client)

    assert result == {"available": True, "slug": "garmin"}


async def test_get_integration_detail():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value={"slug": "garmin"})
    mock_client.sanitize = lambda data: data

    await get_integration(mock_client, "garmin")

    mock_client.get.assert_called_once_with("/v2/api/integrations/garmin/")


async def test_get_integration_health_404():
    request = httpx.Request("GET", "https://api.tymewear.com/v2/api/integrations/garmin/health/")
    response = httpx.Response(404, json={"detail": "Not configured"}, request=request)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError("Not configured", request=request, response=response))

    result = await get_integration_health(mock_client, "garmin")

    assert result["available"] is False
    assert result["reason"] == "integration_not_configured"
