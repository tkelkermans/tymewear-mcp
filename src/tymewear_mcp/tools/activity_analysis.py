"""Compact, read-only activity analysis composition."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Iterable
from typing import Any, cast

import httpx

from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.tools._availability import AvailabilityState, availability_envelope
from tymewear_mcp.tools._safe_values import finite_number, safe_name, safe_text, safe_unit
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
    "enhanced_speed": "speed",
    "enhanced_altitude": "altitude",
    "latitude": "position_lat",
    "gps_latitude": "position_lat",
    "longitude": "position_long",
    "gps_longitude": "position_long",
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
_CAPABILITY_REASONS = frozenset(
    {
        "data_available",
        "feature_not_available",
        "fit_decode_failed",
        "fit_decoded_with_warnings",
        "new_processed_data_not_available",
        "processed_data_not_available",
    }
)
_BREAKPOINT_NAMES = ("vt1", "vt2", "vo2max", "fatmax")
_BREAKPOINT_METRIC_INDEXES = (12, 24)
_OPTIONAL_CAPABILITIES = frozenset({"raw_zone_labels"})
_RAW_COMPLETENESS_FIELDS = {
    "ventilation": "predict_ve_v3",
    "elapsed": "predict_time_v3",
    "heart_rate": "ext_hr",
    "power": "ext_bike_power",
}


def _validate_inputs(
    offset: int,
    limit: int,
    channels: list[str] | None,
    include_location: bool,
) -> list[str] | None:
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_ANALYSIS_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_ANALYSIS_PAGE_SIZE}")
    if type(include_location) is not bool:
        raise ValueError("include_location must be a boolean")
    if channels is None:
        return None
    if not isinstance(channels, list) or not 1 <= len(channels) <= 32:
        raise ValueError("channels must be a non-empty list with at most 32 names")
    normalized: list[str] = []
    for channel in channels:
        if safe_name(channel, max_length=64) is None:
            raise ValueError("channels must contain safe names of at most 64 characters")
        canonical = _canonical_channel(channel)
        if not canonical:
            raise ValueError("channels must normalize to non-empty names")
        if canonical not in normalized:
            normalized.append(canonical)
    return normalized


def _normalized_identifier(value: str) -> str:
    snake_case = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return re.sub(r"[^a-z0-9]+", "_", snake_case.casefold()).strip("_")


def _canonical_channel(value: str) -> str:
    normalized = _normalized_identifier(value)
    return _CHANNEL_ALIASES.get(normalized, normalized)


def _is_safe_channel(field: str, *, include_location: bool) -> bool:
    if safe_name(field, max_length=64) is None:
        return False
    normalized = _normalized_identifier(field)
    if normalized in _ELAPSED_FIELDS or normalized == "timestamp":
        return False
    if (
        normalized in {"zone", "zones", "zone_label", "zone_labels", "raw_zone_labels"}
        or normalized.startswith("zone_")
        or normalized.endswith(("_zone", "_zone_label", "_zone_labels"))
    ):
        return False
    if normalized in _LOCATION_FIELDS:
        return include_location
    parts = frozenset(part for part in normalized.split("_") if part)
    return not any(part in {"lat", "lon", "long", "latitude", "longitude"} for part in parts)


def _safe_numeric(value: Any) -> int | float | bool | None:
    return finite_number(value)


def _elapsed_second(record: dict[str, Any]) -> int | None:
    for field in _ELAPSED_FIELDS:
        value = finite_number(record.get(field))
        if not isinstance(value, (int, float)):
            continue
        return int(round(value))
    return None


def _duration_seconds(activity: dict[str, Any]) -> float | None:
    value = finite_number(activity.get("duration_seconds"))
    if isinstance(value, (int, float)) and value >= 0:
        return float(value)
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
    bounded = finite_number(seconds)
    return float(bounded) if isinstance(bounded, (int, float)) else None


def _capability(
    result: Any,
    *,
    source: str,
    failure_reason: str,
) -> dict[str, Any]:
    capability, _ = _normalize_result(result, source=source, failure_reason=failure_reason)
    return capability


def _capability_tag(
    state: AvailabilityState,
    reason: str,
    *,
    source: str,
    http_status: int | None = None,
) -> dict[str, Any]:
    envelope = availability_envelope(
        state=state,
        reason=reason,
        source=source,
        http_status=http_status,
    )
    return cast(dict[str, Any], envelope["availability"])


def _normalize_result(
    result: Any,
    *,
    source: str,
    failure_reason: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    malformed = _capability_tag("unavailable", "malformed_upstream_payload", source=source)
    if isinstance(result, BaseException):
        status_code = result.response.status_code if isinstance(result, httpx.HTTPStatusError) else None
        failure_state: AvailabilityState = "permission_denied" if status_code == 403 else "unavailable"
        return (
            _capability_tag(failure_state, failure_reason, source=source, http_status=status_code),
            {},
        )
    if not isinstance(result, dict) or not result:
        return malformed, {}

    reported = result.get("availability")
    legacy_present = "available" in result
    legacy_available = result.get("available")
    if legacy_present and not isinstance(legacy_available, bool):
        return malformed, {}

    if "availability" in result:
        if not isinstance(reported, dict):
            return malformed, {}
        reported_state = reported.get("state")
        reason = reported.get("reason")
        http_status = reported.get("http_status")
        if not (
            reported_state
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
            and reason in _CAPABILITY_REASONS
        ):
            return malformed, {}
        state = cast(AvailabilityState, reported_state)
        state_available = state in {"available", "partial"}
        if legacy_present and legacy_available is not state_available:
            return malformed, {}
        capability = _capability_tag(
            state,
            reason,
            source=source,
            http_status=http_status if isinstance(http_status, int) and 100 <= http_status <= 599 else None,
        )
        return capability, result if state_available else {}

    if legacy_available is False:
        status_code = result.get("status_code")
        unavailable_state: AvailabilityState = "permission_denied" if status_code == 403 else "unavailable"
        reason = result.get("reason")
        stable_reason = reason if isinstance(reason, str) and reason in _CAPABILITY_REASONS else failure_reason
        return (
            _capability_tag(
                unavailable_state,
                stable_reason,
                source=source,
                http_status=status_code if isinstance(status_code, int) and 100 <= status_code <= 599 else None,
            ),
            {},
        )
    if legacy_available is True or not legacy_present:
        return _capability_tag("available", "data_available", source=source), result
    return malformed, {}


def _normalize_series_result(
    result: Any,
    *,
    source: str,
    failure_reason: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    capability, payload = _normalize_result(
        result,
        source=source,
        failure_reason=failure_reason,
    )
    if not payload:
        return capability, payload
    records = payload.get("data")
    inventory = payload.get("channels")
    valid = (
        isinstance(records, list)
        and all(isinstance(record, dict) for record in records)
        and isinstance(inventory, dict)
        and all(isinstance(name, str) and isinstance(metadata, dict) for name, metadata in inventory.items())
    )
    if valid:
        return capability, payload
    return _capability_tag("unavailable", "malformed_upstream_payload", source=source), {}


def _usable_dict(result: Any) -> dict[str, Any]:
    _, usable = _normalize_result(
        result,
        source="tymewear_api",
        failure_reason="upstream_request_failed",
    )
    return usable


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
    expected_unit = _CANONICAL_UNITS.get(canonical)
    if not metadata:
        return {
            "source_unit": None,
            "canonical_unit": expected_unit,
            "scale": None,
            "unit_issue": "unit_conflict",
        }

    raw_source_unit = metadata.get("source_unit")
    raw_canonical_unit = metadata.get("canonical_unit")
    raw_scale = metadata.get("scale")
    source_unit = safe_unit(raw_source_unit)
    canonical_unit = safe_unit(raw_canonical_unit)
    scale = finite_number(raw_scale, max_abs=1_000_000)
    unsafe = (
        (raw_source_unit is not None and source_unit is None)
        or (raw_canonical_unit is not None and canonical_unit is None)
        or (raw_scale is not None and not isinstance(scale, (int, float)))
    )
    if unsafe:
        return {
            "source_unit": None,
            "canonical_unit": expected_unit,
            "scale": None,
            "unit_issue": "unsafe_unit_metadata",
        }

    if expected_unit is not None:
        canonical_coordinate = (
            canonical in {"position_lat", "position_long"}
            and raw_field == canonical
            and source_unit is None
            and canonical_unit is None
            and scale == 1
        )
        if canonical_coordinate:
            source_unit = expected_unit
            canonical_unit = expected_unit
        verified = source_unit is not None and canonical_unit == expected_unit and scale == 1
    else:
        verified = False
    return {
        "source_unit": source_unit,
        "canonical_unit": canonical_unit if verified else expected_unit,
        "scale": scale if verified else None,
        "unit_issue": None if verified else "unit_conflict",
    }


def _index_source(
    result: dict[str, Any],
    *,
    source: str,
    duration_seconds: float | None,
    include_location: bool,
) -> tuple[dict[str, dict[int, dict[str, Any]]], set[int], int, int, dict[str, dict[str, Any]]]:
    indexed: dict[str, dict[int, dict[str, Any]]] = {}
    unit_issues: dict[str, dict[str, Any]] = {}
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
        for raw_field in sorted(field for field in record if isinstance(field, str)):
            if not _is_safe_channel(raw_field, include_location=include_location):
                continue
            value = _safe_numeric(record.get(raw_field))
            if value is None:
                continue
            canonical = _canonical_channel(raw_field)
            metadata = _source_channel_metadata(result, raw_field, canonical)
            unit_issue = metadata.pop("unit_issue")
            if isinstance(unit_issue, str):
                issue = unit_issues.setdefault(
                    canonical,
                    {"rejected_sample_count": 0, "reasons": set()},
                )
                issue["rejected_sample_count"] += 1
                issue["reasons"].add(unit_issue)
                continue
            by_second = indexed.setdefault(canonical, {})
            if second in by_second:
                continue
            by_second[second] = {
                "value": value,
                "raw_field": raw_field,
                "source": source,
                **metadata,
            }
            accepted_record = True
        if accepted_record:
            observed_seconds.add(second)
    return indexed, observed_seconds, negative_count, after_duration_count, unit_issues


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
    duration_bounded: bool,
    requested: bool,
    unit_issue: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_counts: dict[str, int] = {}
    fields: dict[str, set[str]] = {}
    for candidate in selected.values():
        source = cast(str, candidate["source"])
        source_counts[source] = source_counts.get(source, 0) + 1
        fields.setdefault(source, set()).add(cast(str, candidate["raw_field"]))
    sample_count = len(selected)
    in_range_sample_count = (
        sum(0 <= second < expected_count for second in selected)
        if duration_bounded
        else sample_count
    )
    coverage_pct = (
        min(100.0, round(in_range_sample_count / expected_count * 100, 2))
        if expected_count
        else 0.0
    )
    accepted_tail_count = (
        sum(second >= expected_count for second in selected)
        if duration_bounded
        else 0
    )
    sources = [source for source in _SOURCE_PRIORITY if source_counts.get(source)]
    selected_source = sources[0] if len(sources) == 1 else "mixed" if sources else None
    issue_reasons = unit_issue.get("reasons", set()) if unit_issue else set()
    state: AvailabilityState
    if issue_reasons:
        state = "partial"
        reason = "unsafe_unit_metadata" if "unsafe_unit_metadata" in issue_reasons else "unit_conflict"
    elif not sources:
        state = "unavailable"
        reason = "requested_channel_not_available" if requested else "channel_not_available"
    elif expected_count and in_range_sample_count < expected_count:
        state = "partial"
        reason = "channel_samples_have_gaps"
    else:
        state = "available"
        reason = "channel_data_available"
    metadata = {
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
    if unit_issue:
        metadata["rejected_unit_sample_count"] = unit_issue.get("rejected_sample_count", 0)
    if accepted_tail_count:
        metadata["accepted_tail_count"] = accepted_tail_count
    return metadata


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
    unit_issues: dict[str, dict[str, Any]] = {}
    observed_seconds: set[int] = set()
    negative_count = 0
    after_duration_count = 0
    for source in _SOURCE_PRIORITY:
        index, observed, negative, after_duration, source_unit_issues = _index_source(
            sources[source],
            source=source,
            duration_seconds=duration_seconds,
            include_location=include_location,
        )
        indexes[source] = index
        observed_seconds.update(observed)
        negative_count += negative
        after_duration_count += after_duration
        for channel, issue in source_unit_issues.items():
            combined = unit_issues.setdefault(channel, {"rejected_sample_count": 0, "reasons": set()})
            combined["rejected_sample_count"] += issue["rejected_sample_count"]
            combined["reasons"].update(issue["reasons"])

    available_channels = {channel for index in indexes.values() for channel in index} | set(unit_issues)
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
    duration_bounded = duration_seconds is not None
    channel_metadata = {
        channel: _channel_metadata(
            channel,
            selected_values[channel],
            expected_count=expected_count,
            duration_bounded=duration_bounded,
            requested=requested,
            unit_issue=unit_issues.get(channel),
        )
        for channel in selected_channels
    }
    selected_timeline = (
        [second for second in timeline if any(second in selected_values[channel] for channel in selected_channels)]
        if requested_channels is not None
        else timeline
    )
    in_range_observed_count = (
        sum(0 <= second < expected_count for second in selected_timeline)
        if duration_bounded
        else len(selected_timeline)
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
            "missing_expected_count": max(0, expected_count - in_range_observed_count),
            "discarded_negative_count": negative_count,
            "discarded_after_duration_count": after_duration_count,
            "duration_tolerance_seconds": DURATION_TOLERANCE_SECONDS,
        },
        "data": page,
    }
    return raw_samples, channel_metadata


def _zone_durations(zone_summary: Any) -> tuple[dict[str, float], float | None, float | None, int]:
    if not isinstance(zone_summary, dict):
        return {}, None, None, 0
    duration_row = zone_summary.get("Duration [sec]")
    if not isinstance(duration_row, dict):
        return {}, None, None, 0
    zones: dict[str, float] = {}
    reported_total: float | None = None
    reported_uncategorized: float | None = None
    invalid_count = 0
    for key, raw_value in duration_row.items():
        safe_key = safe_name(key, max_length=64)
        if safe_key is None:
            continue
        normalized = _normalized_identifier(safe_key)
        recognized = (
            normalized == "total"
            or normalized in {"uncategorized", "unclassified", "unknown"}
            or normalized.startswith("zone")
        )
        if not recognized:
            continue
        numeric = finite_number(raw_value)
        if not isinstance(numeric, (int, float)) or numeric < 0:
            invalid_count += 1
            continue
        value = float(numeric)
        if normalized == "total":
            reported_total = value
        elif normalized in {"uncategorized", "unclassified", "unknown"}:
            reported_uncategorized = value
        else:
            zones[safe_key] = value
    return zones, reported_total, reported_uncategorized, invalid_count


def _invalid_zone_reconciliation(duration_seconds: float | None) -> dict[str, Any]:
    return {
        "availability": {
            "state": "not_computed",
            "reason": "invalid_zone_durations",
            "source": "workout_zone_detection",
        },
        "duration_seconds": duration_seconds,
        "categorized_seconds": None,
        "uncategorized_seconds": None,
        "tolerance_seconds": DURATION_TOLERANCE_SECONDS,
        "comparison": "absolute_delta_lte",
        "within_tolerance": None,
    }


def _zone_reconciliation(zone_summary: Any, duration_seconds: float | None) -> dict[str, Any]:
    zones, reported_total, reported_uncategorized, invalid_count = _zone_durations(zone_summary)
    duration_value = finite_number(duration_seconds)
    trusted_duration = (
        float(duration_value)
        if isinstance(duration_value, (int, float)) and duration_value >= 0
        else reported_total
    )
    if invalid_count and not zones:
        return _invalid_zone_reconciliation(trusted_duration)
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
    categorized_value = finite_number(sum(zones.values()))
    if not isinstance(categorized_value, (int, float)):
        return _invalid_zone_reconciliation(trusted_duration)
    categorized = round(float(categorized_value), 2)
    if reported_uncategorized is None:
        uncategorized = round(max(0.0, trusted_duration - categorized), 2)
        method = "duration_minus_categorized"
    else:
        uncategorized = round(reported_uncategorized, 2)
        method = "reported"
    reconciled_value = finite_number(categorized + uncategorized)
    if not isinstance(reconciled_value, (int, float)):
        return _invalid_zone_reconciliation(trusted_duration)
    reconciled = round(float(reconciled_value), 2)
    delta_value = finite_number(reconciled - trusted_duration)
    if not isinstance(delta_value, (int, float)):
        return _invalid_zone_reconciliation(trusted_duration)
    delta = round(float(delta_value), 2)
    within_tolerance = abs(delta) <= DURATION_TOLERANCE_SECONDS
    availability_state = "partial" if invalid_count else "available" if within_tolerance else "partial"
    availability_reason = (
        "invalid_zone_durations"
        if invalid_count
        else "zone_duration_reconciled"
        if within_tolerance
        else "zone_duration_mismatch"
    )
    return {
        "availability": {
            "state": availability_state,
            "reason": availability_reason,
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
        if safe_name(name, max_length=32) is None or not isinstance(entry, dict):
            continue
        safe_entry: dict[str, Any] = {}
        for key in ("ve", "hr", "steady_state_power_w"):
            scalar = _safe_numeric(entry.get(key))
            if scalar is not None:
                safe_entry[key] = scalar
        confidence = entry.get("confidence")
        safe_confidence = safe_text(confidence, max_length=32)
        if safe_confidence is not None:
            safe_entry["confidence"] = safe_confidence
        safe_entry["metrics"] = _safe_metrics(entry.get("metrics"))
        thresholds[name] = safe_entry
    return thresholds


def _safe_metrics(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    metrics: dict[str, dict[str, Any]] = {}
    for name, entry in value.items():
        if safe_name(name, max_length=32) is None or not isinstance(entry, dict):
            continue
        scalar = _safe_numeric(entry.get("value"))
        if scalar is None:
            continue
        metric: dict[str, Any] = {"value": scalar}
        canonical_unit = safe_unit(entry.get("canonical_unit"))
        if canonical_unit is not None:
            metric["canonical_unit"] = canonical_unit
        source_path = entry.get("source_path")
        if isinstance(source_path, str) and re.fullmatch(r"(?:activity|wzd)\.[A-Za-z0-9_.\[\]-]{1,120}", source_path):
            metric["source_path"] = source_path
        method = safe_name(entry.get("method"), max_length=64, reject_sensitive=False)
        if method is not None:
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
        safe_confidence: dict[str, str] = {}
        for key, item in confidence.items():
            safe_key = safe_name(key, max_length=32)
            safe_value = safe_text(item, max_length=32)
            if safe_key is not None and safe_value is not None:
                safe_confidence[safe_key] = safe_value
        result["per_threshold_confidence"] = safe_confidence
    result["reason_reported"] = bool(value.get("reason"))
    return result


def _safe_numeric_mapping(value: Any) -> dict[str, int | float | bool]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int | float | bool] = {}
    for key, item in value.items():
        if safe_name(key, max_length=64) is None:
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


def _safe_insight_number(value: Any) -> int | float | None:
    numeric = finite_number(value)
    if isinstance(numeric, (int, float)):
        return numeric
    if not isinstance(value, str) or re.fullmatch(r"[+-]?\d{1,12}(?:\.\d{1,6})?", value) is None:
        return None
    try:
        parsed = float(value)
    except (OverflowError, ValueError):
        return None
    bounded = finite_number(parsed)
    return bounded if isinstance(bounded, (int, float)) else None


def _safe_insight_activity(activity: dict[str, Any]) -> dict[str, Any]:
    """Bound the few detail fields coerced by the existing insight extractor."""
    safe_activity = dict(activity)
    for key in ("unix_timestamp", "tz_offset"):
        safe_activity[key] = _safe_insight_number(activity.get(key))
    for key in ("time_stamp", "tz_name"):
        safe_activity[key] = safe_text(activity.get(key), max_length=64)
    for name in _BREAKPOINT_NAMES:
        time_key = f"new_zone_{name}"
        time_value = safe_text(activity.get(time_key), max_length=16)
        safe_activity[time_key] = (
            time_value
            if time_value is not None and re.fullmatch(r"\d{1,3}:\d{2}(?::\d{2})?", time_value)
            else None
        )
        metrics_key = f"{time_key}_metrics"
        metrics = activity.get(metrics_key)
        if isinstance(metrics, list):
            projected: list[int | float | None] = [None] * min(
                len(metrics), max(_BREAKPOINT_METRIC_INDEXES) + 1
            )
            for index in _BREAKPOINT_METRIC_INDEXES:
                if index < len(projected):
                    projected[index] = _safe_insight_number(metrics[index])
            safe_activity[metrics_key] = projected
        else:
            safe_activity[metrics_key] = None
    return safe_activity


def _safe_raw_channel_completeness(activity: dict[str, Any]) -> dict[str, Any]:
    channels: dict[str, dict[str, Any]] = {}
    omitted = activity.get("_omitted_fields")
    for channel, field in _RAW_COMPLETENESS_FIELDS.items():
        value = activity.get(field)
        if isinstance(value, list):
            sample_count = finite_number(len(value))
            state = "observed" if sample_count else "reported_empty"
            method = "array_length"
        else:
            omitted_entry = omitted.get(field) if isinstance(omitted, dict) else None
            raw_length = omitted_entry.get("length") if isinstance(omitted_entry, dict) else None
            sample_count = finite_number(raw_length)
            if not isinstance(sample_count, int) or sample_count < 0:
                sample_count = None
                state = "unknown"
                method = "not_reported"
            else:
                state = "observed" if sample_count else "reported_empty"
                method = "omitted_field_length"
        channels[channel] = {
            "state": state,
            "sample_count": sample_count,
            "source_path": f"activity.{field}",
            "method": method,
        }
    return {"method": "activity_array_inventory", "channels": channels}


def _safe_identity(activity: dict[str, Any]) -> dict[str, Any]:
    identity: dict[str, Any] = {}
    for key in ("name", "sport", "sport_display", "type", "type_display", "data_type", "duration", "duration_seconds"):
        value = activity.get(key)
        numeric = finite_number(value)
        text = safe_text(value)
        if isinstance(numeric, (int, float)):
            identity[key] = numeric
        elif text is not None:
            identity[key] = text
    return identity


def _safe_timestamps(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return reconcile_activity_timestamp(
            unix_timestamp=None,
            source_timestamp=None,
            tz_name=None,
            tz_offset=None,
        )
    result: dict[str, Any] = {}
    for key in ("utc", "local", "source", "tz_name"):
        text = safe_text(value.get(key))
        result[key] = text
    offset = finite_number(value.get("offset_minutes"))
    result["offset_minutes"] = offset if isinstance(offset, (int, float)) else None
    consistency = value.get("consistency")
    safe_consistency: dict[str, Any] = {"state": "unverifiable"}
    if isinstance(consistency, dict) and consistency.get("state") in {"consistent", "conflict", "unverifiable"}:
        safe_consistency = {"state": consistency["state"]}
        delta = finite_number(consistency.get("delta_seconds"))
        if isinstance(delta, (int, float)):
            safe_consistency["delta_seconds"] = delta
    result["consistency"] = safe_consistency
    return result


def _raw_zone_labels_capability(
    wzd: dict[str, Any],
    wzd_capability: dict[str, Any] | None = None,
) -> dict[str, str]:
    if wzd_capability is not None and wzd_capability.get("state") not in {"available", "partial"}:
        return {
            "state": "unavailable",
            "reason": "workout_zone_detection_unavailable",
            "source": "workout_zone_detection",
        }
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
    normalized_channels = _validate_inputs(offset, limit, channels, include_location)
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
    detail_capability, detail = _normalize_result(
        detail_result,
        source="activity_detail",
        failure_reason="upstream_request_failed",
    )
    profile_capability, profile = _normalize_result(
        profile_result,
        source="athlete_profile",
        failure_reason="upstream_request_failed",
    )
    processed_capability, processed = _normalize_series_result(
        processed_result,
        source="processed_data",
        failure_reason="processed_data_request_failed",
    )
    new_processed_capability, new_processed = _normalize_series_result(
        new_processed_result,
        source="new_processed_data",
        failure_reason="new_processed_data_request_failed",
    )
    wzd_capability, wzd = _normalize_result(
        wzd_result,
        source="workout_zone_detection",
        failure_reason="workout_zone_detection_request_failed",
    )
    fit_capability, fit = _normalize_series_result(
        fit_result,
        source="fit_export",
        failure_reason="fit_export_failed",
    )
    duration_seconds = _duration_seconds(detail)
    insight_activity = _safe_insight_activity(detail or {"id": activity_id})
    insights = extract_activity_insights(wzd, insight_activity, profile)
    timestamps_raw = (
        insights.get("timestamps")
        if detail
        else reconcile_activity_timestamp(
            unix_timestamp=None,
            source_timestamp=None,
            tz_name=None,
            tz_offset=None,
        )
    )
    timestamps = _safe_timestamps(timestamps_raw)
    raw_samples, channel_metadata = _merge_sources(
        {
            "processed_data": processed,
            "new_processed_data": new_processed,
            "fit_export": fit,
        },
        duration_seconds=duration_seconds,
        requested_channels=normalized_channels,
        include_location=include_location,
        offset=offset,
        limit=limit,
    )
    capabilities = {
        "activity_detail": detail_capability,
        "athlete_profile": profile_capability,
        "processed_data": processed_capability,
        "new_processed_data": new_processed_capability,
        "workout_zone_detection": wzd_capability,
        "fit_export": fit_capability,
        "activity_insights": _insights_capability(detail, wzd),
        "raw_zone_labels": _raw_zone_labels_capability(wzd, wzd_capability),
    }
    incomplete = any(
        capability["state"] != "available"
        for name, capability in capabilities.items()
        if name not in _OPTIONAL_CAPABILITIES
    )
    summary = {
        "thresholds": _safe_thresholds(insights.get("thresholds")),
        "ve_targets": _safe_numeric_mapping(insights.get("ve_targets")),
        "model_quality": _safe_model_quality(insights.get("quality")),
        "model_input_bounds": _safe_model_input_bounds(insights.get("model_input_bounds")),
        "raw_channel_completeness": _safe_raw_channel_completeness(detail),
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
