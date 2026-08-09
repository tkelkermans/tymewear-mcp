"""Total, non-mutating privacy projection for public MCP results."""

from __future__ import annotations

import math
import re
from typing import Any, cast

from tymewear_mcp.tools._safe_values import MAX_SAFE_INTEGER, normalized_parts

_DROP = object()
_MAX_DEPTH = 32
_MAX_KEY_LENGTH = 256
_MAX_STRING_LENGTH = 2048

_PRIVATE_KEY_PARTS = frozenset(
    {
        "bytes",
        "callback",
        "credential",
        "download",
        "email",
        "identifier",
        "password",
        "path",
        "s3",
        "secret",
        "serial",
        "signed",
        "token",
        "uri",
        "url",
    }
)
_IDENTITY_KEY_PARTS = frozenset({"account", "athlete", "device", "profile", "user"})
_IDENTIFIER_KEY_PARTS = frozenset({"id", "identifier", "serial", "uuid"})
_LOCATION_KEY_PARTS = frozenset(
    {
        "coordinate",
        "coordinates",
        "gps",
        "lat",
        "latitude",
        "lng",
        "location",
        "lon",
        "long",
        "longitude",
        "position",
    }
)
_ANALYSIS_LOCATION_CHANNELS = frozenset({"position_lat", "position_long"})
_LOCATION_CHANNEL_METADATA_KEYS = frozenset(
    {
        "accepted_tail_count",
        "availability",
        "canonical_unit",
        "coverage_pct",
        "expected_count",
        "provenance",
        "rejected_unit_sample_count",
        "sample_count",
        "scale",
        "source",
        "source_unit",
    }
)
_HEAVY_EXACT_KEYS = frozenset(
    {
        "assoc_results",
        "logs",
        "onesignal_results",
        "plf_x_results",
        "prob_list_zone",
        "regression_analysis_x",
        "times_zone",
        "transition_points_zone",
        "ve_list_zone",
        "x",
        "zones_predict_plot",
        "zones_predict_v3_plot",
    }
)
_HEAVY_PREFIXES = ("ext_", "predict_")

