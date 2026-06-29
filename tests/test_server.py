"""Tests for MCP server tool dispatch."""

import json
from unittest.mock import AsyncMock

import pytest

from tymewear_mcp import server as server_mod

NEW_TOOLS = [
    "tw_get_activity_logs",
    "tw_get_activity_strap_files",
    "tw_export_activity_strap_files",
    "tw_get_activity_workout_zone_detection",
    "tw_get_resting_max_values",
    "tw_get_training_plan",
    "tw_get_training_plan_by_date",
    "tw_get_training_plan_by_week",
    "tw_get_training_plan_history",
    "tw_get_training_plan_config",
    "tw_get_training_plan_preview",
    "tw_get_workout_recommendation",
    "tw_get_integrations",
    "tw_get_integration",
    "tw_get_integration_health",
    "tw_get_subscription_status",
    "tw_get_subscription_plans",
]


def _patch_profile(monkeypatch):
    monkeypatch.setattr(
        server_mod.profile_mod,
        "get_profile",
        AsyncMock(return_value={"id": 99999, "uuid": "user-uuid"}),
    )


async def test_list_tools_registers_new_athlete_read_tools():
    tools = await server_mod.list_tools()
    names = {tool.name for tool in tools}

    assert set(NEW_TOOLS).issubset(names)


async def test_tw_get_activities_forwards_dashboard_filters(monkeypatch):
    mock_client = AsyncMock()
    monkeypatch.setattr(server_mod, "_get_client", lambda: mock_client)
    monkeypatch.setattr(server_mod.profile_mod, "get_profile", AsyncMock(return_value={"id": 99999}))
    get_activities = AsyncMock(return_value={"next": None, "previous": None, "results": []})
    monkeypatch.setattr(server_mod.activities_mod, "get_activities", get_activities)

    await server_mod.call_tool(
        "tw_get_activities",
        {
            "sport": 2,
            "sports": ["1"],
            "activity_types": ["0", "6"],
            "search": "tempo",
            "limit": 25,
            "cursor": "abc",
            "user_id": "12345",
            "pro_team": "visma",
        },
    )

    get_activities.assert_awaited_once_with(
        mock_client,
        user_id=99999,
        sport=2,
        limit=25,
        cursor="abc",
        sports=["1"],
        activity_types=["0", "6"],
        search="tempo",
        requested_user_id="12345",
        pro_team="visma",
    )


@pytest.mark.parametrize(
    ("tool_name", "module_name", "function_name"),
    [
        ("tw_get_activity_logs", "activity_files_mod", "get_activity_logs"),
        ("tw_get_activity_strap_files", "activity_files_mod", "get_activity_strap_files"),
        ("tw_export_activity_strap_files", "activity_files_mod", "export_activity_strap_files"),
    ],
)
async def test_activity_file_routes_pass_activity_id(monkeypatch, tool_name, module_name, function_name):
    mock_client = AsyncMock()
    monkeypatch.setattr(server_mod, "_get_client", lambda: mock_client)
    route = AsyncMock(return_value={"tool": tool_name})
    monkeypatch.setattr(getattr(server_mod, module_name), function_name, route)

    result = await server_mod.call_tool(tool_name, {"activity_id": "activity-uuid"})

    route.assert_awaited_once_with(mock_client, "activity-uuid")
    assert json.loads(result[0].text) == {"tool": tool_name}


async def test_workout_zone_detection_route_forwards_include(monkeypatch):
    mock_client = AsyncMock()
    monkeypatch.setattr(server_mod, "_get_client", lambda: mock_client)
    route = AsyncMock(return_value={"tool": "tw_get_activity_workout_zone_detection"})
    monkeypatch.setattr(server_mod.activity_files_mod, "get_activity_workout_zone_detection", route)

    result = await server_mod.call_tool(
        "tw_get_activity_workout_zone_detection", {"activity_id": "activity-uuid"}
    )

    route.assert_awaited_once_with(mock_client, "activity-uuid", include=None)
    assert json.loads(result[0].text) == {"tool": "tw_get_activity_workout_zone_detection"}


@pytest.mark.parametrize(
    ("tool_name", "module_name", "function_name"),
    [
        ("tw_get_resting_max_values", "physiology_mod", "get_resting_max_values"),
        ("tw_get_integrations", "integrations_mod", "get_integrations"),
        ("tw_get_subscription_status", "account_mod", "get_subscription_status"),
        ("tw_get_subscription_plans", "account_mod", "get_subscription_plans"),
    ],
)
async def test_no_arg_routes_pass_client(monkeypatch, tool_name, module_name, function_name):
    mock_client = AsyncMock()
    monkeypatch.setattr(server_mod, "_get_client", lambda: mock_client)
    route = AsyncMock(return_value={"tool": tool_name})
    monkeypatch.setattr(getattr(server_mod, module_name), function_name, route)

    result = await server_mod.call_tool(tool_name, {})

    route.assert_awaited_once_with(mock_client)
    assert json.loads(result[0].text) == {"tool": tool_name}


@pytest.mark.parametrize(
    ("tool_name", "function_name"),
    [
        ("tw_get_training_plan", "get_training_plan"),
        ("tw_get_training_plan_history", "get_training_plan_history"),
        ("tw_get_training_plan_config", "get_training_plan_config"),
        ("tw_get_training_plan_preview", "get_training_plan_preview"),
    ],
)
async def test_training_plan_routes_pass_profile_uuid(monkeypatch, tool_name, function_name):
    mock_client = AsyncMock()
    monkeypatch.setattr(server_mod, "_get_client", lambda: mock_client)
    _patch_profile(monkeypatch)
    route = AsyncMock(return_value={"tool": tool_name})
    monkeypatch.setattr(server_mod.training_plans_mod, function_name, route)

    result = await server_mod.call_tool(tool_name, {})

    route.assert_awaited_once_with(mock_client, "user-uuid")
    assert json.loads(result[0].text) == {"tool": tool_name}


