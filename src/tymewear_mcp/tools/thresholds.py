from __future__ import annotations

import re
from typing import Any, cast

import httpx

from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.tools._safe_values import finite_number
from tymewear_mcp.tools.activities import get_pinned_activity
from tymewear_mcp.tools.activity_files import get_activity_workout_zone_detection

_THRESHOLD_ENDPOINTS = {
    "vt1": "/api/tag-vt1/",
    "vt2": "/api/tag-vt2/",
    "bp": "/api/tag-bp/",
    "vo2max": "/api/tag-v02max/",
}
_NEW_ZONE_ENDPOINTS = {
    "fatmax": "/api/tag-new-zone-fatmax/",
    "vt1": "/api/tag-new-zone-vt1/",
    "vt2": "/api/tag-new-zone-vt2/",
    "vo2max": "/api/tag-new-zone-vo2max/",
}
_THRESHOLD_NAMES = ("vt1", "bp", "vt2", "vo2max")
_SPORTS = ("bike", "running")
_NAME_TOKENS = {
    "vt1": "vt1",
    "vt2": "vt2",
    "bp": "bp",
    "balance": "bp",
    "balancepoint": "bp",
    "vo2max": "vo2max",
    "vo2": "vo2max",
}
_METRIC_TOKENS = {
    "ve": "ve",
    "ventilation": "ve",
    "hr": "hr",
    "heart": "hr",
    "heartrate": "hr",
    "power": "power_w",
    "watts": "power_w",
    "powerw": "power_w",
}
_SPORT_TOKENS = {
    "bike": "bike",
    "cycling": "bike",
    "cycle": "bike",
    "ride": "bike",
    "running": "running",
    "run": "running",
}
_WZD_NAMES = {
    "vt1": "vt1",
    "vt2": "vt2",
    "bp": "bp",
    "balancepoint": "bp",
    "vo2max": "vo2max",
    "v02max": "vo2max",
}
_UNITS = {
    "ve": {"unit": "vol/min", "dashboard_label": "Minute Volume", "equivalent": "L/min"},
    "hr": {"unit": "bpm", "dashboard_label": "Heart rate"},
    "power": {"unit": "W", "dashboard_label": "Power"},
}


def _blank_threshold() -> dict[str, Any]:
    return {
        "ve": None,
        "ve_unit": "vol/min",
        "hr": None,
        "hr_unit": "bpm",
        "power_w": None,
        "power_unit": "W",
        "sources": {},
    }


def _sport_table() -> dict[str, dict[str, dict[str, Any]]]:
    return {sport: {name: _blank_threshold() for name in _THRESHOLD_NAMES} for sport in _SPORTS}


def _assign(
    table: dict[str, dict[str, dict[str, Any]]],
    sport: str,
    name: str,
    metric: str,
    value: Any,
    source: str,
) -> None:
    if sport not in table or name not in _THRESHOLD_NAMES or metric not in {"ve", "hr", "power_w"}:
        return
    number = finite_number(value)
    if not isinstance(number, (int, float)):
        return
    entry = table[sport][name]
    if entry["sources"].get(metric) == "profile" and source != "profile":
        return
    entry[metric] = round(float(number), 1) if source != "profile" else number
    entry["sources"][metric] = source


def _tokens(value: str) -> list[str]:
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return [part for part in re.split(r"[^a-z0-9]+", snake.casefold()) if part]


def _classified(parts: list[str]) -> tuple[str | None, str | None, str | None]:
    sport = None
    name = None
    metric = None
    for part in parts:
        if part in {"target", "targets", "threshold", "thresholds"}:
            continue
        if part in _SPORT_TOKENS and sport is None:
            sport = _SPORT_TOKENS[part]
        elif part in _NAME_TOKENS and name is None:
            name = _NAME_TOKENS[part]
        elif part in _METRIC_TOKENS and metric is None:
            metric = _METRIC_TOKENS[part]
    return sport, name, metric


