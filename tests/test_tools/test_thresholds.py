# tests/test_tools/test_thresholds.py
from unittest.mock import AsyncMock

from tymewear_mcp.tools.thresholds import get_ve_targets, tag_new_zone, tag_threshold


class TestGetVeTargets:
    def test_targets_from_profile(self):
        profile = {
            "bike_ve_target_vt1": 58.7, "bike_ve_target_bp": 77.6,
            "bike_ve_target_vt2": 114.0, "bike_ve_target_vo2max": 158.3,
            "running_ve_target_vt1": 0.0, "running_ve_target_bp": 0.0,
            "running_ve_target_vt2": 0.0, "running_ve_target_vo2max": 0.0,
        }
        result = get_ve_targets(profile)
        assert result["bike"] == {"vt1": 58.7, "bp": 77.6, "vt2": 114.0, "vo2max": 158.3}
        assert result["running"]["vt1"] == 0.0


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
