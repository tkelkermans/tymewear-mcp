"""Compact, read-only activity analysis composition."""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import Awaitable, Iterable
from typing import Any, cast

import httpx

from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.tools._availability import AvailabilityState, availability_envelope
from tymewear_mcp.tools.activities import get_activity
from tymewear_mcp.tools.activity_files import get_activity_workout_zone_detection
from tymewear_mcp.tools.breathing_data import get_new_processed_data, get_processed_data
from tymewear_mcp.tools.exports import fetch_fit_bytes
from tymewear_mcp.tools.fit_timeseries import MAX_PAGE_SIZE, decode_fit_timeseries
from tymewear_mcp.tools.profile import get_profile
from tymewear_mcp.tools.threshold_analysis import extract_activity_insights
from tymewear_mcp.tools.timestamps import reconcile_activity_timestamp

MAX_ANALYSIS_PAGE_SIZE = 1000
DURATION_TOLERANCE_SECONDS = 2
_SOURCE_PRIORITY = ("processed_data", "new_processed_data", "fit_export")
_ELAPSED_FIELDS = ("elapsed_seconds", "elapsed_time", "time", "seconds", "second")
_CHANNEL_ALIASES = {
    "ve": "ventilation",
    "ventilation": "ventilation",
    "minute_ventilation": "ventilation",
    "tyme_minute_volume": "ventilation",
    "hr": "heart_rate",
    "heart_rate": "heart_rate",
    "bike_power": "power",
    "power": "power",
    "br": "breathing_rate",
    "breathing_rate": "breathing_rate",
    "respiratory_rate": "breathing_rate",
    "tyme_breath_rate": "breathing_rate",
    "tv": "tidal_volume",
    "tidal_volume": "tidal_volume",
    "tyme_tidal_volume": "tidal_volume",
}
_CANONICAL_UNITS: dict[str, str | None] = {
    "ventilation": "L/min",
    "heart_rate": "bpm",
    "power": "W",
    "cadence": "rpm",
    "breathing_rate": "breaths/min",
    "tidal_volume": "L",
    "speed": "m/s",
    "distance": "m",
    "altitude": "m",
    "temperature": "C",
    "position_lat": "semicircles",
    "position_long": "semicircles",
}
_SENSITIVE_FIELD_PARTS = frozenset(
    {
        "account",
        "bytes",
        "callback",
        "credential",
        "device",
        "email",
        "file",
        "home",
        "identifier",
        "password",
        "path",
        "s3",
        "secret",
        "serial",
        "token",
        "uri",
        "url",
        "user",
        "uuid",
    }
)
_LOCATION_FIELDS = frozenset(
    {
        "position_lat",
        "position_long",
        "latitude",
        "longitude",
        "gps_latitude",
        "gps_longitude",
    }
)


def _validate_inputs(offset: int, limit: int, channels: list[str] | None) -> None:
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_ANALYSIS_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_ANALYSIS_PAGE_SIZE}")
    if channels is not None and any(not isinstance(channel, str) or not channel.strip() for channel in channels):
        raise ValueError("channels must contain non-empty names")


def _normalized_identifier(value: str) -> str:
    snake_case = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return re.sub(r"[^a-z0-9]+", "_", snake_case.casefold()).strip("_")


def _canonical_channel(value: str) -> str:
    normalized = _normalized_identifier(value)
    return _CHANNEL_ALIASES.get(normalized, normalized)


def _is_safe_channel(field: str, *, include_location: bool) -> bool:
    normalized = _normalized_identifier(field)
    if normalized in _ELAPSED_FIELDS or normalized == "timestamp":
        return False
    parts = frozenset(part for part in normalized.split("_") if part)
    if parts & _SENSITIVE_FIELD_PARTS:
        return False
    if normalized in _LOCATION_FIELDS:
        return include_location
    return not any(part in {"lat", "lon", "long", "latitude", "longitude"} for part in parts)


def _safe_numeric(value: Any) -> int | float | bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return value
    return None


def _elapsed_second(record: dict[str, Any]) -> int | None:
    for field in _ELAPSED_FIELDS:
        value = record.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            continue
        return int(round(float(value)))
    return None


def _duration_seconds(activity: dict[str, Any]) -> float | None:
    value = activity.get("duration_seconds")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return max(0.0, float(value))
    duration = activity.get("duration")
    if not isinstance(duration, str):
        return None
    try:
        parts = [int(part) for part in duration.split(":")]
    except ValueError:
        return None
    if not 2 <= len(parts) <= 3 or any(part < 0 for part in parts):
        return None
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    return float(seconds)