def _absorb_profile(
    table: dict[str, dict[str, dict[str, Any]]],
    profile: dict[str, Any],
    sport: str | None = None,
    name: str | None = None,
) -> None:
    for key, value in profile.items():
        key_sport, key_name, key_metric = _classified(_tokens(str(key)))
        if isinstance(value, dict):
            _absorb_profile(table, value, key_sport or sport, key_name or name)
            continue
        resolved_sport = key_sport or sport
        resolved_name = key_name or name
        resolved_metric = key_metric
        if resolved_sport and resolved_name and resolved_metric:
            _assign(table, resolved_sport, resolved_name, resolved_metric, value, "profile")


def _mapping_number(entry: dict[str, Any], *names: str) -> int | float | None:
    lowered = {str(key).casefold(): value for key, value in entry.items()}
    for name in names:
        if name in entry:
            number = finite_number(entry.get(name))
            if isinstance(number, (int, float)):
                return number
        number = finite_number(lowered.get(name.casefold()))
        if isinstance(number, (int, float)):
            return number
    return None


def _absorb_wzd(
    table: dict[str, dict[str, dict[str, Any]]],
    workout_zone_detection: dict[str, Any] | None,
    sport: str,
) -> None:
    if not isinstance(workout_zone_detection, dict) or workout_zone_detection.get("available") is False:
        return
    zones = workout_zone_detection.get("thresholds_zone")
    steady = workout_zone_detection.get("steady_state_intensity")
    if isinstance(zones, dict):
        for raw_name, entry in zones.items():
            name = _WZD_NAMES.get(str(raw_name).casefold())
            if name is None or not isinstance(entry, dict):
                continue
            _assign(table, sport, name, "ve", _mapping_number(entry, "VE", "ve"), "pinned_activity")
            _assign(table, sport, name, "hr", _mapping_number(entry, "HR", "hr"), "pinned_activity")
    if isinstance(steady, dict):
        for raw_name, entry in steady.items():
            name = _WZD_NAMES.get(str(raw_name).casefold())
            if name is None or not isinstance(entry, dict):
                continue
            _assign(table, sport, name, "power_w", _mapping_number(entry, "power", "power_w"), "pinned_activity")


