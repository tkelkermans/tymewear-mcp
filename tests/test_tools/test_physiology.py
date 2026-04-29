from __future__ import annotations

from unittest.mock import AsyncMock

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