def _capability(
    result: Any,
    *,
    source: str,
    failure_reason: str,
) -> dict[str, Any]:
    def tag(
        state: AvailabilityState,
        reason: str,
        *,
        http_status: int | None = None,
    ) -> dict[str, Any]:
        envelope = availability_envelope(
            state=state,
            reason=reason,
            source=source,
            http_status=http_status,
        )
        return cast(dict[str, Any], envelope["availability"])

    if isinstance(result, BaseException):
        status_code = result.response.status_code if isinstance(result, httpx.HTTPStatusError) else None
        failure_state: AvailabilityState = "permission_denied" if status_code == 403 else "unavailable"
        return tag(failure_state, failure_reason, http_status=status_code)
    if not isinstance(result, dict):
        return tag("unavailable", "malformed_upstream_payload")
    reported = result.get("availability")
    if isinstance(reported, dict):
        reported_state = reported.get("state")
        reason = reported.get("reason")
        http_status = reported.get("http_status")
        if reported_state in {
            "available",
            "partial",
            "not_applicable",
            "not_computed",
            "sync_pending",
            "unavailable",
            "permission_denied",
        } and isinstance(reason, str):
            return tag(
                cast(AvailabilityState, reported_state),
                reason,
                http_status=http_status if isinstance(http_status, int) else None,
            )
    if result.get("available") is False:
        status_code = result.get("status_code")
        unavailable_state: AvailabilityState = "permission_denied" if status_code == 403 else "unavailable"
        reason = result.get("reason")
        return tag(
            unavailable_state,
            reason if isinstance(reason, str) else failure_reason,
            http_status=status_code if isinstance(status_code, int) else None,
        )
    return tag("available", "data_available")


def _usable_dict(result: Any) -> dict[str, Any]:
    if isinstance(result, BaseException) or not isinstance(result, dict) or result.get("available") is False:
        return {}
    return result


async def _decode_complete_fit(client: TymeClient, activity_id: str, *, include_location: bool) -> dict[str, Any]:
    fit_bytes = await fetch_fit_bytes(client, activity_id)
    first = decode_fit_timeseries(
        fit_bytes,
        offset=0,
        limit=MAX_PAGE_SIZE,
        include_location=include_location,
    )
    data = list(first.get("data", [])) if isinstance(first.get("data"), list) else []
    next_offset = first.get("next_offset")
    while isinstance(next_offset, int):
        page = decode_fit_timeseries(
            fit_bytes,
            offset=next_offset,
            limit=MAX_PAGE_SIZE,
            include_location=include_location,
        )
        page_data = page.get("data")
        if isinstance(page_data, list):
            data.extend(page_data)
        next_offset = page.get("next_offset")
    return {**first, "data": data, "returned_records": len(data), "next_offset": None, "has_more": False}


def _source_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    data = result.get("data")
    if not isinstance(data, list):
        return []
    return [cast(dict[str, Any], record) for record in data if isinstance(record, dict)]


def _source_channel_metadata(result: dict[str, Any], raw_field: str, canonical: str) -> dict[str, Any]:
    inventory = result.get("channels")
    metadata = inventory.get(raw_field) if isinstance(inventory, dict) else None
    metadata = metadata if isinstance(metadata, dict) else {}
    canonical_default = _CANONICAL_UNITS.get(canonical)
    source_unit = metadata.get("source_unit", canonical_default)
    canonical_unit = metadata.get("canonical_unit", canonical_default)
    scale = metadata.get("scale", 1 if canonical_unit is not None else None)
    return {
        "source_unit": source_unit if isinstance(source_unit, str) else None,
        "canonical_unit": canonical_unit if isinstance(canonical_unit, str) else None,
        "scale": scale if isinstance(scale, (int, float)) and not isinstance(scale, bool) else None,
    }


