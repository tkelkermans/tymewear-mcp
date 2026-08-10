"""Per-activity insight extraction.

Tyme Wear spreads the physiology a coach needs across two endpoints: the labeled
``workout-zone-detection`` (per-zone time/calories, threshold VE/HR/confidence,
quality, vendor-reported power) and the activity detail (detected breakpoint *times* plus
the displayed power profile in unlabeled positional ``new_zone_*_metrics`` arrays).
``extract_activity_insights`` merges both with the athlete's profile VE targets into
one compact, labeled report.
"""

from __future__ import annotations

from typing import Any, Literal

from tymewear_mcp.tools.timestamps import reconcile_activity_timestamp

# Positions inside the 28-element new_zone_<threshold>_metrics arrays (reverse-engineered).
_METRIC_INSTANT_POWER = 12
_METRIC_ROUNDED_POWER = 24

ActivityKind = Literal["normal", "test", "unknown"]


def _mmss_to_seconds(value: Any) -> int | None:
    """Parse a Tyme Wear "mm:ss" (or "h:mm:ss") elapsed-time string to seconds."""
    if not value or not isinstance(value, str):
        return None
    parts = value.split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    seconds = 0
    for num in nums:
        seconds = seconds * 60 + num
    return seconds


def _ve_targets(profile: dict[str, Any], sport: Any) -> dict[str, Any]:
    prefix = "running" if str(sport) == "1" else "bike"
    return {key: profile.get(f"{prefix}_ve_target_{key}") for key in ("vt1", "bp", "vt2", "vo2max")}


def _metric_num(metrics: Any, idx: int) -> float | None:
    if not isinstance(metrics, list) or idx >= len(metrics):
        return None
    try:
        return round(float(metrics[idx]), 1)
    except (TypeError, ValueError):
        return None


def _metric(value: Any, canonical_unit: str, source_path: str, method: str) -> dict[str, Any]:
    return {
        "value": value,
        "canonical_unit": canonical_unit,
        "source_path": source_path,
        "method": method,
    }


def _array_inventory(activity: dict[str, Any], field: str) -> dict[str, Any]:
    source_path = f"activity.{field}"
    value = activity.get(field)
    if isinstance(value, list):
        sample_count = len(value)
        return {
            "state": "observed" if sample_count else "reported_empty",
            "sample_count": sample_count,
            "source_path": source_path,
            "method": "array_length",
        }

    omitted = activity.get("_omitted_fields")
    omitted_entry = omitted.get(field) if isinstance(omitted, dict) else None
    length = omitted_entry.get("length") if isinstance(omitted_entry, dict) else None
    if isinstance(length, int) and not isinstance(length, bool) and length >= 0:
        return {
            "state": "observed" if length else "reported_empty",
            "sample_count": length,
            "source_path": source_path,
            "method": "omitted_field_length",
        }

    return {
        "state": "unknown",
        "sample_count": None,
        "source_path": source_path,
        "method": "not_reported",
    }


def _raw_channel_completeness(activity: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": "activity_array_inventory",
        "channels": {
            "ventilation": _array_inventory(activity, "predict_ve_v3"),
            "elapsed": _array_inventory(activity, "predict_time_v3"),
            "heart_rate": _array_inventory(activity, "ext_hr"),
            "power": _array_inventory(activity, "ext_bike_power"),
        },
    }


def _activity_kind(activity: dict[str, Any]) -> ActivityKind:
    type_display = activity.get("type_display")
    if isinstance(type_display, str):
        normalized_display = type_display.strip().casefold()
        if normalized_display == "normal activity":
            return "normal"
        if "test" in normalized_display:
            return "test"

    activity_type = activity.get("type")
    if not isinstance(activity_type, bool) and str(activity_type).strip() == "0":
        return "normal"
    return "unknown"


