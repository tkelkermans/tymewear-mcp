"""Tests for MCP server tool dispatch."""

from unittest.mock import AsyncMock

from tymewear_mcp import server as server_mod


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
