"""Per-activity insight extraction.

Tyme Wear spreads the physiology a coach needs across two endpoints: the labeled
``workout-zone-detection`` (per-zone time/calories, threshold VE/HR/confidence,
quality, estimated power) and the activity detail (detected breakpoint *times* plus
the displayed power profile in unlabeled positional ``new_zone_*_metrics`` arrays).
``extract_activity_insights`` merges both with the athlete's profile VE targets into
one compact, labeled report.
"""

from __future__ import annotations

from typing import Any

# Positions inside the 28-element new_zone_<threshold>_metrics arrays (reverse-engineered).
_METRIC_INSTANT_POWER = 12
_METRIC_ROUNDED_POWER = 24


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


def extract_activity_insights(
    wzd: dict[str, Any], activity: dict[str, Any], profile: dict[str, Any]
) -> dict[str, Any]:
    wzd = wzd if isinstance(wzd, dict) else {}
    zones_raw = wzd.get("thresholds_zone")
    zones: dict[str, Any] = zones_raw if isinstance(zones_raw, dict) else {}
    steady_raw = wzd.get("steady_state_intensity")
    steady: dict[str, Any] = steady_raw if isinstance(steady_raw, dict) else {}

    # Labeled thresholds (VE/HR/confidence + estimated power) — present for tests and rides.
    thresholds: dict[str, Any] = {}
    for name, entry in zones.items():
        if name == "_quality" or not isinstance(entry, dict):
            continue
        steady_entry = steady.get(name)
        power = steady_entry.get("power") if isinstance(steady_entry, dict) else None
        thresholds[name] = {
            "ve": entry.get("VE"),
            "hr": entry.get("HR"),
            "confidence": entry.get("confidence"),
            "steady_state_power_w": round(power, 1) if isinstance(power, (int, float)) else None,
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

    # Detected breakpoints with displayed power profile (populated only for threshold tests).
    breakpoints: dict[str, Any] = {}
    for key in ("vt1", "vt2", "vo2max", "fatmax"):
        secs = _mmss_to_seconds(activity.get(f"new_zone_{key}"))
        if secs is None:
            continue
        metrics = activity.get(f"new_zone_{key}_metrics")
        breakpoints[key] = {
            "time": activity.get(f"new_zone_{key}"),
            "time_seconds": secs,
            "displayed_power_w": _metric_num(metrics, _METRIC_ROUNDED_POWER),
            "instant_power_w": _metric_num(metrics, _METRIC_INSTANT_POWER),
        }

    is_test = bool(activity.get("predict_ve_v3"))
    truncated = is_test and ("vt1" in breakpoints or "vt2" in breakpoints) and "vo2max" not in breakpoints

    return {
        "activity_id": activity.get("id"),
        "name": activity.get("name"),
        "sport": activity.get("sport_display"),
        "data_type": activity.get("data_type"),
        "duration": activity.get("duration"),
        "started_at": activity.get("time_stamp"),
        "unix_timestamp": activity.get("unix_timestamp"),
        "fitness_level": activity.get("new_zone_fitness_level"),
        "thresholds": thresholds,
        "detected_breakpoints": breakpoints,
        "ve_targets": _ve_targets(profile, activity.get("sport")),
        "zone_summary": wzd.get("zone_summary_table"),
        "zone_time_kcal": activity.get("new_zone_thresholds_kcal_hrs"),
        "min_max": wzd.get("min_max_used"),
        "quality": quality_out,
        "ve_curve_available": is_test,
        "truncated_test": truncated,
        "note": (
            "Power is recorded from the power meter paired in the Tyme Wear app (measured, not estimated). "
            "detected_breakpoints.displayed_power_w is the threshold power profile; "
            "thresholds.steady_state_power_w is Tyme Wear's separate steady-state figure for the zone."
        ),
    }


def compute_power_at_threshold(
    threshold_times: dict[str, int | None],
    power_samples: list[list[float | None]],
    window_seconds: int = 15,
) -> dict[str, Any]:
    """Average measured watts in a window around each detected breakpoint time.

    Tyme Wear has no measured power, so the caller supplies the power series
    ``[[t_seconds, watts], ...]`` from the matching TrainingPeaks/Garmin ride
    (watts may be ``None`` for gaps).
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