def _index_source(
    result: dict[str, Any],
    *,
    source: str,
    duration_seconds: float | None,
    include_location: bool,
) -> tuple[dict[str, dict[int, dict[str, Any]]], set[int], int, int]:
    indexed: dict[str, dict[int, dict[str, Any]]] = {}
    observed_seconds: set[int] = set()
    negative_count = 0
    after_duration_count = 0
    for record in _source_records(result):
        second = _elapsed_second(record)
        if second is None:
            continue
        if second < 0:
            negative_count += 1
            continue
        if duration_seconds is not None and second > duration_seconds + DURATION_TOLERANCE_SECONDS:
            after_duration_count += 1
            continue
        accepted_record = False
        for raw_field in sorted(record):
            if not _is_safe_channel(raw_field, include_location=include_location):
                continue
            value = _safe_numeric(record.get(raw_field))
            if value is None:
                continue
            canonical = _canonical_channel(raw_field)
            by_second = indexed.setdefault(canonical, {})
            if second in by_second:
                continue
            by_second[second] = {
                "value": value,
                "raw_field": raw_field,
                "source": source,
                **_source_channel_metadata(result, raw_field, canonical),
            }
            accepted_record = True
        if accepted_record:
            observed_seconds.add(second)
    return indexed, observed_seconds, negative_count, after_duration_count


def _single_value(values: Iterable[Any]) -> Any:
    unique: list[Any] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique[0] if len(unique) == 1 else None


def _channel_metadata(
    channel: str,
    selected: dict[int, dict[str, Any]],
    *,
    expected_count: int,
    requested: bool,
) -> dict[str, Any]:
    source_counts: dict[str, int] = {}
    fields: dict[str, set[str]] = {}
    for candidate in selected.values():
        source = cast(str, candidate["source"])
        source_counts[source] = source_counts.get(source, 0) + 1
        fields.setdefault(source, set()).add(cast(str, candidate["raw_field"]))
    sample_count = len(selected)
    coverage_pct = round(sample_count / expected_count * 100, 2) if expected_count else 0.0
    sources = [source for source in _SOURCE_PRIORITY if source_counts.get(source)]
    selected_source = sources[0] if len(sources) == 1 else "mixed" if sources else None
    if not sources:
        state: AvailabilityState = "unavailable"
        reason = "requested_channel_not_available" if requested else "channel_not_available"
    elif expected_count and sample_count < expected_count:
        state = "partial"
        reason = "channel_samples_have_gaps"
    else:
        state = "available"
        reason = "channel_data_available"
    return {
        "source": selected_source,
        "source_unit": _single_value(candidate.get("source_unit") for candidate in selected.values()),
        "canonical_unit": (
            _single_value(candidate.get("canonical_unit") for candidate in selected.values())
            if selected
            else _CANONICAL_UNITS.get(channel)
        ),
        "scale": _single_value(candidate.get("scale") for candidate in selected.values()),
        "sample_count": sample_count,
        "expected_count": expected_count,
        "coverage_pct": coverage_pct,
        "provenance": {
            "selection": "per_channel_per_elapsed_second",
            "source_priority": list(_SOURCE_PRIORITY),
            "selected_sample_counts": {
                source: source_counts[source] for source in _SOURCE_PRIORITY if source in source_counts
            },
            "fields": {source: sorted(fields[source]) for source in _SOURCE_PRIORITY if source in fields},
        },
        "availability": {
            "state": state,
            "reason": reason,
            "source": selected_source if selected_source not in {None, "mixed"} else "activity_analysis",
        },
    }


