"""Pydantic input validators for MCP tools."""

from __future__ import annotations

from typing import Literal
from urllib.parse import unquote

from pydantic import BaseModel, Field, field_validator

PATH_DELIMITERS = frozenset("/\\?#")


def _unquote_repeatedly(value: str) -> str:
    decoded = value
    for _ in range(3):
        next_decoded = unquote(decoded)
        if next_decoded == decoded:
            return decoded
        decoded = next_decoded
    return decoded


class ActivityIdMixin(BaseModel):
    @field_validator("activity_id", check_fields=False)
    @classmethod
    def validate_activity_id_path_segment(cls, value: str) -> str:
        decoded = _unquote_repeatedly(value)
        if not value or value != value.strip() or not decoded or decoded != decoded.strip():
            raise ValueError("activity_id must be a non-empty path segment without surrounding whitespace")
        if value in {".", ".."} or decoded in {".", ".."}:
            raise ValueError("activity_id cannot be a relative path segment")
        if any(delimiter in decoded for delimiter in PATH_DELIMITERS):
            raise ValueError("activity_id cannot contain path or query delimiters")
        return value


class GetActivitiesInput(BaseModel):
    sport: int | str | None = Field(default=None, description="Legacy sport filter: 1=run, 2=bike")

    @field_validator("sport")
    @classmethod
    def _coerce_sport(cls, value: int | str | None) -> int | None:
        if value is None:
            return None
        if isinstance(value, str):
            if not value.isdigit():
                raise ValueError("sport must be 1 (run) or 2 (bike)")
            return int(value)
        return value
    sports: list[str] | None = Field(default=None, description="Website dashboard sport query param filters")
    activity_types: list[str] | None = Field(default=None, description="Website dashboard type query param filters")
    search: str | None = Field(default=None, description="Search activity names and metadata")
    user_id: str | None = Field(default=None, description="Optional user id override for admin/trainer contexts")
    pro_team: str | None = Field(default=None, description="Optional pro team filter")
    limit: int = Field(default=50, le=1000, gt=0, description="Max results to return")
    cursor: str | None = Field(default=None, description="Pagination cursor from previous response")


class GetActivityInput(ActivityIdMixin):
    activity_id: str = Field(description="Activity UUID")


class GetActivityDetailInput(ActivityIdMixin):
    activity_id: str = Field(description="Activity UUID")
    include: list[str] | None = Field(
        default=None,
        description=(
            "Heavy fields to return verbatim instead of summarising under _omitted_fields, "
            "e.g. ['ext_bike_power','predict_ve_v3','times_zone']"
        ),
    )


class GetProcessedDataInput(ActivityIdMixin):
    activity_id: str = Field(description="Activity UUID")
    mode: Literal["summary", "window", "full"] = Field(
        default="summary",
        description="summary=aggregated stats, window=raw data for time range, full=all records",
    )
    window_start: int | None = Field(default=None, description="Start second for window mode")
    window_end: int | None = Field(default=None, description="End second for window mode")


class TagThresholdInput(ActivityIdMixin):
    threshold_type: Literal["vt1", "vt2", "bp", "vo2max"] = Field(description="Threshold type to tag")
    activity_id: str = Field(description="Activity UUID to tag threshold from")


class TagNewZoneInput(ActivityIdMixin):
    zone_type: Literal["fatmax", "vt1", "vt2", "vo2max"] = Field(description="Zone type to tag")
    activity_id: str = Field(description="Activity UUID to tag zone from")


class RespondMaxValueInput(BaseModel):
    detection_id: int = Field(description="Max value detection ID")
    accept: bool = Field(description="True to accept, False to dismiss")


class ExportInput(ActivityIdMixin):
    activity_id: str = Field(description="Activity UUID to export")


class UpdateProfileInput(BaseModel):
    weight: float | None = Field(default=None, description="Weight in current unit system")
    height: float | None = Field(default=None, description="Height in current unit system")
    units: Literal["SI", "imperial"] | None = Field(default=None, description="Unit system")


class TrainingPlanByDateInput(BaseModel):
    date: str = Field(description="ISO date in YYYY-MM-DD format", pattern=r"^\d{4}-\d{2}-\d{2}$")


class TrainingPlanByWeekInput(BaseModel):
    week: str = Field(description="Training plan week identifier, for example 2026-W18")


class IntegrationInput(BaseModel):
    integration_id: str = Field(
        min_length=1,
        pattern=r"^[^/]+$",
        description="Integration id or slug, for example garmin or intervals-icu",
    )