def _legacy_ve(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    def _sport(prefix: str) -> dict[str, Any]:
        return {key: profile.get(f"{prefix}_ve_target_{key}") for key in _THRESHOLD_NAMES}

    return {"bike": _sport("bike"), "running": _sport("running")}


def _pinned_sport(profile: dict[str, Any], pinned: dict[str, Any] | None) -> str:
    if isinstance(pinned, dict):
        sport = pinned.get("sport")
        if str(sport) == "1" or str(pinned.get("sport_display", "")).casefold().find("run") >= 0:
            return "running"
        if str(sport) == "2":
            return "bike"
        display = str(pinned.get("sport_display", "")).casefold()
        if "bike" in display or "cycl" in display:
            return "bike"
    bike_values = [profile.get(f"bike_ve_target_{name}") for name in _THRESHOLD_NAMES]
    if any(isinstance(value, (int, float)) and not isinstance(value, bool) and value != 0 for value in bike_values):
        return "bike"
    return "running"


def get_ve_targets(
    profile: dict[str, Any],
    workout_zone_detection: dict[str, Any] | None = None,
    pinned_activity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble dashboard VT1/VT2 VE, HR, and power targets.

    The legacy ``bike`` and ``running`` maps stay VE-only. ``thresholds`` adds
    heart rate and power from profile fields when they exist, then fills gaps
    from the pinned activity's workout-zone detection. VE stays in dashboard
    vol/min, which is the same number as L/min.
    """
    table = _sport_table()
    sport = _pinned_sport(profile, pinned_activity)
    _absorb_wzd(table, workout_zone_detection, sport)
    _absorb_profile(table, profile)
    legacy = _legacy_ve(profile)
    for prefix in _SPORTS:
        for name in _THRESHOLD_NAMES:
            ve = legacy[prefix][name]
            if isinstance(ve, (int, float)) and not isinstance(ve, bool):
                table[prefix][name]["ve"] = ve
                table[prefix][name]["sources"]["ve"] = "profile"

    populated = [
        entry
        for by_sport in table.values()
        for entry in by_sport.values()
        if entry["ve"] is not None or entry["hr"] is not None or entry["power_w"] is not None
    ]
    has_hr = any(entry["hr"] is not None for entry in populated)
    has_power = any(entry["power_w"] is not None for entry in populated)
    if populated and has_hr and has_power:
        state, reason = "available", "thresholds_include_power_ve_hr"
        detail = None
    elif populated:
        state, reason = "partial", "profile_ve_only" if not has_hr and not has_power else "thresholds_partial"
        detail = (
            "VE targets are present. HR or power was missing from the profile fields "
            "and from the pinned activity workout-zone detection."
        )
    else:
        state, reason = "unavailable", "thresholds_not_in_profile"
        detail = "The profile payload did not include VT1/VT2 VE, HR, or power."

    pinned_id = None
    if isinstance(pinned_activity, dict):
        for key in ("id", "activity_id"):
            value = pinned_activity.get(key)
            if isinstance(value, str) and value:
                pinned_id = value
                break
        nested = pinned_activity.get("activity")
        if pinned_id is None and isinstance(nested, dict):
            for key in ("id", "activity_id"):
                value = nested.get(key)
                if isinstance(value, str) and value:
                    pinned_id = value
                    break

    result: dict[str, Any] = {
        **legacy,
        "units": _UNITS,
        "thresholds": table,
        "availability": {"state": state, "reason": reason, "source": "athlete_thresholds"},
    }
    if detail is not None:
        result["detail"] = detail
    if pinned_id is not None:
        result["pinned_activity"] = {"activity_id": pinned_id, "sport": sport}
    return result


def _activity_id(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("id", "activity_id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    nested = payload.get("activity")
    if isinstance(nested, dict):
        return _activity_id(nested)
    return None


async def get_athlete_thresholds(client: TymeClient) -> dict[str, Any]:
    """Profile VE targets plus pinned-activity HR and power when the API provides them."""
    from tymewear_mcp.tools.profile import get_profile

    profile = await get_profile(client)
    pinned: dict[str, Any] | None = None
    wzd: dict[str, Any] | None = None
    user_id = profile.get("id") if isinstance(profile, dict) else None
    if isinstance(user_id, int) and not isinstance(user_id, bool):
        try:
            loaded = await get_pinned_activity(client, user_id)
        except httpx.HTTPError:
            loaded = None
        if isinstance(loaded, dict):
            pinned = loaded
    pinned_id = _activity_id(pinned)
    if pinned_id is not None:
        try:
            loaded_wzd = await get_activity_workout_zone_detection(client, pinned_id)
        except httpx.HTTPError:
            loaded_wzd = None
        if isinstance(loaded_wzd, dict):
            wzd = loaded_wzd
    safe_profile = profile if isinstance(profile, dict) else {}
    return get_ve_targets(safe_profile, wzd, pinned)


async def tag_threshold(client: TymeClient, threshold_type: str, activity_id: str) -> dict[str, Any]:
    endpoint = _THRESHOLD_ENDPOINTS[threshold_type]
    data = await client.post(endpoint, json={"activity_id": activity_id})
    return cast(dict[str, Any], client.sanitize(data))


async def tag_new_zone(client: TymeClient, zone_type: str, activity_id: str) -> dict[str, Any]:
    endpoint = _NEW_ZONE_ENDPOINTS[zone_type]
    data = await client.post(endpoint, json={"activity_id": activity_id})
    return cast(dict[str, Any], client.sanitize(data))
