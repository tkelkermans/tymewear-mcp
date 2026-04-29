# tests/test_tools/test_zones.py
from unittest.mock import AsyncMock

from tymewear_mcp.tools.zones import get_zone_distribution


class TestGetZoneDistribution:
    async def test_returns_distribution(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"zones": [100, 200, 150, 50]})
        mock_client.sanitize = lambda d: d
        await get_zone_distribution(mock_client, user_id=99999)
        mock_client.get.assert_called_once_with("/v2/api/users/99999/new-zone-distribution/")
