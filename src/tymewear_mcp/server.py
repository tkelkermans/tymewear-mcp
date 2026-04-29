"""MCP server with tool registration."""

from __future__ import annotations

import json
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from tymewear_mcp.auth.storage import CredentialStorage
from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.tools import activities as activities_mod
from tymewear_mcp.tools import auth_status as auth_status_mod
from tymewear_mcp.tools import breathing_data as breathing_data_mod
from tymewear_mcp.tools import exports as exports_mod
from tymewear_mcp.tools import max_values as max_values_mod
from tymewear_mcp.tools import profile as profile_mod
from tymewear_mcp.tools import thresholds as thresholds_mod
from tymewear_mcp.tools import zones as zones_mod
from tymewear_mcp.tools._validation import (
    ExportInput,
    GetActivitiesInput,
    GetActivityInput,
    GetProcessedDataInput,
    RespondMaxValueInput,
    TagNewZoneInput,
    TagThresholdInput,
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


@server.list_tools()
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
            description="List Tyme Wear activities with pagination. Filter by sport (1=run, 2=bike).",
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


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    client = _get_client()

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
