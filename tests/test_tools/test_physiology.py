from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from tymewear_mcp.tools.physiology import get_resting_max_values


async def test_get_resting_max_values():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value={"max_hr": 190, "secret": "x"})
    mock_client.sanitize = lambda data: {"max_hr": data["max_hr"]}

    result = await get_resting_max_values(mock_client)

    mock_client.get.assert_called_once_with("/v2/api/resting-max-values/")
    assert result == {"available": True, "max_hr": 190}


async def test_get_resting_max_values_payload_cannot_override_availability():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value={"available": False, "max_hr": 190})
    mock_client.sanitize = lambda data: data

    result = await get_resting_max_values(mock_client)

    assert result == {"available": True, "max_hr": 190}


async def test_get_resting_max_values_403():
    request = httpx.Request("GET", "https://api.tymewear.com/v2/api/resting-max-values/")
    response = httpx.Response(403, json={"detail": "Upgrade required"}, request=request)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError("Forbidden", request=request, response=response))

    result = await get_resting_max_values(mock_client)

    assert result["available"] is False
    assert result["reason"] == "feature_not_available"


async def test_get_resting_max_values_unexpected_http_status_reraises():
    request = httpx.Request("GET", "https://api.tymewear.com/v2/api/resting-max-values/")
    response = httpx.Response(500, json={"detail": "Server error"}, request=request)
    error = httpx.HTTPStatusError("Server error", request=request, response=response)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=error)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await get_resting_max_values(mock_client)

    assert exc_info.value is error
