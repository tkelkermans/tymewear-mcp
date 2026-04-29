"""MCP server with tool registration."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from tymewear_mcp.auth.storage import CredentialStorage
from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.tools import account as account_mod
from tymewear_mcp.tools import activities as activities_mod
from tymewear_mcp.tools import activity_files as activity_files_mod
from tymewear_mcp.tools import auth_status as auth_status_mod
from tymewear_mcp.tools import breathing_data as breathing_data_mod
from tymewear_mcp.tools import exports as exports_mod
from tymewear_mcp.tools import integrations as integrations_mod
from tymewear_mcp.tools import max_values as max_values_mod
from tymewear_mcp.tools import physiology as physiology_mod
from tymewear_mcp.tools import profile as profile_mod
from tymewear_mcp.tools import thresholds as thresholds_mod
from tymewear_mcp.tools import training_plans as training_plans_mod
from tymewear_mcp.tools import zones as zones_mod
from tymewear_mcp.tools._validation import (
    ExportInput,
    GetActivitiesInput,
    GetActivityInput,
    GetProcessedDataInput,
    IntegrationInput,
    RespondMaxValueInput,
    TagNewZoneInput,
    TagThresholdInput,
    TrainingPlanByDateInput,
    TrainingPlanByWeekInput,
    UpdateProfileInput,
)

logger = logging.getLogger(__name__)

server = Server("tymewear-mcp")
_client: TymeClient | None = None


def _get_client() -> TymeClient:
    global _client
    if _client is not None:
        return _client
    storage = CredentialStorage()
    creds = storage.load()
    if creds is None:
        raise RuntimeError("No credentials found. Run: tymewear-mcp auth")
    _client = TymeClient(credentials=creds)
    return _client


@server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="tw_auth_status",
            description="Check Tyme Wear authentication status and token validity.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_get_profile",
            description=(
                "Get the current user's Tyme Wear profile including weight, height, "
                "VE targets (VT1, BP, VT2, VO2max) per sport, subscription status, and external accounts."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_update_profile",
            description="Update Tyme Wear profile fields (weight, height, units).",
            inputSchema=UpdateProfileInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_activities",
            description=(
                "List Tyme Wear activities with cursor pagination. Supports legacy sport filter "
                "(1=run, 2=bike) plus website filters: sports, activity_types, search, user_id, and pro_team."
            ),
            inputSchema=GetActivitiesInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_activity",
            description="Get full detail for a single Tyme Wear activity including thresholds, zones, TSS, duration.",
            inputSchema=GetActivityInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_activity_status",
            description="Get algorithm processing status for a Tyme Wear activity.",
            inputSchema=GetActivityInput.model_json_schema(),
        ),
        Tool(
            name="tw_pin_activity",
            description="Pin or unpin a Tyme Wear activity for threshold detection.",
            inputSchema=GetActivityInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_pinned_activity",
            description="Get the currently pinned Tyme Wear activity used for threshold detection.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_delete_activity",
            description="Delete a Tyme Wear activity. This action is irreversible.",
            inputSchema=GetActivityInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_processed_data",
            description=(
                "Get per-second breathing time-series for a Tyme Wear activity. "
                "Includes breathing rate, tidal volume, minute ventilation, HR, power, cadence, VE zones. "
                "Modes: summary (default), window (time range), full (all records)."
            ),
            inputSchema=GetProcessedDataInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_new_processed_data",
            description="Get new-format processed breathing data for a Tyme Wear activity (if available).",
            inputSchema=GetActivityInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_ve_targets",
            description="Get current VE threshold targets (VT1, BP, VT2, VO2max) per sport for the athlete.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_get_zone_distribution",
            description="Get ventilation zone time distribution across activities.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_tag_threshold",
            description="Tag a ventilatory threshold (vt1, vt2, bp, vo2max) from a specific activity.",
            inputSchema=TagThresholdInput.model_json_schema(),
        ),
        Tool(
            name="tw_tag_new_zone",
            description="Tag a new-model zone value (fatmax, vt1, vt2, vo2max) from a specific activity.",
            inputSchema=TagNewZoneInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_max_value_detections",
            description="List pending max value detection notifications from Tyme Wear.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_respond_max_value",
            description="Accept or dismiss a Tyme Wear max value detection notification.",
            inputSchema=RespondMaxValueInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_activity_logs",
            description="Get logs associated with a Tyme Wear activity.",
            inputSchema=GetActivityInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_activity_strap_files",
            description="Get strap files associated with a Tyme Wear activity.",
            inputSchema=GetActivityInput.model_json_schema(),
        ),
        Tool(
            name="tw_export_activity_strap_files",
            description="Export strap files for a Tyme Wear activity.",
            inputSchema=ExportInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_activity_workout_zone_detection",
            description="Get workout zone detection data for a Tyme Wear activity.",
            inputSchema=GetActivityInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_resting_max_values",
            description="Get resting and max physiology values for the athlete.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_get_training_plan",
            description="Get the athlete's current training plan.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_get_training_plan_by_date",
            description="Get training plan entries for a specific date.",
            inputSchema=TrainingPlanByDateInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_training_plan_by_week",
            description="Get training plan entries for a specific week.",
            inputSchema=TrainingPlanByWeekInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_training_plan_history",
            description="Get the athlete's training plan history.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_get_training_plan_config",
            description="Get the athlete's training plan configuration.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_get_training_plan_preview",
            description="Get a preview of the athlete's training plan.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_get_workout_recommendation",
            description="Get the athlete's workout recommendation.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_get_integrations",
            description="List connected Tyme Wear integrations.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_get_integration",
            description="Get details for a Tyme Wear integration.",
            inputSchema=IntegrationInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_integration_health",
            description="Get health status for a Tyme Wear integration.",
            inputSchema=IntegrationInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_subscription_status",
            description="Get the athlete's Tyme Wear subscription status.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_get_subscription_plans",
            description="List available Tyme Wear subscription plans.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_export_csv",
            description="Export a Tyme Wear activity as CSV file.",
            inputSchema=ExportInput.model_json_schema(),
        ),
        Tool(
            name="tw_export_csv_full",
            description="Export a Tyme Wear activity as full CSV with all data channels.",
            inputSchema=ExportInput.model_json_schema(),
        ),
        Tool(
            name="tw_export_fit",
            description="Export a Tyme Wear activity as FIT file.",
            inputSchema=ExportInput.model_json_schema(),
        ),
    ]


@server.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    client = _get_client()
    params: Any
    result: Any

    if name == "tw_auth_status":
        result = await auth_status_mod.auth_status(client)

    elif name == "tw_get_profile":
        result = await profile_mod.get_profile(client)

    elif name == "tw_update_profile":
        params = UpdateProfileInput.model_validate(arguments)
        profile = await profile_mod.get_profile(client)
        result = await profile_mod.update_profile(
            client,
            profile_id=profile["id"],
            weight=params.weight,
            height=params.height,
            units=params.units,
        )

    elif name == "tw_get_activities":
        params = GetActivitiesInput.model_validate(arguments)
        profile = await profile_mod.get_profile(client)
        result = await activities_mod.get_activities(
            client,
            user_id=profile["id"],
            sport=params.sport,
            limit=params.limit,
            cursor=params.cursor,
            sports=params.sports,
            activity_types=params.activity_types,
            search=params.search,
            requested_user_id=params.user_id,
            pro_team=params.pro_team,
        )

    elif name == "tw_get_activity":
        params = GetActivityInput.model_validate(arguments)
        result = await activities_mod.get_activity(client, params.activity_id)

    elif name == "tw_get_activity_status":
        params = GetActivityInput.model_validate(arguments)
        result = await activities_mod.get_activity_status(client, params.activity_id)

    elif name == "tw_pin_activity":
        params = GetActivityInput.model_validate(arguments)
        result = await activities_mod.pin_activity(client, params.activity_id)

    elif name == "tw_get_pinned_activity":
        profile = await profile_mod.get_profile(client)
        result = await activities_mod.get_pinned_activity(client, user_id=profile["id"])

    elif name == "tw_delete_activity":
        params = GetActivityInput.model_validate(arguments)
        result = await activities_mod.delete_activity(client, params.activity_id)

    elif name == "tw_get_processed_data":
        params = GetProcessedDataInput.model_validate(arguments)
        result = await breathing_data_mod.get_processed_data(
            client, params.activity_id,
            mode=params.mode, window_start=params.window_start, window_end=params.window_end,
        )

    elif name == "tw_get_new_processed_data":
        params = GetActivityInput.model_validate(arguments)
        result = await breathing_data_mod.get_new_processed_data(client, params.activity_id)

    elif name == "tw_get_ve_targets":
        profile = await profile_mod.get_profile(client)
        result = await thresholds_mod.get_ve_targets(client, user_id=profile["id"])

    elif name == "tw_get_zone_distribution":
        profile = await profile_mod.get_profile(client)
        result = await zones_mod.get_zone_distribution(client, user_id=profile["id"])

    elif name == "tw_tag_threshold":
        params = TagThresholdInput.model_validate(arguments)
        result = await thresholds_mod.tag_threshold(client, params.threshold_type, params.activity_id)

    elif name == "tw_tag_new_zone":
        params = TagNewZoneInput.model_validate(arguments)
        result = await thresholds_mod.tag_new_zone(client, params.zone_type, params.activity_id)

    elif name == "tw_get_max_value_detections":
        result = await max_values_mod.get_max_value_detections(client)

    elif name == "tw_respond_max_value":
        params = RespondMaxValueInput.model_validate(arguments)
        result = await max_values_mod.respond_max_value(client, params.detection_id, params.accept)

    elif name == "tw_get_activity_logs":
        params = GetActivityInput.model_validate(arguments)
        result = await activity_files_mod.get_activity_logs(client, params.activity_id)

    elif name == "tw_get_activity_strap_files":
        params = GetActivityInput.model_validate(arguments)
        result = await activity_files_mod.get_activity_strap_files(client, params.activity_id)

    elif name == "tw_export_activity_strap_files":
        params = ExportInput.model_validate(arguments)
        result = await activity_files_mod.export_activity_strap_files(client, params.activity_id)

    elif name == "tw_get_activity_workout_zone_detection":
        params = GetActivityInput.model_validate(arguments)
        result = await activity_files_mod.get_activity_workout_zone_detection(client, params.activity_id)

    elif name == "tw_get_resting_max_values":
        result = await physiology_mod.get_resting_max_values(client)

    elif name == "tw_get_training_plan":
        profile = await profile_mod.get_profile(client)
        result = await training_plans_mod.get_training_plan(client, profile["uuid"])

    elif name == "tw_get_training_plan_by_date":
        params = TrainingPlanByDateInput.model_validate(arguments)
        profile = await profile_mod.get_profile(client)
        result = await training_plans_mod.get_training_plan_by_date(client, profile["uuid"], params.date)

    elif name == "tw_get_training_plan_by_week":
        params = TrainingPlanByWeekInput.model_validate(arguments)
        profile = await profile_mod.get_profile(client)
        result = await training_plans_mod.get_training_plan_by_week(client, profile["uuid"], params.week)

    elif name == "tw_get_training_plan_history":
        profile = await profile_mod.get_profile(client)
        result = await training_plans_mod.get_training_plan_history(client, profile["uuid"])

    elif name == "tw_get_training_plan_config":
        profile = await profile_mod.get_profile(client)
        result = await training_plans_mod.get_training_plan_config(client, profile["uuid"])

    elif name == "tw_get_training_plan_preview":
        profile = await profile_mod.get_profile(client)
        result = await training_plans_mod.get_training_plan_preview(client, profile["uuid"])

    elif name == "tw_get_workout_recommendation":
        profile = await profile_mod.get_profile(client)
        result = await training_plans_mod.get_workout_recommendation(client, profile["id"])

    elif name == "tw_get_integrations":
        result = await integrations_mod.get_integrations(client)

    elif name == "tw_get_integration":
        params = IntegrationInput.model_validate(arguments)
        result = await integrations_mod.get_integration(client, params.integration_id)

    elif name == "tw_get_integration_health":
        params = IntegrationInput.model_validate(arguments)
        result = await integrations_mod.get_integration_health(client, params.integration_id)

    elif name == "tw_get_subscription_status":
        result = await account_mod.get_subscription_status(client)

    elif name == "tw_get_subscription_plans":
        result = await account_mod.get_subscription_plans(client)

    elif name == "tw_export_csv":
        params = ExportInput.model_validate(arguments)
        result = await exports_mod.export_csv(client, params.activity_id)

    elif name == "tw_export_csv_full":
        params = ExportInput.model_validate(arguments)
        result = await exports_mod.export_csv_full(client, params.activity_id)

    elif name == "tw_export_fit":
        params = ExportInput.model_validate(arguments)
        result = await exports_mod.export_fit(client, params.activity_id)

    else:
        result = {"error": f"Unknown tool: {name}"}

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


def run_server() -> None:
    import asyncio

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_run())
