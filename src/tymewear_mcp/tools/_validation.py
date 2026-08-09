"""Pydantic input validators for MCP tools."""

from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import unquote

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from tymewear_mcp.tools._safe_values import safe_name

PATH_DELIMITERS = frozenset("/\\?#")
ANALYSIS_CHANNEL_PATTERN = r"^[A-Za-z][A-Za-z0-9_. -]*$"
AnalysisChannel = Annotated[
    StrictStr,
    StringConstraints(max_length=64, pattern=ANALYSIS_CHANNEL_PATTERN),
]


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


class GetActivityAnalysisInput(ActivityIdMixin):
    model_config = ConfigDict(extra="forbid", strict=True)

    activity_id: str = Field(description="Activity UUID")
    offset: StrictInt = Field(default=0, ge=0)
    limit: StrictInt = Field(default=500, ge=1, le=1000)
    channels: list[AnalysisChannel] | None = Field(default=None, min_length=1, max_length=32)
    include_location: StrictBool = False

    @field_validator("channels")
    @classmethod
    def validate_channels(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if any(safe_name(channel, max_length=64) is None for channel in value):
            raise ValueError("channels must contain safe names of at most 64 characters")
        return value


class ComputePowerAtThresholdInput(ActivityIdMixin):
    activity_id: str = Field(description="Tyme Wear activity UUID to read detected threshold times from")
    power_samples: list[list[float | None]] = Field(
        description=(
            "Power series as [[t_seconds, watts], ...] from the matching TrainingPeaks/Garmin ride "
            "(watts may be null for gaps)"
        ),
    )
    window_seconds: int = Field(
        default=15, ge=0, le=120, description="Averaging half-window (seconds) around each breakpoint"
    )


class GetProcessedDataInput(ActivityIdMixin):
    activity_id: str = Field(description="Activity UUID")
    mode: Literal["summary", "window", "full"] = Field(
        default="summary",
        description="summary=aggregated stats, window=raw data for time range, full=all records",
    )
    window_start: int | None = Field(default=None, ge=0, description="Inclusive start second for window mode")
    window_end: int | None = Field(default=None, ge=0, description="Inclusive end second for window mode")

    @model_validator(mode="after")
    def validate_window_bounds(self) -> GetProcessedDataInput:
        if self.mode == "window":
            if self.window_start is None or self.window_end is None:
                raise ValueError("window mode requires both window_start and window_end")
            if self.window_end < self.window_start:
                raise ValueError("window_end must be greater than or equal to window_start")
        elif self.window_start is not None or self.window_end is not None:
            raise ValueError("window_start and window_end are only valid in window mode")
        return self


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
