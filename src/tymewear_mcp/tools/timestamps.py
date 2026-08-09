"""Activity timestamp reconciliation."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any


def _parse_epoch(value: Any) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(seconds):
        return None
    try:
        return datetime.fromtimestamp(seconds, timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _parse_offset_minutes(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and ":" in value:
        sign = -1 if value.startswith("-") else 1
        raw = value.lstrip("+-")
        parts = raw.split(":")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            return None
        hours, minutes = (int(part) for part in parts)
        if minutes >= 60:
            return None
        total = sign * (hours * 60 + minutes)
    else:
        try:
            minutes_float = float(value) * 60
        except (TypeError, ValueError):
            return None
        if not math.isfinite(minutes_float) or not minutes_float.is_integer():
            return None
        total = int(minutes_float)
    return total if -1439 <= total <= 1439 else None


def _parse_source(value: Any, offset_minutes: int | None) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    source = value.strip()
    iso_source = f"{source[:-1]}+00:00" if source.endswith(("Z", "z")) else source
    try:
        parsed = datetime.fromisoformat(iso_source)
    except ValueError:
        try:
            parsed = datetime.strptime(source, "%Y %b %d %H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is None and offset_minutes is not None:
        parsed = parsed.replace(tzinfo=timezone(timedelta(minutes=offset_minutes)))
    return parsed if parsed.tzinfo is not None else None


def _utc_rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def reconcile_activity_timestamp(
    *,
    unix_timestamp: Any,
    source_timestamp: Any,
    tz_name: Any,
    tz_offset: Any,
) -> dict[str, Any]:
    """Reconcile activity timestamp inputs into a stable timestamp contract."""
    epoch = _parse_epoch(unix_timestamp)
    offset_minutes = _parse_offset_minutes(tz_offset)
    source = _parse_source(source_timestamp, offset_minutes)

    if offset_minutes is None and source is not None:
        source_offset = source.utcoffset()
        if source_offset is not None:
            offset_minutes = int(source_offset.total_seconds() / 60)

    authoritative = epoch or source
    local_tz = timezone(timedelta(minutes=offset_minutes)) if offset_minutes is not None else None

    consistency: dict[str, Any] = {"state": "unverifiable"}
    if epoch is not None and source is not None:
        delta_seconds = round(source.timestamp() - epoch.timestamp())
        if delta_seconds == 0:
            consistency = {"state": "consistent"}
        else:
            consistency = {"state": "conflict", "delta_seconds": delta_seconds}

    return {
        "utc": _utc_rfc3339(authoritative) if authoritative is not None else None,
        "local": (
            authoritative.astimezone(local_tz).isoformat(timespec="seconds")
            if authoritative is not None and local_tz is not None
            else None
        ),
        "source": source_timestamp if isinstance(source_timestamp, str) else None,
        "tz_name": tz_name if isinstance(tz_name, str) else None,
        "offset_minutes": offset_minutes,
        "consistency": consistency,
    }
