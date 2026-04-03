"""Pydantic input validators for MCP tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GetActivitiesInput(BaseModel):
    sport: int | None = Field(default=None, description="Filter by sport: 1=run, 2=bike")
    limit: int = Field(default=50, le=1000, gt=0, description="Max results to return")
    cursor: str | None = Field(default=None, description="Pagination cursor from previous response")


class GetActivityInput(BaseModel):
    activity_id: str = Field(description="Activity UUID")


class GetProcessedDataInput(BaseModel):
    activity_id: str = Field(description="Activity UUID")
    mode: Literal["summary", "window", "full"] = Field(
        default="summary",
        description="summary=aggregated stats, window=raw data for time range, full=all records",
    )
    window_start: int | None = Field(default=None, description="Start second for window mode")
    window_end: int | None = Field(default=None, description="End second for window mode")


class TagThresholdInput(BaseModel):
    threshold_type: Literal["vt1", "vt2", "bp", "vo2max"] = Field(description="Threshold type to tag")
    activity_id: str = Field(description="Activity UUID to tag threshold from")


class TagNewZoneInput(BaseModel):
    zone_type: Literal["fatmax", "vt1", "vt2", "vo2max"] = Field(description="Zone type to tag")
    activity_id: str = Field(description="Activity UUID to tag zone from")


class RespondMaxValueInput(BaseModel):
    detection_id: int = Field(description="Max value detection ID")
    accept: bool = Field(description="True to accept, False to dismiss")


class ExportInput(BaseModel):
    activity_id: str = Field(description="Activity UUID to export")


class UpdateProfileInput(BaseModel):
    weight: float | None = Field(default=None, description="Weight in current unit system")
    height: float | None = Field(default=None, description="Height in current unit system")
    units: Literal["SI", "imperial"] | None = Field(default=None, description="Unit system")