def _merge_sources(
    sources: dict[str, dict[str, Any]],
    *,
    duration_seconds: float | None,
    requested_channels: list[str] | None,
    include_location: bool,
    offset: int,
    limit: int,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    indexes: dict[str, dict[str, dict[int, dict[str, Any]]]] = {}
    observed_seconds: set[int] = set()
    negative_count = 0
    after_duration_count = 0
    for source in _SOURCE_PRIORITY:
        index, observed, negative, after_duration = _index_source(
            sources[source],
            source=source,
            duration_seconds=duration_seconds,
            include_location=include_location,
        )
        indexes[source] = index
        observed_seconds.update(observed)
        negative_count += negative
        after_duration_count += after_duration

    available_channels = {channel for index in indexes.values() for channel in index}
    if requested_channels is None:
        selected_channels = sorted(available_channels)
        requested = False
    else:
        selected_channels = list(dict.fromkeys(_canonical_channel(channel) for channel in requested_channels))
        requested = True

    timeline = sorted(observed_seconds)
    selected_values: dict[str, dict[int, dict[str, Any]]] = {}
    for channel in selected_channels:
        by_second: dict[int, dict[str, Any]] = {}
        for second in timeline:
            for source in _SOURCE_PRIORITY:
                candidate = indexes[source].get(channel, {}).get(second)
                if candidate is not None:
                    by_second[second] = candidate
                    break
        selected_values[channel] = by_second

    expected_count = int(round(duration_seconds)) if duration_seconds is not None else len(timeline)
    channel_metadata = {
        channel: _channel_metadata(
            channel,
            selected_values[channel],
            expected_count=expected_count,
            requested=requested,
        )
        for channel in selected_channels
    }
    selected_timeline = (
        [second for second in timeline if any(second in selected_values[channel] for channel in selected_channels)]
        if requested_channels is not None
        else timeline
    )
    merged = [
        {
            "elapsed_seconds": second,
            **{
                channel: selected_values[channel][second]["value"]
                for channel in selected_channels
                if second in selected_values[channel]
            },
        }
        for second in selected_timeline
    ]
    page = merged[offset : offset + limit]
    next_offset = offset + len(page) if offset + len(page) < len(merged) else None
    raw_samples = {
        "total_records": len(merged),
        "returned_records": len(page),
        "offset": offset,
        "limit": limit,
        "has_more": next_offset is not None,
        "next_offset": next_offset,
        "timeline": {
            "policy": "sorted_observed_seconds",
            "expected_count": expected_count,
            "observed_count": len(selected_timeline),
            "missing_expected_count": max(0, expected_count - len(selected_timeline)),
            "discarded_negative_count": negative_count,
            "discarded_after_duration_count": after_duration_count,
            "duration_tolerance_seconds": DURATION_TOLERANCE_SECONDS,
        },
        "data": page,
    }
    return raw_samples, channel_metadata


def _zone_durations(zone_summary: Any) -> tuple[dict[str, float], float | None, float | None]:
    if not isinstance(zone_summary, dict):
        return {}, None, None
    duration_row = zone_summary.get("Duration [sec]")
    if not isinstance(duration_row, dict):
        return {}, None, None
    zones: dict[str, float] = {}
    reported_total: float | None = None
    reported_uncategorized: float | None = None
    for key, raw_value in duration_row.items():
        if (
            isinstance(raw_value, bool)
            or not isinstance(raw_value, (int, float))
            or not math.isfinite(float(raw_value))
        ):
            continue
        value = float(raw_value)
        normalized = _normalized_identifier(str(key))
        if normalized == "total":
            reported_total = value
        elif normalized in {"uncategorized", "unclassified", "unknown"}:
            reported_uncategorized = value
        elif normalized.startswith("zone"):
            zones[str(key)] = value
    return zones, reported_total, reported_uncategorized


def _zone_reconciliation(zone_summary: Any, duration_seconds: float | None) -> dict[str, Any]:
    zones, reported_total, reported_uncategorized = _zone_durations(zone_summary)
    trusted_duration = duration_seconds if duration_seconds is not None else reported_total
    if trusted_duration is None or not zones:
        return {
            "availability": {
                "state": "not_computed",
                "reason": "zone_duration_inputs_missing",
                "source": "workout_zone_detection",
            },
            "duration_seconds": trusted_duration,
            "categorized_seconds": None,
            "uncategorized_seconds": None,
            "tolerance_seconds": DURATION_TOLERANCE_SECONDS,
            "comparison": "absolute_delta_lte",
            "within_tolerance": None,
        }
    categorized = round(sum(zones.values()), 2)
    if reported_uncategorized is None:
        uncategorized = round(max(0.0, trusted_duration - categorized), 2)
        method = "duration_minus_categorized"
    else:
        uncategorized = round(reported_uncategorized, 2)
        method = "reported"
    reconciled = round(categorized + uncategorized, 2)
    delta = round(reconciled - trusted_duration, 2)
    within_tolerance = abs(delta) <= DURATION_TOLERANCE_SECONDS
    return {
        "availability": {
            "state": "available" if within_tolerance else "partial",
            "reason": "zone_duration_reconciled" if within_tolerance else "zone_duration_mismatch",
            "source": "workout_zone_detection",
        },
        "duration_seconds": trusted_duration,
        "categorized_seconds": categorized,
        "uncategorized_seconds": uncategorized,
        "uncategorized_method": method,
        "reconciled_seconds": reconciled,
        "delta_seconds": delta,
        "tolerance_seconds": DURATION_TOLERANCE_SECONDS,
        "comparison": "absolute_delta_lte",
        "within_tolerance": within_tolerance,
    }


def _safe_thresholds(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    thresholds: dict[str, dict[str, Any]] = {}
    for name, entry in value.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_. -]{1,32}", name) or not isinstance(entry, dict):
            continue
        safe_entry: dict[str, Any] = {}
        for key in ("ve", "hr", "steady_state_power_w"):
            scalar = _safe_numeric(entry.get(key))
            if scalar is not None:
                safe_entry[key] = scalar
        confidence = entry.get("confidence")
        if isinstance(confidence, str) and re.fullmatch(r"[A-Za-z0-9_. -]{1,32}", confidence):
            safe_entry["confidence"] = confidence
        safe_entry["metrics"] = _safe_metrics(entry.get("metrics"))
        thresholds[name] = safe_entry
    return thresholds


def _safe_metrics(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    metrics: dict[str, dict[str, Any]] = {}
    for name, entry in value.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_. -]{1,32}", name) or not isinstance(entry, dict):
            continue
        scalar = _safe_numeric(entry.get("value"))
        if scalar is None:
            continue
        metric: dict[str, Any] = {"value": scalar}
        canonical_unit = entry.get("canonical_unit")
        if isinstance(canonical_unit, str) and re.fullmatch(r"[A-Za-z0-9%/^. -]{1,24}", canonical_unit):
            metric["canonical_unit"] = canonical_unit
        source_path = entry.get("source_path")
        if isinstance(source_path, str) and re.fullmatch(r"(?:activity|wzd)\.[A-Za-z0-9_.\[\]-]{1,120}", source_path):
            metric["source_path"] = source_path
        method = entry.get("method")
        if isinstance(method, str) and re.fullmatch(r"[a-z0-9_]{1,64}", method):
            metric["method"] = method
        metrics[name] = metric
    return metrics


def _safe_breakpoints(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    breakpoints: dict[str, dict[str, Any]] = {}
    for name, entry in value.items():
        if name not in {"vt1", "vt2", "vo2max", "fatmax"} or not isinstance(entry, dict):
            continue
        breakpoint: dict[str, Any] = {}
        availability = entry.get("availability")
        if isinstance(availability, dict):
            state = availability.get("state")
            reason = availability.get("reason")
            source = availability.get("source")
            if (
                state
                in {
                    "available",
                    "partial",
                    "not_applicable",
                    "not_computed",
                    "sync_pending",
                    "unavailable",
                    "permission_denied",
                }
                and isinstance(reason, str)
                and re.fullmatch(r"[a-z0-9_]{1,64}", reason)
                and isinstance(source, str)
                and re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", source)
            ):
                breakpoint["availability"] = {"state": state, "reason": reason, "source": source}
        time = entry.get("time")
        if isinstance(time, str) and re.fullmatch(r"\d{1,3}:\d{2}(?::\d{2})?", time):
            breakpoint["time"] = time
        for key in ("time_seconds", "displayed_power_w", "instant_power_w"):
            scalar = _safe_numeric(entry.get(key))
            if scalar is not None:
                breakpoint[key] = scalar
        breakpoint["metrics"] = _safe_metrics(entry.get("metrics"))
        breakpoints[name] = breakpoint
    return breakpoints


def _safe_model_quality(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, Any] = {}
    fit_r2 = _safe_numeric(value.get("fit_r2"))
    if fit_r2 is not None:
        result["fit_r2"] = fit_r2
    confidence = value.get("per_threshold_confidence")
    if isinstance(confidence, dict):
        result["per_threshold_confidence"] = {
            str(key): item
            for key, item in confidence.items()
            if isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9_. -]{1,32}", item)
        }
    result["reason_reported"] = bool(value.get("reason"))
    return result


def _safe_numeric_mapping(value: Any) -> dict[str, int | float | bool]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int | float | bool] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_. -]{1,64}", key):
            continue
        scalar = _safe_numeric(item)
        if scalar is not None:
            result[key] = scalar
    return result


