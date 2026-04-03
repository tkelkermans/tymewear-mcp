from unittest.mock import AsyncMock
import pytest
from tymewear_mcp.tools.max_values import get_max_value_detections, respond_max_value


class TestGetMaxValueDetections:
    async def test_returns_detections(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=[{"id": 1, "type": "vt1", "value": 60.0}])
        mock_client.sanitize = lambda d: d
        result = await get_max_value_detections(mock_client)
        mock_client.get.assert_called_once_with("/v2/api/max-value-detections/")

    async def test_returns_empty_list(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=[])
        mock_client.sanitize = lambda d: d
        result = await get_max_value_detections(mock_client)
        assert result == []


class TestRespondMaxValue:
    async def test_accept(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value={"status": "accepted"})
        mock_client.sanitize = lambda d: d
        result = await respond_max_value(mock_client, detection_id=42, accept=True)
        mock_client.post.assert_called_once_with("/v2/api/max-value-detections/42/respond/", json={"accept": True})

    async def test_dismiss(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value={"status": "dismissed"})
        mock_client.sanitize = lambda d: d
        result = await respond_max_value(mock_client, detection_id=42, accept=False)
        mock_client.post.assert_called_once_with("/v2/api/max-value-detections/42/respond/", json={"accept": False})
