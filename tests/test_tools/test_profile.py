"""Tests for profile tools."""

from unittest.mock import AsyncMock

import pytest

from tymewear_mcp.tools.profile import get_profile, update_profile


SAMPLE_PROFILE = {
    "id": 99999, "email": "test@example.com", "gender": "M", "units": "SI",
    "is_active": True, "weight": 70.0, "weight_units": "SI",
    "birthday": "2000 Jan 01", "uuid": "abc-123", "raw_data_access": False,
    "height": 178, "height_units": "SI", "user_type": "trainee",
    "first_name": "Test", "last_name": "User",
    "external_accounts": {"GARMIN": "2025-01-01T00:00:00Z"},
    "bike_ve_target_vt1": 60.0, "bike_ve_target_bp": 80.0,
    "bike_ve_target_vt2": 110.0, "bike_ve_target_vo2max": 160.0,
    "running_ve_target_vt1": 0.0, "running_ve_target_bp": 0.0,
    "running_ve_target_vt2": 0.0, "running_ve_target_vo2max": 0.0,
    "zone_targets": [0, 0, 0, 0, 0], "toc_accepted": True,
    "toc_accepted_at": "2025-01-01", "workout_recommendation_access": False,
    "subscription_tier": "paid", "subscription_status": "active",
}


class TestGetProfile:
    async def test_returns_sanitized_profile(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=SAMPLE_PROFILE.copy())
        mock_client.sanitize = lambda d: {k: v for k, v in d.items() if k not in ("password", "token")}

        result = await get_profile(mock_client)
        assert result["id"] == 99999
        assert result["bike_ve_target_vt1"] == 60.0
        mock_client.get.assert_called_once_with("/v2/api/profile/")


class TestUpdateProfile:
    async def test_update_weight(self):
        mock_client = AsyncMock()
        updated = SAMPLE_PROFILE.copy()
        updated["weight"] = 73.0
        mock_client.patch = AsyncMock(return_value=updated)
        mock_client.sanitize = lambda d: d

        result = await update_profile(mock_client, profile_id=99999, weight=73.0)
        mock_client.patch.assert_called_once_with("/v2/api/profile/99999/", json={"weight": 73.0})
        assert result["weight"] == 73.0