def _breakpoint_availability(name: str, *, detected: bool, activity_kind: ActivityKind) -> dict[str, str]:
    if detected:
        reason = "threshold_detected"
    elif activity_kind == "test":
        reason = "threshold_not_detected"
    elif activity_kind == "normal":
        reason = "normal_activity"
    else:
        reason = "activity_type_unknown"
    return {
        "state": "available" if detected else "not_computed",
        "reason": reason,
        "source": f"activity.new_zone_{name}",
    }


def _duration_metric(activity: dict[str, Any]) -> dict[str, Any]:
    duration_seconds = activity.get("duration_seconds")
    if isinstance(duration_seconds, (int, float)) and not isinstance(duration_seconds, bool):
        return _metric(duration_seconds, "s", "activity.duration_seconds", "reported")
    return _metric(_mmss_to_seconds(activity.get("duration")), "s", "activity.duration", "parsed_duration")


def extract_activity_insights(
    wzd: dict[str, Any], activity: dict[str, Any], profile: dict[str, Any]
) -> dict[str, Any]:
    wzd = wzd if isinstance(wzd, dict) else {}
    zones_raw = wzd.get("thresholds_zone")
    zones: dict[str, Any] = zones_raw if isinstance(zones_raw, dict) else {}
    steady_raw = wzd.get("steady_state_intensity")
    steady: dict[str, Any] = steady_raw if isinstance(steady_raw, dict) else {}

    # Labeled thresholds (VE/HR/confidence + vendor-reported power) — present for tests and rides.
    thresholds: dict[str, Any] = {}
    for name, entry in zones.items():
        if name == "_quality" or not isinstance(entry, dict):
            continue
        steady_entry = steady.get(name)
        power = steady_entry.get("power") if isinstance(steady_entry, dict) else None
        ve = entry.get("VE")
        hr = entry.get("HR")
        steady_state_power = round(power, 1) if isinstance(power, (int, float)) else None
        thresholds[name] = {
            "ve": ve,
            "hr": hr,
            "confidence": entry.get("confidence"),
            "steady_state_power_w": steady_state_power,
            "metrics": {
                "ve": _metric(ve, "L/min", f"wzd.thresholds_zone.{name}.VE", "workout_zone_detection"),
                "hr": _metric(hr, "bpm", f"wzd.thresholds_zone.{name}.HR", "workout_zone_detection"),
                "steady_state_power": _metric(
                    steady_state_power,
                    "W",
                    f"wzd.steady_state_intensity.{name}.power",
                    "workout_zone_detection_steady_state",
                ),
            },
        }

    quality_raw = zones.get("_quality")
    quality = quality_raw if isinstance(quality_raw, dict) else None
    quality_out = (
        {
            "fit_r2": quality.get("fit_r2"),
            "per_threshold_confidence": quality.get("per_threshold_confidence"),
            "reason": quality.get("reason"),
        }
        if quality
        else None
    )

    raw_channel_completeness = _raw_channel_completeness(activity)
    ve_sample_count = raw_channel_completeness["channels"]["ventilation"]["sample_count"]
    ve_curve_available = isinstance(ve_sample_count, int) and ve_sample_count > 0

    parsed_breakpoints = {
        key: _mmss_to_seconds(activity.get(f"new_zone_{key}"))
        for key in ("vt1", "vt2", "vo2max", "fatmax")
    }
    activity_kind = _activity_kind(activity)

    # Detected breakpoints with displayed power profile (populated only for threshold tests).
    detected_breakpoints: dict[str, Any] = {}
    breakpoints: dict[str, Any] = {}
    for key in ("vt1", "vt2", "vo2max", "fatmax"):
        secs = parsed_breakpoints[key]
        if secs is None:
            breakpoints[key] = {
                "availability": _breakpoint_availability(key, detected=False, activity_kind=activity_kind)
            }
            continue
        metrics = activity.get(f"new_zone_{key}_metrics")
        displayed_power = _metric_num(metrics, _METRIC_ROUNDED_POWER)
        instant_power = _metric_num(metrics, _METRIC_INSTANT_POWER)
        breakpoint = {
            "availability": _breakpoint_availability(key, detected=True, activity_kind=activity_kind),
            "time": activity.get(f"new_zone_{key}"),
            "time_seconds": secs,
            "displayed_power_w": displayed_power,
            "instant_power_w": instant_power,
            "metrics": {
                "elapsed": _metric(
                    secs,
                    "s",
                    f"activity.new_zone_{key}",
                    "detected_breakpoint",
                ),
                "displayed_power": _metric(
                    displayed_power,
                    "W",
                    f"activity.new_zone_{key}_metrics[{_METRIC_ROUNDED_POWER}]",
                    "positional_metric_array",
                ),
                "instant_power": _metric(
                    instant_power,
                    "W",
                    f"activity.new_zone_{key}_metrics[{_METRIC_INSTANT_POWER}]",
                    "positional_metric_array",
                ),
            },
        }
        breakpoints[key] = breakpoint
        detected_breakpoints[key] = breakpoint

    truncated = (
        activity_kind == "test"
        and ("vt1" in detected_breakpoints or "vt2" in detected_breakpoints)
        and "vo2max" not in detected_breakpoints
    )
    timestamps = reconcile_activity_timestamp(
        unix_timestamp=activity.get("unix_timestamp"),
        source_timestamp=activity.get("time_stamp"),
        tz_name=activity.get("tz_name"),
        tz_offset=activity.get("tz_offset"),
    )

    return {
        "activity_id": activity.get("id"),
        "name": activity.get("name"),
        "sport": activity.get("sport_display"),
        "data_type": activity.get("data_type"),
        "duration": activity.get("duration"),
        "started_at": timestamps["utc"],
        "unix_timestamp": activity.get("unix_timestamp"),
        "timestamps": timestamps,
        "fitness_level": activity.get("new_zone_fitness_level"),
        "thresholds": thresholds,
        "breakpoints": breakpoints,
        "detected_breakpoints": detected_breakpoints,
        "ve_targets": _ve_targets(profile, activity.get("sport")),
        "zone_summary": wzd.get("zone_summary_table"),
        "zone_time_kcal": activity.get("new_zone_thresholds_kcal_hrs"),
        "metrics": {
            "elapsed": _duration_metric(activity),
            "energy": _metric(
                activity.get("kcal_expenditure"),
                "kcal",
                "activity.kcal_expenditure",
                "reported",
            ),
        },
        "model_input_bounds": {
            "values": wzd.get("min_max_used"),
            "source_path": "wzd.min_max_used",
            "method": "model_calibration_input",
            "interpretation": "model_calibration_bounds_not_activity_extrema",
        },
        "quality": quality_out,
        "raw_channel_completeness": raw_channel_completeness,
        "ve_curve_available": ve_curve_available,
        "truncated_test": truncated,
        "note": (
            "thresholds.steady_state_power_w is vendor-reported from wzd.steady_state_intensity; "
            "breakpoint power is vendor-reported from positional activity metric arrays. "
            "The MCP does not verify the upstream calculation or measurement method."
        ),
    }


def compute_power_at_threshold(
    threshold_times: dict[str, int | None],
    power_samples: list[list[float | None]],
    window_seconds: int = 15,
) -> dict[str, Any]:
    """Average supplied watts in a window around each detected breakpoint time.

    The caller supplies ``[[t_seconds, watts], ...]`` from a matching external
    activity; watts may be ``None`` for gaps.
    """
    series = [(float(t), float(w)) for t, w in power_samples if t is not None and w is not None]
    out: dict[str, Any] = {}
    for name, secs in threshold_times.items():
        if secs is None:
            out[name] = None
            continue
        window = [w for (t, w) in series if abs(t - secs) <= window_seconds]
        out[name] = {
            "power_watts": round(sum(window) / len(window), 1) if window else None,
            "samples": len(window),
            "at_seconds": secs,
        }
    return out