async def test_workout_recommendation_route_passes_profile_id(monkeypatch):
    mock_client = AsyncMock()
    monkeypatch.setattr(server_mod, "_get_client", lambda: mock_client)
    _patch_profile(monkeypatch)
    route = AsyncMock(return_value={"recommendation": "endurance"})
    monkeypatch.setattr(server_mod.training_plans_mod, "get_workout_recommendation", route)

    result = await server_mod.call_tool("tw_get_workout_recommendation", {})

    route.assert_awaited_once_with(mock_client, 99999)
    assert json.loads(result[0].text) == {"recommendation": "endurance"}


@pytest.mark.parametrize(
    ("tool_name", "function_name"),
    [
        ("tw_get_integration", "get_integration"),
        ("tw_get_integration_health", "get_integration_health"),
    ],
)
async def test_integration_routes_pass_integration_id(monkeypatch, tool_name, function_name):
    mock_client = AsyncMock()
    monkeypatch.setattr(server_mod, "_get_client", lambda: mock_client)
    route = AsyncMock(return_value={"integration": "garmin"})
    monkeypatch.setattr(server_mod.integrations_mod, function_name, route)

    result = await server_mod.call_tool(tool_name, {"integration_id": "garmin"})

    route.assert_awaited_once_with(mock_client, "garmin")
    assert json.loads(result[0].text) == {"integration": "garmin"}


@pytest.mark.parametrize(
    ("tool_name", "function_name", "arguments", "expected_extra"),
    [
        (
            "tw_get_training_plan_by_date",
            "get_training_plan_by_date",
            {"date": "2026-04-29"},
            "2026-04-29",
        ),
        (
            "tw_get_training_plan_by_week",
            "get_training_plan_by_week",
            {"week": "2026-W18"},
            "2026-W18",
        ),
    ],
)
async def test_training_plan_date_and_week_routes_validate_and_pass_value(
    monkeypatch,
    tool_name,
    function_name,
    arguments,
    expected_extra,
):
    mock_client = AsyncMock()
    monkeypatch.setattr(server_mod, "_get_client", lambda: mock_client)
    _patch_profile(monkeypatch)
    route = AsyncMock(return_value={"tool": tool_name})
    monkeypatch.setattr(server_mod.training_plans_mod, function_name, route)

    result = await server_mod.call_tool(tool_name, arguments)

    route.assert_awaited_once_with(mock_client, "user-uuid", expected_extra)
    assert json.loads(result[0].text) == {"tool": tool_name}


async def test_get_activity_insights_route(monkeypatch):
    mock_client = AsyncMock()
    monkeypatch.setattr(server_mod, "_get_client", lambda: mock_client)
    monkeypatch.setattr(
        server_mod.activity_files_mod,
        "get_activity_workout_zone_detection",
        AsyncMock(return_value={"thresholds_zone": {"VT1": {"VE": 60.7, "HR": 131.0, "confidence": "high"}}}),
    )
    monkeypatch.setattr(
        server_mod.activities_mod,
        "get_activity",
        AsyncMock(return_value={"id": "e4", "sport": "2", "sport_display": "Bike"}),
    )
    monkeypatch.setattr(
        server_mod.profile_mod,
        "get_profile",
        AsyncMock(return_value={"bike_ve_target_vt2": 114.0}),
    )

    result = await server_mod.call_tool("tw_get_activity_insights", {"activity_id": "e4"})

    data = json.loads(result[0].text)
    assert data["thresholds"]["VT1"]["ve"] == 60.7
    assert data["ve_targets"]["vt2"] == 114.0


async def test_compute_power_at_threshold_route(monkeypatch):
    mock_client = AsyncMock()
    monkeypatch.setattr(server_mod, "_get_client", lambda: mock_client)
    monkeypatch.setattr(
        server_mod.activity_files_mod, "get_activity_workout_zone_detection", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        server_mod.activities_mod,
        "get_activity",
        AsyncMock(return_value={"id": "e4", "sport": "2", "new_zone_vt1": "01:00", "predict_ve_v3": [1.0]}),
    )
    monkeypatch.setattr(server_mod.profile_mod, "get_profile", AsyncMock(return_value={"bike_ve_target_vt1": 58.7}))

    samples = [[float(t), 200.0] for t in range(50, 71)]
    result = await server_mod.call_tool(
        "tw_compute_power_at_threshold",
        {"activity_id": "e4", "power_samples": samples, "window_seconds": 10},
    )

    data = json.loads(result[0].text)
    assert data["power_at_threshold"]["vt1"]["power_watts"] == 200.0
    assert data["power_at_threshold"]["vt1"]["at_seconds"] == 60


def test_public_get_client_uses_stored_credentials(monkeypatch):
    from tymewear_mcp.client.http import TymeClient

    monkeypatch.setattr(server_mod, "_public_mode", True)
    monkeypatch.setattr(server_mod, "_client", None)

    class _Storage:
        def load(self):
            return {"email": "athlete@example.com", "password": "secret"}

    monkeypatch.setattr(server_mod, "CredentialStorage", _Storage)

    client = server_mod._get_client()
    assert isinstance(client, TymeClient)


def test_public_get_client_without_credentials_raises(monkeypatch):
    monkeypatch.setattr(server_mod, "_public_mode", True)
    monkeypatch.setattr(server_mod, "_client", None)

    class _Storage:
        def load(self):
            return None

    monkeypatch.setattr(server_mod, "CredentialStorage", _Storage)

    with pytest.raises(server_mod.PublicCredentialError, match="TYMEWEAR_EMAIL"):
        server_mod._get_client()
