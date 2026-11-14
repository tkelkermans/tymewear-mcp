"""Tymewear ventilation units as the dashboard shows them.

The dashboard labels minute volume ``vol/min``, breathing rate ``brpm``, and
tidal volume ``vol/breath``. FIT developer fields use the same quantities under
the strings ``vol/min``, ``brpm``, and ``vol/br``. Those numbers are already the
dashboard numbers:

* ``vol/min`` matches ``L/min`` one-for-one (a VT2 near 114 is the same figure
  either way).
* ``brpm`` is breaths per minute.
* ``vol/breath`` is Tymewear's volume per breath. It lines up with
  ``VE ≈ BR × TV / 100``, so 100 vol is about 1 L. A hard rep at TV 258–307
  vol/breath is about 2.6–3.1 L. The figure is the dashboard number, in vol
  per breath, and a universal litre calibration is not published by Tymewear.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_UNIT_SPACES = re.compile(r"\s+")

_FIELD_CHANNELS = {
    "tyme_minute_volume": "ventilation",
    "minute_volume": "ventilation",
    "tyme_breath_rate": "breathing_rate",
    "breath_rate": "breathing_rate",
    "tyme_tidal_volume": "tidal_volume",
}

_FIELD_DEFAULT_UNITS = {
    "ve": "L/min",
    "ventilation": "L/min",
    "minute_ventilation": "L/min",
    "tyme_minute_volume": "vol/min",
    "minute_volume": "vol/min",
    "br": "brpm",
    "breathing_rate": "breaths/min",
    "respiratory_rate": "breaths/min",
    "tyme_breath_rate": "brpm",
    "breath_rate": "brpm",
    "tv": "L",
    "tidal_volume": "L",
    "tyme_tidal_volume": "vol/br",
    "hr": "bpm",
    "heart_rate": "bpm",
    "power": "W",
    "bike_power": "W",
    "cadence": "rpm",
}


@dataclass(frozen=True)
class ResolvedUnit:
    """One accepted source unit and the canonical unit it already represents."""

    canonical_unit: str
    dashboard_unit: str
    scale: int
    inferred: bool = False


def normalize_unit_token(value: str) -> str:
    """Case-fold a declared unit and drop interior whitespace."""
    return _UNIT_SPACES.sub("", value.strip().casefold())


def _resolved(canonical_unit: str, dashboard_unit: str, *, inferred: bool = False) -> ResolvedUnit:
    return ResolvedUnit(
        canonical_unit=canonical_unit,
        dashboard_unit=dashboard_unit,
        scale=1,
        inferred=inferred,
    )


_ALIASES: dict[str, dict[str, ResolvedUnit]] = {
    "ventilation": {
        token: _resolved("L/min", "vol/min")
        for token in (
            "l/min",
            "liter/min",
            "liters/min",
            "litre/min",
            "litres/min",
            "vol/min",
            "volume/min",
        )
    },
    "breathing_rate": {
        token: _resolved("breaths/min", "brpm")
        for token in ("breaths/min", "breath/min", "breaths/minute", "brpm", "br/min")
    },
    "tidal_volume": {
        "l": _resolved("L", "L"),
        "liter": _resolved("L", "L"),
        "liters": _resolved("L", "L"),
        "litre": _resolved("L", "L"),
        "litres": _resolved("L", "L"),
        "vol/br": _resolved("vol/breath", "vol/breath"),
        "vol/breath": _resolved("vol/breath", "vol/breath"),
        "vol/breaths": _resolved("vol/breath", "vol/breath"),
        "volume/br": _resolved("vol/breath", "vol/breath"),
        "volume/breath": _resolved("vol/breath", "vol/breath"),
    },
}


def field_default_unit(field_name: str) -> str | None:
    """Return the unit implied by a known Tymewear or Garmin field name."""
    return _FIELD_DEFAULT_UNITS.get(field_name)


def resolve_source_unit(
    channel: str,
    source_unit: str | None,
    *,
    inferred: bool = False,
) -> ResolvedUnit | None:
    """Map a declared unit string onto the canonical unit for ``channel``."""
    if source_unit is None:
        return None
    table = _ALIASES.get(channel)
    if table is None:
        return None
    resolved = table.get(normalize_unit_token(source_unit))
    if resolved is None:
        return None
    if inferred and not resolved.inferred:
        return ResolvedUnit(
            canonical_unit=resolved.canonical_unit,
            dashboard_unit=resolved.dashboard_unit,
            scale=resolved.scale,
            inferred=True,
        )
    return resolved


def resolve_developer_field(field_name: str, source_unit: str | None) -> ResolvedUnit | None:
    """Resolve a FIT developer field, inferring the unit when the file omits it."""
    channel = _FIELD_CHANNELS.get(field_name)
    if channel is None:
        return None
    inferred = source_unit is None
    declared = _FIELD_DEFAULT_UNITS[field_name] if inferred else source_unit
    return resolve_source_unit(channel, declared, inferred=inferred)
