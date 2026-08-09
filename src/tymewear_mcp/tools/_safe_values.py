"""Small JSON-safe value and metadata validators used by read-only compositions."""

from __future__ import annotations

import math
import re
from typing import Any

MAX_SAFE_INTEGER = 2**53 - 1
SENSITIVE_NAME_PARTS = frozenset(
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
_SAFE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_. -]*")
_SAFE_UNIT = re.compile(r"[A-Za-z0-9%°^_. -]+(?:/[A-Za-z0-9%°^_. -]+)?")


def finite_number(
    value: Any,
    *,
    allow_bool: bool = False,
    max_abs: int | float = MAX_SAFE_INTEGER,
) -> int | float | bool | None:
    """Return a finite, bounded JSON number without lossy overflow coercion."""
    if isinstance(value, bool):
        return value if allow_bool else None
    if isinstance(value, int):
        return value if abs(value) <= max_abs else None
    if isinstance(value, float):
        return value if math.isfinite(value) and abs(value) <= max_abs else None
    return None


def normalized_parts(value: str) -> frozenset[str]:
    snake_case = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    normalized = re.sub(r"[^a-z0-9]+", "_", snake_case.casefold()).strip("_")
    return frozenset(part for part in normalized.split("_") if part)


def safe_name(value: Any, *, max_length: int = 64, reject_sensitive: bool = True) -> str | None:
    """Validate a source-controlled metadata key or field name."""
    if not isinstance(value, str) or not 1 <= len(value) <= max_length or _SAFE_NAME.fullmatch(value) is None:
        return None
    if reject_sensitive and normalized_parts(value) & SENSITIVE_NAME_PARTS:
        return None
    return value


def safe_unit(value: Any) -> str | None:
    """Validate a short declared unit without accepting paths, URLs or controls."""
    if not isinstance(value, str) or not 1 <= len(value) <= 24 or _SAFE_UNIT.fullmatch(value) is None:
        return None
    if normalized_parts(value) & SENSITIVE_NAME_PARTS:
        return None
    return value


def safe_text(value: Any, *, max_length: int = 128) -> str | None:
    """Keep a compact printable scalar while excluding obvious private locators."""
    if not isinstance(value, str) or not 1 <= len(value) <= max_length:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    lowered = value.casefold()
    if "@" in value or "://" in value or value.startswith(("/", "\\")):
        return None
    if normalized_parts(lowered) & SENSITIVE_NAME_PARTS:
        return None
    return value
