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
        assert result["thresholds"]["bike"]["vt1"]["ve"] == 58.7
        assert result["thresholds"]["bike"]["vt1"]["ve_unit"] == "vol/min"
        assert result["thresholds"]["bike"]["vt1"]["hr"] is None
        assert result["thresholds"]["bike"]["vt1"]["power_w"] is None
        assert result["units"]["ve"]["unit"] == "vol/min"
        assert result["availability"]["reason"] == "profile_ve_only"

    def test_profile_and_pinned_activity_supply_power_and_hr(self):
        profile = {
            "bike_ve_target_vt1": 81,
            "bike_ve_target_bp": 0,
            "bike_ve_target_vt2": 114,
            "bike_ve_target_vo2max": 0,
            "bike_hr_target_vt1": 144,
            "running_ve_target_vt1": 0,
            "running_ve_target_bp": 0,
            "running_ve_target_vt2": 0,
            "running_ve_target_vo2max": 0,
            "thresholds": {"bike": {"vt2": {"hr": 161, "power": 290}}},
        }
        wzd = {
            "available": True,
            "thresholds_zone": {"VT1": {"VE": 80.7, "HR": 143.6}, "VT2": {"VE": 113.4, "HR": 160.4}},
            "steady_state_intensity": {"VT1": {"power": 239.2}, "VT2": {"power": 288}},
        }
        result = get_ve_targets(profile, wzd, {"id": "22c58cb1-a717-45fc-9b66-ac87f144626d", "sport": "2"})

        vt1 = result["thresholds"]["bike"]["vt1"]
        vt2 = result["thresholds"]["bike"]["vt2"]
        assert vt1["ve"] == 81
        assert vt1["hr"] == 144
        assert vt1["power_w"] == 239.2
        assert vt1["sources"]["ve"] == "profile"
        assert vt1["sources"]["hr"] == "profile"
        assert vt1["sources"]["power_w"] == "pinned_activity"
        assert vt2["ve"] == 114
        assert vt2["hr"] == 161
        assert vt2["power_w"] == 290
        assert result["pinned_activity"]["activity_id"] == "22c58cb1-a717-45fc-9b66-ac87f144626d"
        assert result["availability"]["reason"] == "thresholds_include_power_ve_hr"


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
