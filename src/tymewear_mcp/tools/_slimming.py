"""Shared helper for trimming heavy fields out of large API responses.

Several Tyme Wear endpoints embed multi-thousand-element per-second arrays inline,
producing multi-megabyte payloads. ``slim_dict`` drops a known set of heavy keys and
records what was dropped under ``_omitted_fields`` so callers can opt back in.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def describe_omitted(value: Any) -> dict[str, Any]:
    info: dict[str, Any] = {"type": type(value).__name__}
    if isinstance(value, (list, str, dict)):
        info["length"] = len(value)
    return info


def slim_dict(data: Any, heavy_fields: frozenset[str], include: Iterable[str]) -> Any:
    if not isinstance(data, dict):
        return data
    keep = set(include)
    out: dict[str, Any] = {}
    omitted: dict[str, Any] = {}
    for key, value in data.items():
        if key in heavy_fields and key not in keep:
            omitted[key] = describe_omitted(value)
        else:
            out[key] = value
    if omitted:
        out["_omitted_fields"] = omitted
    return out
