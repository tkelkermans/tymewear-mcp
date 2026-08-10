from __future__ import annotations

from unittest.mock import AsyncMock

import httpx

from tymewear_mcp.tools._validation import TrainingPlanByDateInput, TrainingPlanByWeekInput
from tymewear_mcp.tools.training_plans import (
    get_training_plan,
    get_training_plan_by_date,
    get_training_plan_by_week,
    get_training_plan_config,
    get_training_plan_history,
    get_training_plan_preview,
    get_workout_recommendation,
)


class TestTrainingPlanValidation:
    def test_date_input_accepts_iso_date(self):
        params = TrainingPlanByDateInput.model_validate({"date": "2026-04-28"})
        assert params.date == "2026-04-28"

    def test_week_input_accepts_string(self):
        params = TrainingPlanByWeekInput.model_validate({"week": "2026-W18"})
        assert params.week == "2026-W18"


class TestTrainingPlanTools:
    async def test_get_training_plan(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"weeks": []})
        mock_client.sanitize = lambda data: data

        result = await get_training_plan(mock_client, "user-uuid")

        mock_client.get.assert_called_once_with("/v2/api/users/user-uuid/training-plan/")
        assert result == {"available": True, "weeks": []}

    async def test_get_training_plan_by_date(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"date": "2026-04-28"})
        mock_client.sanitize = lambda data: data

        await get_training_plan_by_date(mock_client, "user-uuid", "2026-04-28")

        mock_client.get.assert_called_once_with(
            "/v2/api/users/user-uuid/training-plan/",
            params={"date": "2026-04-28"},
        )

    async def test_get_training_plan_by_week(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"week": "2026-W18"})
        mock_client.sanitize = lambda data: data

        await get_training_plan_by_week(mock_client, "user-uuid", "2026-W18")

        mock_client.get.assert_called_once_with(
            "/v2/api/users/user-uuid/training-plan/",
            params={"week": "2026-W18"},
        )

    async def test_get_training_plan_history(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=[])
        mock_client.sanitize = lambda data: data

        await get_training_plan_history(mock_client, "user-uuid")

        mock_client.get.assert_called_once_with("/v2/api/users/user-uuid/training-plans/history/")

    async def test_get_training_plan_config(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"hours": 8})
        mock_client.sanitize = lambda data: data

        await get_training_plan_config(mock_client, "user-uuid")

        mock_client.get.assert_called_once_with("/v2/api/users/user-uuid/training-plan-config/")

    async def test_get_training_plan_preview(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"preview": []})
        mock_client.sanitize = lambda data: data

        await get_training_plan_preview(mock_client, "user-uuid")

        mock_client.get.assert_called_once_with("/v2/api/users/user-uuid/training-plan-preview/")

    async def test_get_workout_recommendation_uses_user_id(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"recommendation": "endurance"})
        mock_client.sanitize = lambda data: data

        await get_workout_recommendation(mock_client, 99999)

        mock_client.get.assert_called_once_with("/api/users/99999/workout-recommendation/")

    async def test_available_flag_cannot_be_overridden_by_api_payload(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"available": False, "weeks": []})
        mock_client.sanitize = lambda data: data

        result = await get_training_plan(mock_client, "user-uuid")

        assert result == {"available": True, "weeks": []}

    async def test_404_returns_availability_result(self):
        request = httpx.Request("GET", "https://api.tymewear.com/v2/api/users/user-uuid/training-plan/")
        response = httpx.Response(404, json={"detail": "No plan"}, request=request)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError("No plan", request=request, response=response))

        result = await get_training_plan(mock_client, "user-uuid")

        assert result["available"] is False
        assert result["reason"] == "not_found"
