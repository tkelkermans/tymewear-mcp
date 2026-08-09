"""Tests for activity timestamp reconciliation."""

from tymewear_mcp.tools.timestamps import reconcile_activity_timestamp


def test_epoch_is_authoritative_and_conflicting_z_source_is_not_reinterpreted_as_local():
    result = reconcile_activity_timestamp(
        unix_timestamp=1786271495,
        source_timestamp="2026-08-09T12:31:35Z",
        tz_name="CEST",
        tz_offset="2.0",
    )

    assert result == {
        "utc": "2026-08-09T10:31:35Z",
        "local": "2026-08-09T12:31:35+02:00",
        "source": "2026-08-09T12:31:35Z",
        "tz_name": "CEST",
        "offset_minutes": 120,
        "consistency": {"state": "conflict", "delta_seconds": 7200},
    }


def test_matching_offset_source_is_consistent():
    result = reconcile_activity_timestamp(
        unix_timestamp=1786271495,
        source_timestamp="2026-08-09T12:31:35+02:00",
        tz_name="Europe/Zurich",
        tz_offset="+02:00",
    )

    assert result["utc"] == "2026-08-09T10:31:35Z"
    assert result["local"] == "2026-08-09T12:31:35+02:00"
    assert result["offset_minutes"] == 120
    assert result["consistency"] == {"state": "consistent"}


def test_valid_source_is_used_when_epoch_is_absent_but_consistency_is_unverifiable():
    result = reconcile_activity_timestamp(
        unix_timestamp=None,
        source_timestamp="2026-08-09T10:31:35Z",
        tz_name="CEST",
        tz_offset=2,
    )

    assert result["utc"] == "2026-08-09T10:31:35Z"
    assert result["local"] == "2026-08-09T12:31:35+02:00"
    assert result["consistency"] == {"state": "unverifiable"}


def test_malformed_source_does_not_hide_valid_epoch():
    result = reconcile_activity_timestamp(
        unix_timestamp=1786271495,
        source_timestamp="not-a-timestamp",
        tz_name="CEST",
        tz_offset="2.0",
    )

    assert result["utc"] == "2026-08-09T10:31:35Z"
    assert result["local"] == "2026-08-09T12:31:35+02:00"
    assert result["source"] == "not-a-timestamp"
    assert result["consistency"] == {"state": "unverifiable"}


def test_malformed_epoch_offset_and_source_return_explicit_unknowns():
    result = reconcile_activity_timestamp(
        unix_timestamp="not-an-epoch",
        source_timestamp="not-a-timestamp",
        tz_name=None,
        tz_offset="25:00",
    )

    assert result == {
        "utc": None,
        "local": None,
        "source": "not-a-timestamp",
        "tz_name": None,
        "offset_minutes": None,
        "consistency": {"state": "unverifiable"},
    }
