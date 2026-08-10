"""In-memory FIT decoding and time-series normalization."""

from __future__ import annotations

import gzip
import re
from collections.abc import Iterable
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, cast

from garmin_fit_sdk import Decoder, Stream

from tymewear_mcp.tools._availability import availability_envelope, feature_available

MAX_COMPRESSED_FIT_BYTES = 16 * 1024 * 1024
MAX_DECOMPRESSED_FIT_BYTES = 64 * 1024 * 1024
MAX_PAGE_SIZE = 1000
_COORDINATE_FIELD = re.compile(r"(?:^|_)(?:position_)?(?:lat|lon|long|latitude|longitude)(?:_|$)")
_STANDARD_UNITS: dict[str, str | None] = {
    "heart_rate": "bpm",
    "power": "W",
    "cadence": "rpm",
    "speed": "m/s",
    "enhanced_speed": "m/s",
    "distance": "m",
    "altitude": "m",
    "enhanced_altitude": "m",
    "temperature": "C",
    "position_lat": "semicircles",
    "position_long": "semicircles",
}
_DEVELOPER_CANONICAL_UNITS: dict[str, str] = {
    "tyme_minute_volume": "L/min",
    "tyme_breath_rate": "breaths/min",
    "tyme_tidal_volume": "L",
}


def _validate_paging(offset: int, limit: int) -> None:
    if isinstance(offset, bool) or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    if isinstance(limit, bool) or limit < 1 or limit > MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")


def _utc_timestamp(value: Any) -> tuple[datetime | None, str | None]:
    if not isinstance(value, datetime):
        return None, None
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    utc = aware.astimezone(timezone.utc)
    return utc, utc.isoformat(timespec="seconds").replace("+00:00", "Z")


def _is_coordinate_field(field_name: str) -> bool:
    snake_case = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", field_name)
    normalized = re.sub(r"[^a-z0-9]+", "_", snake_case.casefold()).strip("_")
    return _COORDINATE_FIELD.search(normalized) is not None


