"""Pydantic models for Tyme Wear API responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class Profile(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    email: str
    gender: str
    units: str
    is_active: bool
    weight: float
    weight_units: str
    birthday: str
    uuid: str
    raw_data_access: bool
    height: float
    height_units: str
    user_type: str
    first_name: str
    last_name: str
    external_accounts: dict[str, str]
    bike_ve_target_vt1: float
    bike_ve_target_bp: float
    bike_ve_target_vt2: float
    bike_ve_target_vo2max: float
    running_ve_target_vt1: float
    running_ve_target_bp: float
    running_ve_target_vt2: float
    running_ve_target_vo2max: float
    zone_targets: list[float]
    toc_accepted: bool
    toc_accepted_at: str | None
    workout_recommendation_access: bool
    subscription_tier: str
    subscription_status: str


class Activity(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    type: str
    type_display: str
    sport: str
    sport_display: str
    time_stamp: str
    tz_offset: str
    pinned: bool
    was_pinned: bool
    vt1: str
    vt2: str
    v02max: str
    duration: str
    duration_seconds: int
    user: int
    pinned_status: str | None
    algo_status: str
    app_version: str
    firmware_version: str
    hardware_version: str
    hr_firmware_version: str
    baseline: float | None
    max_amp: float | None
    fev1: float | None
    pod_id: str
    garmin_iq_app_v: str | None
    battery_life: int | None
    data_type: str
    success_rate: str
    kcal_expenditure: float | None
    zones_distribution_summary_table: list[Any]
    new_zone_distribution_summary_table: list[Any]


class ActivityDetail(Activity):
    algo_version: str
    placeholder: bool
    unix_timestamp: int
    tz_name: str
    intervals: dict[str, Any]
    third_party_activities: list[Any]
    is_bike: bool
    admin_notes: str
    ext_hr: list[Any]
    ext_bike_power: list[Any]
    ext_cadence: list[Any]
    ext_speed: list[Any]
    zones: list[Any]
    tss: float | None
    balance_point: str
    strap_model: str | None
    shirt_id: str
    fs: float | None
    imu_fs: float | None


class PaginatedActivities(BaseModel):
    next: str | None
    previous: str | None
    results: list[Activity]


class MaxValueDetection(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int


class RestingMaxValues(BaseModel):
    model_config = ConfigDict(extra="allow")