_EMAIL = re.compile(r"(?i)(?<![\w.+-])[\w.+-]+@[\w.-]+\.[a-z]{2,}(?![\w.-])")
_URI = re.compile(r"(?i)\b(?:[a-z][a-z0-9+.-]{1,31}://|data:|mailto:|urn:)")
_ABSOLUTE_PATH = re.compile(
    r"(?i)(?:^|[\s\"'(<>=:])(?:/[A-Za-z0-9._~-][^\s\"'<>]*|[A-Z]:[\\/][^\s\"'<>]+|\\\\[^\s\"'<>]+)"
)
_BARE_S3_HOST = re.compile(
    r"(?i)(?:^|[^a-z0-9.-])(?:[a-z0-9.-]+\.)?s3(?:[.-][a-z0-9-]+)?\.amazonaws\.com(?:[/:]|$)"
)
_QUERY_SECRET = re.compile(
    r"(?i)(?:access[_-]?token|api[_-]?key|authorization|bearer|credential|password|secret|signature|token)"
    r"\s*(?:=|:|%3d)"
)
_JWT_OR_BEARER = re.compile(r"(?i)^(?:bearer\s+\S+|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)$")
_COMMON_SECRET_PREFIX = re.compile(r"^(?:gh[opusr]_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]+)$")
_AWS_ACCESS_KEY = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
_UUID = re.compile(r"(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _unsafe_text(value: str, *, max_length: int, allow_activity_uuid: bool = False) -> bool:
    if not 1 <= len(value) <= max_length:
        return True
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return True
    if (
        _EMAIL.search(value)
        or _URI.search(value)
        or _ABSOLUTE_PATH.search(value)
        or _BARE_S3_HOST.search(value)
        or _QUERY_SECRET.search(value)
        or _AWS_ACCESS_KEY.search(value)
    ):
        return True
    if _JWT_OR_BEARER.fullmatch(value) or _COMMON_SECRET_PREFIX.fullmatch(value):
        return True
    return bool(_UUID.fullmatch(value) and not allow_activity_uuid)


def _activity_id_alias_allowed(
    path: tuple[str | int, ...],
    key: str,
    preserve_activity_ids: bool,
) -> bool:
    if not preserve_activity_ids or key not in {"activity_uuid", "id"}:
        return False
    if not path:
        return True
    if len(path) == 1 and isinstance(path[0], int):
        return True
    return len(path) == 2 and path[0] == "results" and isinstance(path[1], int)


def _unsafe_key(
    key: str,
    *,
    path: tuple[str | int, ...],
    preserve_activity_ids: bool,
) -> bool:
    if _unsafe_text(key, max_length=_MAX_KEY_LENGTH):
        return True

    parts = normalized_parts(key)
    if parts & _PRIVATE_KEY_PARTS:
        return True
    if key.casefold() in {"id", "uuid"}:
        return not _activity_id_alias_allowed(path, key, preserve_activity_ids)
    return bool(parts & _IDENTITY_KEY_PARTS and parts & _IDENTIFIER_KEY_PARTS)


def _is_location_key(key: str) -> bool:
    parts = normalized_parts(key)
    return bool(parts & _LOCATION_KEY_PARTS) or "home" in parts


def _location_allowed(path: tuple[str | int, ...], key: str, allow_analysis_location: bool) -> bool:
    if not allow_analysis_location or key not in _ANALYSIS_LOCATION_CHANNELS:
        return False
    if path == ("channels",):
        return True
    return len(path) == 3 and path[:2] == ("raw_samples", "data") and isinstance(path[2], int)


def _location_shape_allowed(path: tuple[str | int, ...], value: Any) -> bool:
    if path == ("channels",):
        return type(value) is dict
    return type(value) is int or type(value) is float


def _location_metadata_key_allowed(path: tuple[str | int, ...], key: str) -> bool:
    if len(path) == 2 and path[0] == "channels" and path[1] in _ANALYSIS_LOCATION_CHANNELS:
        return key in _LOCATION_CHANNEL_METADATA_KEYS
    return True


def _is_heavy_key(key: str, *, compact_analysis: bool) -> bool:
    snake_case = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    normalized = re.sub(r"[^a-z0-9]+", "_", snake_case.casefold()).strip("_")
    if normalized == "raw_samples":
        return not compact_analysis
    if normalized.startswith("raw_"):
        return not compact_analysis or normalized not in {
            "raw_channel_completeness",
            "raw_samples",
            "raw_zone_labels",
        }
    return normalized in _HEAVY_EXACT_KEYS or normalized.startswith(_HEAVY_PREFIXES)


def _unsafe_string(
    value: str,
    *,
    path: tuple[str | int, ...],
    preserve_activity_ids: bool,
) -> bool:
    allow_activity_uuid = bool(path and path[-1] == "activity_id")
    if path and isinstance(path[-1], str):
        allow_activity_uuid = allow_activity_uuid or _activity_id_alias_allowed(
            path[:-1],
            path[-1],
            preserve_activity_ids,
        )
    return _unsafe_text(
        value,
        max_length=_MAX_STRING_LENGTH,
        allow_activity_uuid=allow_activity_uuid,
    )


def _project(
    value: Any,
    *,
    path: tuple[str | int, ...],
    compact_analysis: bool,
    allow_analysis_location: bool,
    preserve_activity_ids: bool,
    active_containers: set[int],
    depth: int,
) -> Any:
    if depth > _MAX_DEPTH:
        return _DROP
    if value is None or type(value) is bool:
        return value
    if type(value) is int:
        return value if abs(value) <= MAX_SAFE_INTEGER else _DROP
    if type(value) is float:
        return value if math.isfinite(value) else _DROP
    if type(value) is str:
        return (
            _DROP
            if _unsafe_string(value, path=path, preserve_activity_ids=preserve_activity_ids)
            else value
        )
    if type(value) is not dict and type(value) is not list:
        return _DROP

    container_id = id(value)
    if container_id in active_containers:
        return _DROP
    active_containers.add(container_id)
    try:
        if type(value) is list:
            projected_list: list[Any] = []
            for index, item in enumerate(value):
                projected = _project(
                    item,
                    path=(*path, index),
                    compact_analysis=compact_analysis,
                    allow_analysis_location=allow_analysis_location,
                    preserve_activity_ids=preserve_activity_ids,
                    active_containers=active_containers,
                    depth=depth + 1,
                )
                if projected is not _DROP:
                    projected_list.append(projected)
            return projected_list

        projected_dict: dict[str, Any] = {}
        for key, item in cast(dict[Any, Any], value).items():
            if type(key) is not str:
                continue
            if not _location_metadata_key_allowed(path, key):
                continue
            location_key = _is_location_key(key)
            if location_key:
                if not _location_allowed(path, key, allow_analysis_location):
                    continue
                if not _location_shape_allowed(path, item):
                    continue
            if not location_key and (
                _unsafe_key(key, path=path, preserve_activity_ids=preserve_activity_ids)
                or _is_heavy_key(key, compact_analysis=compact_analysis)
            ):
                continue
            projected = _project(
                item,
                path=(*path, key),
                compact_analysis=compact_analysis,
                allow_analysis_location=allow_analysis_location,
                preserve_activity_ids=preserve_activity_ids,
                active_containers=active_containers,
                depth=depth + 1,
            )
            if projected is not _DROP:
                projected_dict[key] = projected
        return projected_dict
    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
        return _DROP
    finally:
        active_containers.discard(container_id)


def project_public_payload(
    value: Any,
    *,
    compact_analysis: bool = False,
    allow_analysis_location: bool = False,
    preserve_activity_ids: bool = False,
) -> Any:
    """Return a recursively projected, standard-JSON-safe copy of ``value``.

    Unsupported values and unsafe fields are omitted. A wholly unsupported root
    becomes ``None`` so callers can always serialize the result without a
    fallback string conversion.
    """
    projected = _project(
        value,
        path=(),
        compact_analysis=compact_analysis,
        allow_analysis_location=allow_analysis_location,
        preserve_activity_ids=preserve_activity_ids,
        active_containers=set(),
        depth=0,
    )
    return None if projected is _DROP else projected
