"""Tests for activity tools."""

from unittest.mock import AsyncMock

from tymewear_mcp.tools._validation import GetActivitiesInput
from tymewear_mcp.tools.activities import (
    delete_activity,
    get_activities,
    get_activity,
    get_activity_status,
    get_pinned_activity,
    pin_activity,
)

SAMPLE_ACTIVITY = {
    "id": "abc-123", "name": "Morning Ride", "type": "0",
    "type_display": "Normal Activity", "sport": "2", "sport_display": "Bike",
    "time_stamp": "2025 Jan 15 10:00:00", "duration": "01:30:00",
    "duration_seconds": 5400, "pinned": False, "algo_status": "success",
}


class TestGetActivities:
    async def test_list_activities(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={
            "next": None, "previous": None, "results": [SAMPLE_ACTIVITY],
        })
        mock_client.sanitize = lambda d: d
        result = await get_activities(mock_client, user_id=99999, sport=2, limit=10)
        mock_client.get.assert_called_once()
        call_kwargs = mock_client.get.call_args
        assert "user=99999" in str(call_kwargs) or "99999" in str(call_kwargs)
        assert len(result["results"]) == 1

    async def test_list_activities_no_sport_filter(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"next": None, "previous": None, "results": []})
        mock_client.sanitize = lambda d: d
        await get_activities(mock_client, user_id=99999)


class TestGetActivity:
    async def test_get_single_activity(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=SAMPLE_ACTIVITY)
        mock_client.sanitize = lambda d: d
        result = await get_activity(mock_client, "abc-123")
        mock_client.get.assert_called_once_with("/v2/api/activities/abc-123/")
        assert result["sport_display"] == "Bike"


class TestGetActivityStatus:
    async def test_get_status(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"status": "success"})
        mock_client.sanitize = lambda d: d
        await get_activity_status(mock_client, "abc-123")
        mock_client.get.assert_called_once_with("/v2/api/activities/abc-123/status/")


class TestPinActivity:
    async def test_pin(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value={"pinned": True})
        mock_client.sanitize = lambda d: d
        await pin_activity(mock_client, "abc-123")
        mock_client.post.assert_called_once_with("/api/activities/abc-123/pin/")


class TestGetPinnedActivity:
    async def test_get_pinned(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"id": "abc-123", "pinned": True})
        mock_client.sanitize = lambda d: d
        await get_pinned_activity(mock_client, user_id=99999)
        mock_client.get.assert_called_once_with("/api/users/99999/pinned-activity/")


class TestDeleteActivity:
    async def test_delete(self):
        mock_client = AsyncMock()
        mock_client.delete = AsyncMock(return_value=None)
        result = await delete_activity(mock_client, "abc-123")
        mock_client.delete.assert_called_once_with("/v2/api/activities/abc-123/")
        assert result["status"] == "deleted"


class TestActivityFilters:
    def test_validation_accepts_website_filters(self):
        params = GetActivitiesInput.model_validate(
            {
                "sport": 2,
                "sports": ["2"],
                "activity_types": ["0", "6"],
                "search": "tempo",
                "user_id": "99999",
                "pro_team": "visma",
            }
        )

        assert params.sport == 2
        assert params.sports == ["2"]
        assert params.activity_types == ["0", "6"]
        assert params.search == "tempo"
        assert params.user_id == "99999"
        assert params.pro_team == "visma"

    async def test_get_activities_sends_dashboard_filters(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"next": None, "previous": None, "results": []})
        mock_client.sanitize = lambda d: d

        await get_activities(
            mock_client,
            user_id=99999,
            sport=2,
            sports=["1"],
            activity_types=["0", "6"],
            search="tempo",
            limit=25,
            cursor="abc",
            requested_user_id="12345",
            pro_team="visma",
        )

        mock_client.get.assert_called_once_with(
            "/v2/api/activities-cursor/",
            params={
                "user": "12345",
                "limit": 25,
                "sport": ["1"],
                "type": ["0", "6"],
                "search": "tempo",
                "cursor": "abc",
                "pro_team": "visma",
            },
        )

    async def test_legacy_sport_maps_to_sport_filter(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"next": None, "previous": None, "results": []})
        mock_client.sanitize = lambda d: d

        await get_activities(mock_client, user_id=99999, sport=2)

        mock_client.get.assert_called_once_with(
            "/v2/api/activities-cursor/",
            params={"user": 99999, "limit": 50, "sport": ["2"]},
        )

    async def test_empty_sports_list_does_not_fall_back_to_legacy_sport(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"next": None, "previous": None, "results": []})
        mock_client.sanitize = lambda d: d

        await get_activities(mock_client, user_id=99999, sport=2, sports=[])

        mock_client.get.assert_called_once_with(
            "/v2/api/activities-cursor/",
            params={"user": 99999, "limit": 50},
        )


class TestSlimActivity:
    async def test_heavy_fields_omitted_by_default(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value={**SAMPLE_ACTIVITY, "x": [0] * 100, "predict_ve_v3": [1.0] * 3231, "new_zone_vt1": "37:27"}
        )
        mock_client.sanitize = lambda d: d
        result = await get_activity(mock_client, "abc-123")
        assert "x" not in result
        assert "predict_ve_v3" not in result
        assert result["_omitted_fields"]["x"]["length"] == 100
        assert result["new_zone_vt1"] == "37:27"

    async def test_include_restores_field(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={**SAMPLE_ACTIVITY, "x": [0] * 100})
        mock_client.sanitize = lambda d: d
        result = await get_activity(mock_client, "abc-123", include=["x"])
        assert result["x"] == [0] * 100
        assert "_omitted_fields" not in result
