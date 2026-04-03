# tests/test_tools/test_thresholds.py
from unittest.mock import AsyncMock
import pytest
from tymewear_mcp.tools.thresholds import get_ve_targets, tag_threshold, tag_new_zone


class TestGetVeTargets:
    async def test_returns_targets(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"bike_vt1": 60.0, "bike_bp": 80.0, "bike_vt2": 110.0, "bike_vo2max": 160.0})
        mock_client.sanitize = lambda d: d
        result = await get_ve_targets(mock_client, user_id=99999)
        mock_client.get.assert_called_once_with("/api/users/99999/ve-targets/")
        assert result["bike_vt1"] == 60.0


class TestTagThreshold:
    async def test_tag_vt1(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value={"status": "ok"})
        mock_client.sanitize = lambda d: d
        await tag_threshold(mock_client, "vt1", "abc-123")
        mock_client.post.assert_called_once_with("/api/tag-vt1/", json={"activity_id": "abc-123"})

    async def test_tag_vo2max(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value={"status": "ok"})
        mock_client.sanitize = lambda d: d
        await tag_threshold(mock_client, "vo2max", "abc-123")
        mock_client.post.assert_called_once_with("/api/tag-v02max/", json={"activity_id": "abc-123"})


class TestTagNewZone:
    async def test_tag_fatmax(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value={"status": "ok"})
        mock_client.sanitize = lambda d: d
        await tag_new_zone(mock_client, "fatmax", "abc-123")
        mock_client.post.assert_called_once_with("/api/tag-new-zone-fatmax/", json={"activity_id": "abc-123"})

    async def test_tag_vt2(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value={"status": "ok"})
        mock_client.sanitize = lambda d: d
        await tag_new_zone(mock_client, "vt2", "abc-123")
        mock_client.post.assert_called_once_with("/api/tag-new-zone-vt2/", json={"activity_id": "abc-123"})
