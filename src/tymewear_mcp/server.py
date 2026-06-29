"""MCP server with tool registration."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from pydantic import ValidationError

from tymewear_mcp.auth.storage import CredentialStorage
from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.public import PublicCredentialError
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
from tymewear_mcp.tools import threshold_analysis as threshold_analysis_mod
from tymewear_mcp.tools import thresholds as thresholds_mod
from tymewear_mcp.tools import training_plans as training_plans_mod
from tymewear_mcp.tools import zones as zones_mod
from tymewear_mcp.tools._validation import (
    ComputePowerAtThresholdInput,
    ExportInput,
    GetActivitiesInput,
    GetActivityDetailInput,
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
_public_mode = False
_public_allow_mutations = False

_PUBLIC_DISABLED_EXPORT_TOOLS = {
    "tw_export_activity_strap_files",
    "tw_export_csv",
    "tw_export_csv_full",
    "tw_export_fit",
}
_PUBLIC_MUTATION_TOOLS = {
    "tw_delete_activity",
    "tw_pin_activity",
    "tw_respond_max_value",
    "tw_tag_new_zone",
    "tw_tag_threshold",
    "tw_update_profile",
}


def enable_public_mode(*, allow_mutations: bool = False) -> None:
    global _public_allow_mutations, _public_mode
    _public_mode = True
    _public_allow_mutations = allow_mutations


def disable_public_mode() -> None:
    global _public_allow_mutations, _public_mode
    _public_mode = False
    _public_allow_mutations = False


def _get_client() -> TymeClient:
    global _client
    if _public_mode:
        # Single-tenant: every authorized caller reads the operator's data via
        # server-side credentials. Read os.environ directly — CredentialStorage's
        # keyring/encrypted-file backends write under $HOME, which is read-only on
        # serverless (Vercel) and raises Errno 30 on every call.
        email = os.environ.get("TYMEWEAR_EMAIL")
        password = os.environ.get("TYMEWEAR_PASSWORD")
        if not (email and password):
            raise PublicCredentialError(
                "Public mode requires server-side Tyme Wear credentials (set TYMEWEAR_EMAIL/TYMEWEAR_PASSWORD)."
            )
        return TymeClient(credentials={"email": email, "password": password})

    if _client is not None:
        return _client
    storage = CredentialStorage()
    creds = storage.load()
    if creds is None:
        raise RuntimeError("No credentials found. Run: tymewear-mcp auth")
    _client = TymeClient(credentials=creds)
    return _client


def _public_exports_disabled_result() -> dict[str, Any]:
    return {
        "isError": True,
        "error_code": "PUBLIC_EXPORTS_DISABLED",
        "message": "File export tools are disabled in public mode because they would persist end-customer data.",
    }


def _public_mutations_disabled_result() -> dict[str, Any]:
    return {
        "isError": True,
        "error_code": "PUBLIC_MUTATIONS_DISABLED",
        "message": (
            "Mutation tools are disabled in public mode by default. "
            "Enable them explicitly only for trusted deployments."
        ),
    }


def _public_credentials_error_result(error: PublicCredentialError) -> dict[str, Any]:
    return {
        "isError": True,
        "error_code": "TYMEWEAR_UPSTREAM_TOKEN_REQUIRED",
        "message": str(error),
    }


def _public_validation_error_result() -> dict[str, Any]:
    return {
        "isError": True,
        "error_code": "INVALID_TOOL_ARGUMENTS",
        "message": "Invalid tool arguments.",
    }


def _public_unknown_tool_result() -> dict[str, Any]:
    return {
        "isError": True,
        "error_code": "UNKNOWN_TOOL",
        "message": "Unknown tool.",
    }


def _registered_tools() -> list[Tool]:
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
            description=(
                "Get full detail for a single Tyme Wear activity (thresholds, zones, TSS, duration). "
                "Large per-second arrays (x, predict_*, ext_*) are summarised under _omitted_fields by default; "
                "pass include=[...] to return specific heavy fields verbatim."
            ),
            inputSchema=GetActivityDetailInput.model_json_schema(),
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
            name="tw_get_activity_insights",
            description=(
                "Compact, labeled per-activity report: VT1/VT2/Endurance VE+HR+confidence, the measured "
                "power-at-threshold (from the meter paired in the Tyme Wear app), detected breakpoint times, "
                "per-zone time/calories, quality flags, a truncated-test flag, and the athlete's VE targets. "
                "Works for tests and rides."
            ),
            inputSchema=GetActivityInput.model_json_schema(),
        ),
        Tool(
            name="tw_compute_power_at_threshold",
            description=(
                "Cross-check/backfill: join an external power series to Tyme Wear's detected breakpoint times and "
                "return mean watts at VT1/VT2/VO2max/FatMax. Tyme Wear already records power from the meter paired "
                "in its app, so use this only to validate against a separate file or when an activity lacks power."
            ),
            inputSchema=ComputePowerAtThresholdInput.model_json_schema(),
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
            description=(
                "Get labeled workout zone detection for an activity: per-zone time/calories, "
                "VT1/VT2/Endurance VE+HR+confidence, quality flags, and estimated power. "
                "Per-second point clouds are summarised under _omitted_fields; pass include=[...] for them verbatim."
            ),
            inputSchema=GetActivityDetailInput.model_json_schema(),
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


def _registered_tool_names() -> set[str]:
    return {tool.name for tool in _registered_tools()}


@server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
async def list_tools() -> list[Tool]:
    tools = _registered_tools()
    if _public_mode:
        disabled_tools = set(_PUBLIC_DISABLED_EXPORT_TOOLS)
        if not _public_allow_mutations:
            disabled_tools.update(_PUBLIC_MUTATION_TOOLS)
        return [tool for tool in tools if tool.name not in disabled_tools]
    return tools


@server.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if _public_mode and name in _PUBLIC_DISABLED_EXPORT_TOOLS:
        return [TextContent(type="text", text=json.dumps(_public_exports_disabled_result(), indent=2))]
    if _public_mode and not _public_allow_mutations and name in _PUBLIC_MUTATION_TOOLS:
        return [TextContent(type="text", text=json.dumps(_public_mutations_disabled_result(), indent=2))]
    if _public_mode and name not in _registered_tool_names():
        return [TextContent(type="text", text=json.dumps(_public_unknown_tool_result(), indent=2))]

    try:
        client = _get_client()
    except PublicCredentialError as exc:
        return [TextContent(type="text", text=json.dumps(_public_credentials_error_result(exc), indent=2))]

    params: Any
    result: Any

    try:
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
            params = GetActivityDetailInput.model_validate(arguments)
            result = await activities_mod.get_activity(client, params.activity_id, include=params.include)

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
                client,
                params.activity_id,
                mode=params.mode,
                window_start=params.window_start,
                window_end=params.window_end,
            )

        elif name == "tw_get_new_processed_data":
            params = GetActivityInput.model_validate(arguments)
            result = await breathing_data_mod.get_new_processed_data(client, params.activity_id)

        elif name == "tw_get_ve_targets":
            profile = await profile_mod.get_profile(client)
            result = thresholds_mod.get_ve_targets(profile)

        elif name == "tw_get_activity_insights":
            params = GetActivityInput.model_validate(arguments)
            wzd = await activity_files_mod.get_activity_workout_zone_detection(client, params.activity_id)
            activity = await activities_mod.get_activity(client, params.activity_id, include=["predict_ve_v3"])
            profile = await profile_mod.get_profile(client)
            result = threshold_analysis_mod.extract_activity_insights(wzd, activity, profile)

        elif name == "tw_compute_power_at_threshold":
            params = ComputePowerAtThresholdInput.model_validate(arguments)
            wzd = await activity_files_mod.get_activity_workout_zone_detection(client, params.activity_id)
            activity = await activities_mod.get_activity(client, params.activity_id, include=["predict_ve_v3"])
            profile = await profile_mod.get_profile(client)
            insights = threshold_analysis_mod.extract_activity_insights(wzd, activity, profile)
            times = {key: bp["time_seconds"] for key, bp in insights["detected_breakpoints"].items()}
            result = {
                "activity_id": params.activity_id,
                "power_at_threshold": threshold_analysis_mod.compute_power_at_threshold(
                    times, params.power_samples, params.window_seconds
                ),
                "ve_targets": insights["ve_targets"],
                "truncated_test": insights["truncated_test"],
            }

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
            params = GetActivityDetailInput.model_validate(arguments)
            result = await activity_files_mod.get_activity_workout_zone_detection(
                client, params.activity_id, include=params.include
            )

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
    except ValidationError:
        if not _public_mode:
            raise
        result = _public_validation_error_result()
    finally:
        if _public_mode:
            await client.close()

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


def run_server() -> None:
    import asyncio

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_run())
