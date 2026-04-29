from __future__ import annotations

from unittest.mock import AsyncMock

from tymewear_mcp.tools.account import get_subscription_plans, get_subscription_status


async def test_get_subscription_status():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value={"status": "active"})
    mock_client.sanitize = lambda data: data

    result = await get_subscription_status(mock_client)

    mock_client.get.assert_called_once_with("/v2/api/subscription/status/")
    assert result == {"available": True, "status": "active"}


async def test_get_subscription_status_payload_cannot_override_availability():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value={"available": False, "status": "active"})
    mock_client.sanitize = lambda data: data

    result = await get_subscription_status(mock_client)

    assert result == {"available": True, "status": "active"}


async def test_get_subscription_plans():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=[{"name": "Pro"}])
    mock_client.sanitize = lambda data: data

    result = await get_subscription_plans(mock_client)

    mock_client.get.assert_called_once_with("/v2/api/subscription/plans/")
    assert result == {"available": True, "data": [{"name": "Pro"}]}
