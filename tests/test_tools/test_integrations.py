from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

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
    mock_client.get = AsyncMock(return_value={"slug": "garmin", "token": "secret"})
    mock_client.sanitize = lambda data: {"slug": data["slug"]}

    result = await get_integration(mock_client, "garmin")

    mock_client.get.assert_called_once_with("/v2/api/integrations/garmin/")
    assert result == {"available": True, "slug": "garmin"}


async def test_get_integration_404():
    request = httpx.Request("GET", "https://api.tymewear.com/v2/api/integrations/garmin/")
    response = httpx.Response(404, json={"detail": "Not found"}, request=request)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError("Not found", request=request, response=response))

    result = await get_integration(mock_client, "garmin")

    assert result["available"] is False
    assert result["reason"] == "not_found"


async def test_get_integration_health_success():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value={"status": "healthy", "token": "secret"})
    mock_client.sanitize = lambda data: {"status": data["status"]}

    result = await get_integration_health(mock_client, "garmin")

    mock_client.get.assert_called_once_with("/v2/api/integrations/garmin/health/")
    assert result == {"available": True, "status": "healthy"}


async def test_get_integration_health_404():
    request = httpx.Request("GET", "https://api.tymewear.com/v2/api/integrations/garmin/health/")
    response = httpx.Response(404, json={"detail": "Not configured"}, request=request)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError("Not configured", request=request, response=response))

    result = await get_integration_health(mock_client, "garmin")

    assert result["available"] is False
    assert result["reason"] == "integration_not_configured"


async def test_get_integration_health_unexpected_http_status_reraises():
    request = httpx.Request("GET", "https://api.tymewear.com/v2/api/integrations/garmin/health/")
    response = httpx.Response(500, json={"detail": "Server error"}, request=request)
    error = httpx.HTTPStatusError("Server error", request=request, response=response)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=error)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await get_integration_health(mock_client, "garmin")

    assert exc_info.value is error