def _safe_model_input_bounds(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "values": _safe_numeric_mapping(value.get("values")),
        "source_path": "wzd.min_max_used",
        "method": "model_calibration_input",
        "interpretation": "model_calibration_bounds_not_activity_extrema",
    }


def _safe_identity(activity: dict[str, Any]) -> dict[str, Any]:
    identity: dict[str, Any] = {}
    for key in ("name", "sport", "sport_display", "type", "type_display", "data_type", "duration", "duration_seconds"):
        value = activity.get(key)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            identity[key] = value
    return identity


def _raw_zone_labels_capability(wzd: dict[str, Any]) -> dict[str, str]:
    return {
        "state": "not_computed",
        "reason": "raw_zone_labels_not_reported",
        "source": "workout_zone_detection",
    }


def _insights_capability(detail: dict[str, Any], wzd: dict[str, Any]) -> dict[str, str]:
    if detail and wzd:
        return {"state": "available", "reason": "insights_composed", "source": "activity_analysis"}
    if detail or wzd:
        return {"state": "partial", "reason": "insight_source_missing", "source": "activity_analysis"}
    return {"state": "unavailable", "reason": "insight_sources_unavailable", "source": "activity_analysis"}


async def tw_get_activity_analysis(
    client: TymeClient,
    activity_id: str,
    offset: int = 0,
    limit: int = 500,
    channels: list[str] | None = None,
    include_location: bool = False,
) -> dict[str, Any]:
    """Compose activity detail, WZD summaries and fallback raw channels."""
    _validate_inputs(offset, limit, channels)
    calls: tuple[Awaitable[Any], ...] = (
        get_activity(client, activity_id),
        get_profile(client),
        get_processed_data(client, activity_id, mode="full"),
        get_new_processed_data(client, activity_id),
        get_activity_workout_zone_detection(client, activity_id),
        _decode_complete_fit(client, activity_id, include_location=include_location),
    )
    gathered = await asyncio.gather(*calls, return_exceptions=True)
    detail_result, profile_result, processed_result, new_processed_result, wzd_result, fit_result = gathered
    detail = _usable_dict(detail_result)
    profile = _usable_dict(profile_result)
    processed = _usable_dict(processed_result)
    new_processed = _usable_dict(new_processed_result)
    wzd = _usable_dict(wzd_result)
    fit = _usable_dict(fit_result)
    duration_seconds = _duration_seconds(detail)
    insights = extract_activity_insights(wzd, detail or {"id": activity_id}, profile)
    timestamps = (
        insights.get("timestamps")
        if detail
        else reconcile_activity_timestamp(
            unix_timestamp=None,
            source_timestamp=None,
            tz_name=None,
            tz_offset=None,
        )
    )
    raw_samples, channel_metadata = _merge_sources(
        {
            "processed_data": processed,
            "new_processed_data": new_processed,
            "fit_export": fit,
        },
        duration_seconds=duration_seconds,
        requested_channels=channels,
        include_location=include_location,
        offset=offset,
        limit=limit,
    )
    capabilities = {
        "activity_detail": _capability(
            detail_result,
            source="activity_detail",
            failure_reason="upstream_request_failed",
        ),
        "athlete_profile": _capability(
            profile_result,
            source="athlete_profile",
            failure_reason="upstream_request_failed",
        ),
        "processed_data": _capability(
            processed_result,
            source="processed_data",
            failure_reason="processed_data_request_failed",
        ),
        "new_processed_data": _capability(
            new_processed_result,
            source="new_processed_data",
            failure_reason="new_processed_data_request_failed",
        ),
        "workout_zone_detection": _capability(
            wzd_result,
            source="workout_zone_detection",
            failure_reason="workout_zone_detection_request_failed",
        ),
        "fit_export": _capability(
            fit_result,
            source="fit_export",
            failure_reason="fit_export_failed",
        ),
        "activity_insights": _insights_capability(detail, wzd),
        "raw_zone_labels": _raw_zone_labels_capability(wzd),
    }
    incomplete = any(capability["state"] != "available" for capability in capabilities.values())
    summary = {
        "thresholds": _safe_thresholds(insights.get("thresholds")),
        "ve_targets": _safe_numeric_mapping(insights.get("ve_targets")),
        "model_quality": _safe_model_quality(insights.get("quality")),
        "model_input_bounds": _safe_model_input_bounds(insights.get("model_input_bounds")),
        "raw_channel_completeness": insights.get("raw_channel_completeness"),
        "zones": {
            "reported": _zone_durations(insights.get("zone_summary"))[0],
            "reconciliation": _zone_reconciliation(insights.get("zone_summary"), duration_seconds),
        },
    }
    return {
        **availability_envelope(
            state="partial" if incomplete else "available",
            reason="partial_analysis_available" if incomplete else "analysis_available",
            source="activity_analysis",
        ),
        "activity_id": activity_id,
        "identity": _safe_identity(detail),
        "timestamps": timestamps,
        "summary": summary,
        "breakpoints": _safe_breakpoints(insights.get("breakpoints")),
        "channels": channel_metadata,
        "raw_samples": raw_samples,
        "capabilities": capabilities,
        "merge_policy": {
            "alignment": "rounded_integer_elapsed_second",
            "source_priority": list(_SOURCE_PRIORITY),
            "same_source_collision": "first_non_null_by_record_then_field",
            "pagination": "after_full_observed_union_merge",
        },
    }
