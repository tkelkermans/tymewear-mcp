"""Coach-facing ventilation streams and interval stats.

Values are labeled in the units the Tymewear dashboard draws: minute volume in
vol/min (the same number as L/min), breathing rate in brpm, and tidal volume in
vol/breath. A processed-data series stored in litres is scaled by 100 so the
coach sees the dashboard tidal-volume number.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.tools.activity_analysis import _canonical_channel, tw_get_activity_analysis

_STREAM_CHANNELS = (
    "ventilation",
    "breathing_rate",
    "tidal_volume",
    "heart_rate",
    "power",
    "cadence",
)
_DISPLAY: dict[str, dict[str, Any]] = {
    "ventilation": {
        "unit": "vol/min",
        "dashboard_label": "Minute Volume",
        "canonical_scale": {"L/min": 1.0},
        "note": (
            "Dashboard Minute Volume in vol/min. The number matches L/min one-for-one "
            "(a value of 80.7 vol/min is 80.7 L/min)."
        ),
    },
    "breathing_rate": {
        "unit": "brpm",
        "dashboard_label": "Breathing rate",
        "canonical_scale": {"breaths/min": 1.0},
        "note": "Dashboard breathing rate in brpm (breaths per minute).",
    },
    "tidal_volume": {
        "unit": "vol/breath",
        "dashboard_label": "Tidal volume",
        "canonical_scale": {"vol/breath": 1.0, "L": 100.0},
        "note": (
            "Dashboard tidal volume in vol/breath. VE (vol/min) ≈ BR (brpm) × TV (vol/breath) / 100, "
            "so 100 vol is about 1 L. A 5x3 min rep near 298 W with TV 258–307 vol/breath is about "
            "2.6–3.1 L per breath. Tymewear does not publish a universal litre calibration."
        ),
    },
    "heart_rate": {
        "unit": "bpm",
        "dashboard_label": "Heart rate",
        "canonical_scale": {"bpm": 1.0},
        "note": "Heart rate in beats per minute.",
    },
    "power": {
        "unit": "W",
        "dashboard_label": "Power",
        "canonical_scale": {"W": 1.0},
        "note": "Cycling power in watts.",
    },
    "cadence": {
        "unit": "rpm",
        "dashboard_label": "Cadence",
        "canonical_scale": {"rpm": 1.0},
        "note": "Cadence in revolutions per minute.",
    },
}
_STATS_CHANNELS = ("ventilation", "breathing_rate", "tidal_volume", "heart_rate", "power")


def canonicalize_stream_channels(channels: list[str] | None) -> list[str] | None:
    """Map coach aliases onto the stream channels, preserving order."""
    if channels is None:
        return None
    selected: list[str] = []
    for channel in channels:
        canonical = _canonical_channel(channel)
        if canonical not in _DISPLAY:
            raise ValueError(
                "channels must be ventilation, breathing_rate, tidal_volume, heart_rate, power, or cadence"
            )
        if canonical not in selected:
            selected.append(canonical)
    return selected


def _round_display(channel: str, value: float) -> float:
    if channel == "power":
        return round(value, 1)
    return round(value, 1)


def _display_series(
    channel: str,
    canonical_unit: str | None,
    points: list[tuple[int, float]],
) -> tuple[list[tuple[int, float]], str | None]:
    spec = _DISPLAY[channel]
    scales: dict[str, float] = spec["canonical_scale"]
    if canonical_unit not in scales:
        return [], None
    scale = scales[canonical_unit]
    converted = [(second, value * scale) for second, value in points]
    conversion = "litres_times_100" if channel == "tidal_volume" and canonical_unit == "L" else None
    return converted, conversion


def _channel_points(samples: list[dict[str, Any]], channel: str) -> list[tuple[int, float]]:
    points: list[tuple[int, float]] = []
    for sample in samples:
        second = sample.get("elapsed_seconds")
        value = sample.get(channel)
        if isinstance(second, int) and isinstance(value, (int, float)) and not isinstance(value, bool):
            points.append((second, float(value)))
    points.sort()
    return points


def _window(
    points: list[tuple[int, float]],
    start_seconds: int,
    end_seconds: int | None,
) -> list[tuple[int, float]]:
    return [
        (second, value)
        for second, value in points
        if second >= start_seconds and (end_seconds is None or second <= end_seconds)
    ]


def _summary(channel: str, points: list[tuple[int, float]]) -> dict[str, Any]:
    unit = _DISPLAY[channel]["unit"]
    if not points:
        return {"unit": unit, "sample_count": 0, "min": None, "avg": None, "max": None}
    values = [value for _, value in points]
    return {
        "unit": unit,
        "sample_count": len(values),
        "min": _round_display(channel, min(values)),
        "avg": _round_display(channel, sum(values) / len(values)),
        "max": _round_display(channel, max(values)),
    }


def _smooth(points: list[tuple[int, float]], smoothing_seconds: int) -> list[tuple[int, float]]:
    if smoothing_seconds <= 1 or len(points) < 2:
        return points
    half = smoothing_seconds // 2
    smoothed: list[tuple[int, float]] = []
    for index, (second, _) in enumerate(points):
        window = [
            value
            for other_second, value in points
            if abs(other_second - second) <= half
        ]
        if window:
            smoothed.append((second, sum(window) / len(window)))
        else:
            smoothed.append((second, points[index][1]))
    return smoothed


def _downsample(points: list[tuple[int, float]], period: int, origin: int) -> list[tuple[int, float]]:
    if period <= 1:
        return points
    buckets: dict[int, list[float]] = defaultdict(list)
    for second, value in points:
        key = origin + ((second - origin) // period) * period
        buckets[key].append(value)
    return [(second, sum(values) / len(values)) for second, values in sorted(buckets.items())]


def _identity(series: dict[str, list[tuple[int, float]]]) -> dict[str, Any] | None:
    ventilation = dict(series.get("ventilation", []))
    breathing = dict(series.get("breathing_rate", []))
    tidal = dict(series.get("tidal_volume", []))
    shared = sorted(set(ventilation) & set(breathing) & set(tidal))
    if len(shared) < 5:
        return None
    errors = [abs(ventilation[second] - breathing[second] * tidal[second] / 100.0) for second in shared]
    errors.sort()
    median = errors[len(errors) // 2]
    return {
        "formula": "ventilation ≈ breathing_rate × tidal_volume / 100",
        "units": "vol/min ≈ brpm × vol/breath / 100",
        "sample_count": len(shared),
        "median_abs_error_vol_per_min": round(median, 2),
        "note": (
            "A small error is normal because the dashboard smooths the three traces independently. "
            "A large error means the tidal-volume scale still does not match minute volume."
        ),
    }


def _channel_report(metadata: dict[str, Any] | None, channel: str) -> dict[str, Any]:
    availability = metadata.get("availability") if isinstance(metadata, dict) else None
    if not isinstance(availability, dict):
        availability = {
            "state": "unavailable",
            "reason": "channel_not_available",
            "source": "activity_analysis",
        }
    report: dict[str, Any] = {
        "unit": _DISPLAY[channel]["unit"],
        "dashboard_label": _DISPLAY[channel]["dashboard_label"],
        "availability": {
            "state": availability.get("state"),
            "reason": availability.get("reason"),
            "source": availability.get("source"),
        },
    }
    detail = metadata.get("detail") if isinstance(metadata, dict) else None
    if isinstance(detail, str):
        report["detail"] = detail
    canonical = metadata.get("canonical_unit") if isinstance(metadata, dict) else None
    if isinstance(canonical, str):
        report["source_canonical_unit"] = canonical
    return report


def _project_stream(
    analysis: dict[str, Any],
    *,
    start_seconds: int,
    end_seconds: int | None,
    sample_period_seconds: int,
    smoothing_seconds: int,
    offset: int,
    limit: int,
    channels: list[str],
) -> dict[str, Any]:
    raw = analysis.get("raw_samples")
    samples = raw.get("data") if isinstance(raw, dict) else None
    rows = [row for row in samples if isinstance(row, dict)] if isinstance(samples, list) else []
    channel_meta = analysis.get("channels") if isinstance(analysis.get("channels"), dict) else {}
    display_series: dict[str, list[tuple[int, float]]] = {}
    conversions: dict[str, str] = {}
    reports: dict[str, Any] = {}
    for channel in channels:
        metadata = channel_meta.get(channel) if isinstance(channel_meta, dict) else None
        reports[channel] = _channel_report(metadata if isinstance(metadata, dict) else None, channel)
        canonical = metadata.get("canonical_unit") if isinstance(metadata, dict) else None
        canonical_unit = canonical if isinstance(canonical, str) else None
        converted, conversion = _display_series(channel, canonical_unit, _channel_points(rows, channel))
        windowed = _window(converted, start_seconds, end_seconds)
        display_series[channel] = windowed
        if conversion is not None and windowed:
            conversions[channel] = conversion
            reports[channel]["conversion"] = conversion

    summaries = {channel: _summary(channel, display_series[channel]) for channel in channels}
    plotted: dict[str, list[tuple[int, float]]] = {}
    for channel, points in display_series.items():
        plotted[channel] = _downsample(_smooth(points, smoothing_seconds), sample_period_seconds, start_seconds)
    timeline = sorted({second for points in plotted.values() for second, _ in points})
    page = timeline[offset : offset + limit]
    page_lookup = {channel: dict(plotted[channel]) for channel in channels}
    page_rows = []
    for second in page:
        row: dict[str, Any] = {"elapsed_seconds": second}
        for channel in channels:
            value = page_lookup[channel].get(second)
            if value is not None:
                row[channel] = _round_display(channel, value)
        page_rows.append(row)
    next_offset = offset + len(page_rows) if offset + len(page_rows) < len(timeline) else None
    usable = [
        channel
        for channel in channels
        if summaries[channel]["sample_count"] and reports[channel]["availability"]["state"] != "unavailable"
    ]
    missing = [channel for channel in channels if channel not in usable]
    if usable and not missing:
        state, reason = "available", "stream_available"
    elif usable:
        state, reason = "partial", "partial_stream_available"
    else:
        state, reason = "unavailable", "stream_channels_missing"
    result: dict[str, Any] = {
        "availability": {"state": state, "reason": reason, "source": "activity_stream"},
        "activity_id": analysis.get("activity_id"),
        "units": {
            channel: {
                "unit": _DISPLAY[channel]["unit"],
                "dashboard_label": _DISPLAY[channel]["dashboard_label"],
                "note": _DISPLAY[channel]["note"],
            }
            for channel in channels
        },
        "window": {"start_seconds": start_seconds, "end_seconds": end_seconds},
        "smoothing_seconds": smoothing_seconds,
        "sample_period_seconds": sample_period_seconds,
        "aggregation": "bucket_mean" if sample_period_seconds > 1 else "sample",
        "summary_scope": "window_before_smoothing",
        "summary": summaries,
        "channels": reports,
        "samples": page_rows,
        "total_samples": len(timeline),
        "offset": offset,
        "limit": limit,
        "has_more": next_offset is not None,
        "next_offset": next_offset,
    }
    if conversions:
        result["conversions"] = conversions
    identity = _identity(display_series)
    if identity is not None:
        result["ventilation_identity"] = identity
    if not usable:
        result["detail"] = (
            "No usable VE, breathing-rate, tidal-volume, heart-rate, power, or cadence samples "
            "were available for this activity."
        )
    return result


def _interval_stats(
    series: dict[str, list[tuple[int, float]]],
    start_seconds: int,
    end_seconds: int,
) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    for channel in _STATS_CHANNELS:
        points = [
            (second, value)
            for second, value in series.get(channel, [])
            if start_seconds <= second <= end_seconds
        ]
        if not points:
            stats[channel] = {
                "unit": _DISPLAY[channel]["unit"],
                "sample_count": 0,
                "avg": None,
                "min": None,
                "max": None,
                "end": None,
            }
            continue
        values = [value for _, value in points]
        stats[channel] = {
            "unit": _DISPLAY[channel]["unit"],
            "sample_count": len(values),
            "avg": _round_display(channel, sum(values) / len(values)),
            "min": _round_display(channel, min(values)),
            "max": _round_display(channel, max(values)),
            "end": _round_display(channel, points[-1][1]),
        }
    return stats


def _power_segments(
    power: list[tuple[int, float]],
    *,
    work_power_w: float,
    min_segment_seconds: int,
) -> list[dict[str, Any]]:
    if not power:
        return []
    flagged = [(second, value >= work_power_w) for second, value in power]
    groups: list[tuple[bool, int, int]] = []
    current_flag = flagged[0][1]
    start = flagged[0][0]
    previous = flagged[0][0]
    for second, is_work in flagged[1:]:
        if is_work == current_flag and second <= previous + 1:
            previous = second
            continue
        groups.append((current_flag, start, previous))
        current_flag = is_work
        start = second
        previous = second
    groups.append((current_flag, start, previous))
    segments: list[dict[str, Any]] = []
    counts = {"work": 0, "recovery": 0}
    for is_work, group_start, group_end in groups:
        if group_end - group_start + 1 < min_segment_seconds:
            continue
        kind = "work" if is_work else "recovery"
        counts[kind] += 1
        segments.append(
            {
                "label": f"{kind}_{counts[kind]}",
                "source": "power_work" if is_work else "power_recovery",
                "start_seconds": group_start,
                "end_seconds": group_end,
            }
        )
    return segments


def _project_intervals(
    analysis: dict[str, Any],
    *,
    intervals: list[dict[str, Any]] | None,
    detect: str,
    work_power_w: int | None,
    min_segment_seconds: int,
) -> dict[str, Any]:
    raw = analysis.get("raw_samples")
    samples = raw.get("data") if isinstance(raw, dict) else None
    rows = [row for row in samples if isinstance(row, dict)] if isinstance(samples, list) else []
    channel_meta = analysis.get("channels") if isinstance(analysis.get("channels"), dict) else {}
    series: dict[str, list[tuple[int, float]]] = {}
    for channel in _STATS_CHANNELS:
        metadata = channel_meta.get(channel) if isinstance(channel_meta, dict) else None
        canonical = metadata.get("canonical_unit") if isinstance(metadata, dict) else None
        canonical_unit = canonical if isinstance(canonical, str) else None
        converted, _ = _display_series(channel, canonical_unit, _channel_points(rows, channel))
        series[channel] = converted

    described: list[dict[str, Any]] = []
    if intervals:
        for index, interval in enumerate(intervals, start=1):
            label = interval.get("label")
            described.append(
                {
                    "label": label if isinstance(label, str) and label else f"interval_{index}",
                    "source": "supplied",
                    "start_seconds": int(interval["start_seconds"]),
                    "end_seconds": int(interval["end_seconds"]),
                }
            )
    if detect == "laps":
        laps = analysis.get("laps")
        if isinstance(laps, list) and laps:
            for index, lap in enumerate(laps, start=1):
                if not isinstance(lap, dict):
                    continue
                described.append(
                    {
                        "label": f"lap_{index}",
                        "source": "fit_lap",
                        "start_seconds": int(lap["start_seconds"]),
                        "end_seconds": int(lap["end_seconds"]),
                    }
                )
        else:
            described.append(
                {
                    "label": "laps",
                    "source": "fit_lap",
                    "start_seconds": None,
                    "end_seconds": None,
                    "detail": "This activity's FIT export has no lap messages.",
                    "stats": None,
                }
            )
    if detect == "power":
        if work_power_w is None:
            raise ValueError("work_power_w is required when detect is power")
        detected = _power_segments(
            series.get("power", []),
            work_power_w=float(work_power_w),
            min_segment_seconds=min_segment_seconds,
        )
        if detected:
            described.extend(detected)
        else:
            described.append(
                {
                    "label": "power",
                    "source": "power_work",
                    "start_seconds": None,
                    "end_seconds": None,
                    "detail": (
                        f"No power segment lasted at least {min_segment_seconds}s "
                        f"at or above {work_power_w} W, and no recovery segment of that length was found."
                    ),
                    "stats": None,
                }
            )

    results: list[dict[str, Any]] = []
    for entry in described:
        if entry.get("stats") is None and entry.get("start_seconds") is None:
            results.append(entry)
            continue
        start = int(entry["start_seconds"])
        end = int(entry["end_seconds"])
        stats = _interval_stats(series, start, end)
        item = {**entry, "stats": stats}
        if all(stats[channel]["sample_count"] == 0 for channel in _STATS_CHANNELS):
            item["detail"] = "No VE, BR, TV, HR, or power samples fall inside this interval."
        results.append(item)

    found = any(
        isinstance(item.get("stats"), dict) and any(stat.get("sample_count") for stat in item["stats"].values())
        for item in results
    )
    if not described:
        state, reason = "unavailable", "intervals_not_requested"
        detail = "Pass intervals or set detect to laps or power."
    elif found:
        state, reason, detail = "available", "intervals_computed", None
    else:
        state, reason = "unavailable", "intervals_not_found"
        detail = "No lap or power segment with samples was found."
    payload: dict[str, Any] = {
        "availability": {"state": state, "reason": reason, "source": "activity_intervals"},
        "activity_id": analysis.get("activity_id"),
        "units": {channel: _DISPLAY[channel]["unit"] for channel in _STATS_CHANNELS},
        "intervals": results,
    }
    if detail is not None:
        payload["detail"] = detail
    return payload


async def tw_get_activity_stream(
    client: TymeClient,
    activity_id: str,
    *,
    start_seconds: int = 0,
    end_seconds: int | None = None,
    sample_period_seconds: int = 1,
    smoothing_seconds: int = 0,
    offset: int = 0,
    limit: int = 500,
    channels: list[str] | None = None,
) -> dict[str, Any]:
    """Return dashboard-labeled VE, BR, TV, HR, power, and cadence samples."""
    if end_seconds is not None and end_seconds < start_seconds:
        raise ValueError("end_seconds must be greater than or equal to start_seconds")
    selected = list(_STREAM_CHANNELS if channels is None else canonicalize_stream_channels(channels) or [])
    analysis = await tw_get_activity_analysis(
        client,
        activity_id,
        channels=selected,
        unpaged=True,
    )
    return _project_stream(
        analysis,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        sample_period_seconds=sample_period_seconds,
        smoothing_seconds=smoothing_seconds,
        offset=offset,
        limit=limit,
        channels=selected,
    )


async def tw_get_activity_intervals(
    client: TymeClient,
    activity_id: str,
    *,
    intervals: list[dict[str, Any]] | None = None,
    detect: str = "none",
    work_power_w: int | None = None,
    min_segment_seconds: int = 30,
) -> dict[str, Any]:
    """Average, min, max, and end VE/BR/TV/HR/power for supplied or detected intervals."""
    if detect == "none" and not intervals:
        raise ValueError("pass intervals or set detect to laps or power")
    if detect == "power" and work_power_w is None:
        raise ValueError("work_power_w is required when detect is power")
    analysis = await tw_get_activity_analysis(
        client,
        activity_id,
        channels=list(_STATS_CHANNELS),
        unpaged=True,
    )
    return _project_intervals(
        analysis,
        intervals=intervals,
        detect=detect,
        work_power_w=work_power_w,
        min_segment_seconds=min_segment_seconds,
    )