def _developer_descriptions(
    messages: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[Any, tuple[str, str, str | None]]:
    descriptions: dict[Any, tuple[str, str, str | None]] = {}
    native_fields = {field for record in records for field in record if field != "developer_fields"}
    output_fields = set(native_fields)
    raw_descriptions = messages.get("field_description_mesgs", [])
    if not isinstance(raw_descriptions, list):
        return descriptions
    for description in raw_descriptions:
        if not isinstance(description, dict):
            continue
        key = description.get("key")
        field_name = description.get("field_name")
        if key is None or not isinstance(field_name, str) or not field_name:
            continue
        units = description.get("units")
        output_name = field_name
        if output_name in output_fields:
            output_name = f"developer_{field_name}"
        if output_name in output_fields:
            output_name = f"{output_name}_{key}"
        output_fields.add(output_name)
        descriptions[key] = (
            field_name,
            output_name,
            units if isinstance(units, str) and units else None,
        )
    return descriptions


def _record_messages(messages: dict[str, Any]) -> list[dict[str, Any]]:
    records = messages.get("record_mesgs", [])
    if not isinstance(records, list):
        return []
    return [cast(dict[str, Any], record) for record in records if isinstance(record, dict)]


def _field_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return None


def _normalized_records(
    records: list[dict[str, Any]],
    descriptions: dict[Any, tuple[str, str, str | None]],
    *,
    include_location: bool,
) -> list[dict[str, Any]]:
    first_timestamp = next((_utc_timestamp(record.get("timestamp"))[0] for record in records), None)
    normalized: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        timestamp, timestamp_text = _utc_timestamp(record.get("timestamp"))
        elapsed_seconds = (
            round((timestamp - first_timestamp).total_seconds()) if timestamp and first_timestamp else index
        )
        sample: dict[str, Any] = {"elapsed_seconds": elapsed_seconds}
        if timestamp_text is not None:
            sample["timestamp"] = timestamp_text

        for field, value in record.items():
            if field in {"timestamp", "developer_fields"} or (
                _is_coordinate_field(field) and not include_location
            ):
                continue
            normalized_value = _field_value(value)
            if normalized_value is not None:
                sample[field] = normalized_value

        developer_fields = record.get("developer_fields")
        if isinstance(developer_fields, dict):
            for key, value in developer_fields.items():
                description = descriptions.get(key)
                if description is None:
                    continue
                declared_name, output_name, _ = description
                if not include_location and (
                    _is_coordinate_field(declared_name) or _is_coordinate_field(output_name)
                ):
                    continue
                normalized_value = _field_value(value)
                if normalized_value is not None:
                    sample[output_name] = normalized_value
        normalized.append(sample)
    return normalized


def _channel_inventory(
    data: list[dict[str, Any]],
    descriptions: dict[Any, tuple[str, str, str | None]],
) -> dict[str, dict[str, Any]]:
    developer_fields = {output: (declared, units) for declared, output, units in descriptions.values()}
    channels = sorted({field for sample in data for field in sample if field not in {"elapsed_seconds", "timestamp"}})
    inventory: dict[str, dict[str, Any]] = {}
    for channel in channels:
        developer_field = developer_fields.get(channel)
        if developer_field is None:
            source_field = channel
            source_unit = _STANDARD_UNITS.get(channel)
            canonical_unit = source_unit
            scale: int | None = 1
        else:
            source_field, source_unit = developer_field
            expected_unit = _DEVELOPER_CANONICAL_UNITS.get(source_field)
            if (
                expected_unit is not None
                and source_unit is not None
                and source_unit.casefold() == expected_unit.casefold()
            ):
                canonical_unit = expected_unit
                scale = 1
            else:
                canonical_unit = None
                scale = None
        sample_count = sum(sample.get(channel) is not None for sample in data)
        channel_metadata: dict[str, Any] = {
            "source_unit": source_unit,
            "canonical_unit": canonical_unit,
            "scale": scale,
            "sample_count": sample_count,
            "expected_count": len(data),
            "coverage_pct": round(sample_count / len(data) * 100, 2) if data else 0.0,
            "provenance": {"source": "fit_export", "field": source_field},
        }
        if developer_field is not None and canonical_unit is None:
            channel_metadata["conversion"] = {
                "state": "unverified",
                "reason": "source_unit_not_canonical",
            }
        inventory[channel] = channel_metadata
    return inventory


def _safe_warnings(warnings: Iterable[Exception]) -> list[dict[str, str]]:
    return [{"type": type(warning).__name__} for warning in warnings]


def normalize_fit_messages(
    messages: dict[str, Any],
    *,
    decoder_warnings: Iterable[Exception],
    offset: int = 0,
    limit: int = 500,
    include_location: bool = False,
    compression: str = "none",
    valid_fit: bool = True,
) -> dict[str, Any]:
    """Normalize decoded Garmin SDK messages into a paged public-neutral series."""
    _validate_paging(offset, limit)
    warnings = _safe_warnings(decoder_warnings)
    records = _record_messages(messages)
    descriptions = _developer_descriptions(messages, records)
    data = _normalized_records(records, descriptions, include_location=include_location)
    if not valid_fit or (warnings and not data):
        availability = availability_envelope(
            state="unavailable",
            reason="fit_decode_failed",
            source="fit_export",
        )
    elif warnings:
        availability = availability_envelope(
            state="partial",
            reason="fit_decoded_with_warnings",
            source="fit_export",
        )
    else:
        availability = feature_available(source="fit_export")

    page = data[offset : offset + limit]
    next_offset = offset + len(page) if offset + len(page) < len(data) else None
    return {
        **availability,
        "compression": compression,
        "total_records": len(data),
        "returned_records": len(page),
        "offset": offset,
        "limit": limit,
        "has_more": next_offset is not None,
        "next_offset": next_offset,
        "channels": _channel_inventory(data, descriptions),
        "decoder_warnings": warnings,
        "data": page,
    }


def _fit_payload(fit_bytes: bytes) -> tuple[bytes, str]:
    if len(fit_bytes) > MAX_COMPRESSED_FIT_BYTES:
        raise ValueError("FIT payload exceeds the compressed size limit")
    if not fit_bytes.startswith(b"\x1f\x8b"):
        if len(fit_bytes) > MAX_DECOMPRESSED_FIT_BYTES:
            raise ValueError("FIT payload exceeds the decompressed size limit")
        return fit_bytes, "none"
    try:
        with gzip.GzipFile(fileobj=BytesIO(fit_bytes)) as compressed:
            payload = compressed.read(MAX_DECOMPRESSED_FIT_BYTES + 1)
    except (EOFError, OSError) as exc:
        raise ValueError("FIT payload contains invalid gzip data") from exc
    if len(payload) > MAX_DECOMPRESSED_FIT_BYTES:
        raise ValueError("FIT payload exceeds the decompressed size limit")
    return payload, "gzip"


def decode_fit_timeseries(
    fit_bytes: bytes,
    *,
    offset: int = 0,
    limit: int = 500,
    include_location: bool = False,
) -> dict[str, Any]:
    """Decode FIT bytes in memory with the official Garmin SDK."""
    _validate_paging(offset, limit)
    payload, compression = _fit_payload(fit_bytes)
    is_fit = False
    messages: Any = {}
    warnings: list[Exception] = []
    try:
        decoder = Decoder(Stream.from_byte_array(bytearray(payload)))
        is_fit = decoder.is_fit()
        if is_fit:
            messages, warnings = decoder.read()
    except Exception as exc:
        warnings = [exc]
    return normalize_fit_messages(
        cast(dict[str, Any], messages),
        decoder_warnings=warnings,
        offset=offset,
        limit=limit,
        include_location=include_location,
        compression=compression,
        valid_fit=is_fit,
    )
