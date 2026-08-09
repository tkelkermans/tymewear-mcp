from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from garmin_fit_sdk import Encoder

from tymewear_mcp.client.http import TymeClient

ACTIVITY_ID = "5ca66dc7-c21f-47c6-bd6d-cc7cea8c2b9e"


def _http_error(status: int, detail: str = "private upstream detail") -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.tymewear.com/private?token=secret")
    response = httpx.Response(status, json={"detail": detail}, request=request)
    return httpx.HTTPStatusError(detail, request=request, response=response)


def _activity(*, duration_seconds: int = 3) -> dict[str, Any]:
    return {
        "id": ACTIVITY_ID,
        "name": "Morning Ride",
        "sport": "2",
        "sport_display": "Bike",
        "type": "0",
        "type_display": "Normal Activity",
        "data_type": "tyme-wear",
        "duration": f"00:00:{duration_seconds:02d}",
        "duration_seconds": duration_seconds,
        "unix_timestamp": 1786271495,
        "time_stamp": "2026-08-09T12:31:35Z",
        "tz_name": "CEST",
        "tz_offset": "2.0",
        "email": "athlete@example.test",
        "user_uuid": "user-private-uuid",
        "account_id": "account-private-uuid",
        "device_serial": "strap-private-serial",
        "callback_url": "https://example.test/callback?token=secret",
        "home_lat": 46.1,
        "home_long": 7.1,
    }


def _profile() -> dict[str, Any]:
    return {
        "id": 99999,
        "email": "athlete@example.test",
        "bike_ve_target_vt1": 58.7,
        "bike_ve_target_bp": 77.6,
        "bike_ve_target_vt2": 114.0,
        "bike_ve_target_vo2max": 158.3,
    }


def _wzd() -> dict[str, Any]:
    return {
        "thresholds_zone": {
            "VT1": {"HR": 131.0, "VE": 60.68, "confidence": "high"},
            "_quality": {"fit_r2": 0.965, "reason": "", "per_threshold_confidence": {"VT1": "high"}},
        },
        "steady_state_intensity": {"VT1": {"power": 132.9}},
        "zone_summary_table": {"Duration [sec]": {"Total": 3.0, "Zone 1": 1.0, "Zone 2": 2.0}},
        "min_max_used": {"HR_max": 179.0, "VE_max": 194.3},
    }


def _fit_bytes(records: list[dict[str, Any]]) -> bytes:
    encoder = Encoder()
    for record in records:
        encoder.write_mesg({"mesg_num": 20, **record})
    return encoder.close()


class ReadOnlyClient:
    def __init__(
        self,
        *,
        activity: Any | None = None,
        profile: Any | None = None,
        processed: Any | None = None,
        new_processed: Any | None = None,
        wzd: Any | None = None,
        fit: bytes | BaseException | None = None,
    ) -> None:
        self.responses = {
            f"/v2/api/activities/{ACTIVITY_ID}/": _activity() if activity is None else activity,
            "/v2/api/profile/": _profile() if profile is None else profile,
            f"/v2/api/activities/{ACTIVITY_ID}/processed-data/": [] if processed is None else processed,
            f"/v2/api/activities/{ACTIVITY_ID}/new-processed-data/": [] if new_processed is None else new_processed,
            f"/v2/api/activities/{ACTIVITY_ID}/workout-zone-detection/": _wzd() if wzd is None else wzd,
        }
        self.fit = _fit_bytes([]) if fit is None else fit
        self.read_paths: list[str] = []
        self.fit_reads: list[str] = []

    async def get(self, path: str, **kwargs: Any) -> Any:
        assert not kwargs
        self.read_paths.append(path)
        result = self.responses[path]
        if isinstance(result, BaseException):
            raise result
        return result

    async def post_raw(self, path: str, **kwargs: Any) -> httpx.Response:
        self.fit_reads.append(path)
        assert path == "/v2/api/activities/export-fit/"
        assert kwargs == {"json": {"activity_id": ACTIVITY_ID}}
        if isinstance(self.fit, BaseException):
            raise self.fit
        return httpx.Response(200, content=self.fit, headers={"content-type": "application/octet-stream"})

    async def get_raw(self, path: str, **kwargs: Any) -> httpx.Response:
        self.fit_reads.append(path)
        assert not kwargs
        if isinstance(self.fit, BaseException):
            raise self.fit
        return httpx.Response(200, content=self.fit, headers={"content-type": "application/octet-stream"})

    async def post(self, path: str, **kwargs: Any) -> Any:
        raise AssertionError(f"unsupported mutation POST called: {path}, {kwargs}")

    async def patch(self, path: str, **kwargs: Any) -> Any:
        raise AssertionError(f"unsupported mutation PATCH called: {path}, {kwargs}")

    async def delete(self, path: str, **kwargs: Any) -> Any:
        raise AssertionError(f"unsupported mutation DELETE called: {path}, {kwargs}")

    @staticmethod
    def sanitize(data: Any) -> Any:
        return TymeClient.sanitize(data)


async def _analyze(client: ReadOnlyClient, **kwargs: Any) -> dict[str, Any]:
    module = importlib.import_module("tymewear_mcp.tools.activity_analysis")
    analyze = getattr(module, "tw_get_activity_analysis", None)
    assert analyze is not None, "Task 4 requires the unregistered tw_get_activity_analysis callable"
    return await analyze(client, ACTIVITY_ID, **kwargs)


async def test_selects_each_channel_and_null_sample_independently_by_source_priority() -> None:
    started_at = datetime(2026, 8, 9, 10, 31, 35, tzinfo=timezone.utc)
    client = ReadOnlyClient(
        processed=[
            {"time": 0.2, "ve": 40.0, "hr": None},
            {"time": 1.2, "ve": 41.0, "hr": 151},
            {"time": 2.2, "ve": 42.0, "hr": None},
        ],
        new_processed=[
            {"elapsed_seconds": 0, "heart_rate": 141, "power": 250},
            {"elapsed_seconds": 1, "heart_rate": None, "power": None},
            {"elapsed_seconds": 2, "heart_rate": None, "power": 270},
        ],
        fit=_fit_bytes(
            [
                {"timestamp": started_at, "heart_rate": 131, "power": 230, "cadence": 80},
                {"timestamp": started_at + timedelta(seconds=1), "heart_rate": 132, "power": 231, "cadence": 81},
                {"timestamp": started_at + timedelta(seconds=2), "heart_rate": 133, "power": 232, "cadence": 82},
            ]
        ),
    )

    result = await _analyze(client)

    assert result["raw_samples"]["data"] == [
        {"elapsed_seconds": 0, "ventilation": 40.0, "heart_rate": 141, "power": 250, "cadence": 80},
        {"elapsed_seconds": 1, "ventilation": 41.0, "heart_rate": 151, "power": 231, "cadence": 81},
        {"elapsed_seconds": 2, "ventilation": 42.0, "heart_rate": 133, "power": 270, "cadence": 82},
    ]
    assert result["channels"]["ventilation"]["source"] == "processed_data"
    assert result["channels"]["heart_rate"]["source"] == "mixed"
    assert result["channels"]["heart_rate"]["provenance"]["selected_sample_counts"] == {
        "processed_data": 1,
        "new_processed_data": 1,
        "fit_export": 1,
    }
    assert result["channels"]["power"]["provenance"]["selected_sample_counts"] == {
        "new_processed_data": 2,
        "fit_export": 1,
    }
    assert result["channels"]["cadence"]["source_unit"] == "rpm"
    assert result["channels"]["cadence"]["canonical_unit"] == "rpm"
    assert result["channels"]["cadence"]["scale"] == 1
    assert result["channels"]["cadence"]["sample_count"] == 3
    assert result["channels"]["cadence"]["expected_count"] == 3
    assert result["channels"]["cadence"]["coverage_pct"] == 100.0
    assert result["channels"]["cadence"]["availability"]["state"] == "available"


async def test_fit_only_analysis_remains_available_when_processed_sources_are_missing() -> None:
    started_at = datetime(2026, 8, 9, 10, 31, 35, tzinfo=timezone.utc)
    client = ReadOnlyClient(
        processed=_http_error(404),
        new_processed=_http_error(404),
        fit=_fit_bytes([{"timestamp": started_at, "heart_rate": 142, "power": 275, "cadence": 88}]),
    )

    result = await _analyze(client, channels=["heart_rate", "power", "cadence"])

    assert result["capabilities"]["processed_data"]["state"] == "unavailable"
    assert result["capabilities"]["new_processed_data"]["state"] == "unavailable"
    assert result["capabilities"]["fit_export"]["state"] == "available"
    assert result["raw_samples"]["data"] == [
        {"elapsed_seconds": 0, "heart_rate": 142, "power": 275, "cadence": 88}
    ]
    assert all(result["channels"][name]["source"] == "fit_export" for name in ("heart_rate", "power", "cadence"))


async def test_wzd_summary_stays_available_without_processed_fit_or_raw_zone_labels() -> None:
    client = ReadOnlyClient(
        processed=_http_error(404),
        new_processed=_http_error(404),
        fit=_http_error(404),
    )

    result = await _analyze(client)

    assert result["capabilities"]["workout_zone_detection"]["state"] == "available"
    assert result["summary"]["thresholds"]["VT1"]["ve"] == 60.68
    assert result["summary"]["model_quality"]["fit_r2"] == 0.965
    assert result["raw_samples"]["data"] == []
    assert result["breakpoints"] != result["raw_samples"]
    assert result["capabilities"]["raw_zone_labels"] == {
        "state": "not_computed",
        "reason": "raw_zone_labels_not_reported",
        "source": "workout_zone_detection",
    }
    assert "zone_label" not in result["channels"]


def test_wzd_times_zone_is_elapsed_axis_not_raw_zone_labels() -> None:
    module = importlib.import_module("tymewear_mcp.tools.activity_analysis")

    result = module._raw_zone_labels_capability({"times_zone": [0, 1, 2]})

    assert result == {
        "state": "not_computed",
        "reason": "raw_zone_labels_not_reported",
        "source": "workout_zone_detection",
    }


async def test_requested_missing_channel_is_explicit_and_not_inferred_from_other_arrays() -> None:
    client = ReadOnlyClient(
        processed=[{"time": 0, "ve": 40.0}, {"time": 1, "ve": 41.0}],
        new_processed=[],
        fit=_fit_bytes([]),
    )

    result = await _analyze(client, channels=["ventilation", "heart_rate"])

    assert result["channels"]["heart_rate"] == {
        "source": None,
        "source_unit": None,
        "canonical_unit": "bpm",
        "scale": None,
        "sample_count": 0,
        "expected_count": 3,
        "coverage_pct": 0.0,
        "provenance": {
            "selection": "per_channel_per_elapsed_second",
            "source_priority": ["processed_data", "new_processed_data", "fit_export"],
            "selected_sample_counts": {},
            "fields": {},
        },
        "availability": {
            "state": "unavailable",
            "reason": "requested_channel_not_available",
            "source": "activity_analysis",
        },
    }
    assert result["summary"]["raw_channel_completeness"]["channels"]["heart_rate"]["state"] == "unknown"


async def test_requested_channels_do_not_emit_elapsed_only_rows_from_unrequested_channels() -> None:
    started_at = datetime(2026, 8, 9, 10, 31, 35, tzinfo=timezone.utc)
    client = ReadOnlyClient(
        processed=[{"time": 0, "ve": 40.0}],
        new_processed=[],
        fit=_fit_bytes(
            [
                {"timestamp": started_at, "power": 230},
                {"timestamp": started_at + timedelta(seconds=1), "power": 231},
                {"timestamp": started_at + timedelta(seconds=2), "power": 232},
            ]
        ),
    )

    result = await _analyze(client, channels=["ventilation"])

    assert result["raw_samples"]["total_records"] == 1
    assert result["raw_samples"]["data"] == [{"elapsed_seconds": 0, "ventilation": 40.0}]


async def test_paginates_sorted_observed_union_after_merge_and_reports_filtered_outliers() -> None:
    started_at = datetime(2026, 8, 9, 10, 31, 35, tzinfo=timezone.utc)
    client = ReadOnlyClient(
        activity=_activity(duration_seconds=4),
        processed=[
            {"time": -1, "ve": 99.0},
            {"time": 0, "ve": 40.0},
            {"time": 2, "ve": 42.0},
            {"time": 75609, "ve": 100.0},
        ],
        new_processed=[],
        fit=_fit_bytes(
            [
                {"timestamp": started_at, "power": 230},
                {"timestamp": started_at + timedelta(seconds=1), "power": 231},
                {"timestamp": started_at + timedelta(seconds=2), "power": 232},
                {"timestamp": started_at + timedelta(seconds=3), "power": 233},
            ]
        ),
    )

    result = await _analyze(client, offset=1, limit=2)

    assert result["raw_samples"]["total_records"] == 4
    assert result["raw_samples"]["returned_records"] == 2
    assert result["raw_samples"]["data"] == [
        {"elapsed_seconds": 1, "power": 231},
        {"elapsed_seconds": 2, "ventilation": 42.0, "power": 232},
    ]
    assert result["raw_samples"]["next_offset"] == 3
    assert result["raw_samples"]["timeline"] == {
        "policy": "sorted_observed_seconds",
        "expected_count": 4,
        "observed_count": 4,
        "missing_expected_count": 0,
        "discarded_negative_count": 1,
        "discarded_after_duration_count": 1,
        "duration_tolerance_seconds": 2,
    }
    assert "75609" not in str(result["raw_samples"]["data"])


async def test_same_source_same_second_collision_is_deterministic() -> None:
    client = ReadOnlyClient(
        processed=[
            {"time": 0.1, "hr": 140},
            {"time": 0.4, "heart_rate": 199},
        ],
        new_processed=[],
        fit=_fit_bytes([]),
    )

    result = await _analyze(client, channels=["heart_rate"])

    assert result["raw_samples"]["data"] == [{"elapsed_seconds": 0, "heart_rate": 140}]
    assert result["merge_policy"]["same_source_collision"] == "first_non_null_by_record_then_field"


async def test_location_requires_opt_in_and_never_exposes_nonanalytic_sensitive_fields() -> None:
    processed = [
        {
            "time": 0,
            "ve": 40.0,
            "position_lat": 123456,
            "position_long": 654321,
            "home_lat": 46.1,
            "home_long": 7.1,
            "signed_url": "https://s3.example.test/private.fit?token=secret",
            "temp_path": "/private/tmp/private.fit",
            "raw_bytes": b"private-fit",
        }
    ]
    profile = {**_profile(), "bike_ve_target_vt1": "athlete@example.test"}
    wzd = _wzd()
    wzd["min_max_used"] = {
        "HR_max": 179.0,
        "callback_url": "https://example.test/callback?token=secret",
    }
    hidden = await _analyze(
        ReadOnlyClient(processed=processed, new_processed=[], fit=_fit_bytes([]), profile=profile, wzd=wzd)
    )
    visible = await _analyze(
        ReadOnlyClient(processed=processed, new_processed=[], fit=_fit_bytes([]), profile=profile, wzd=wzd),
        include_location=True,
    )

    assert "position_lat" not in hidden["channels"]
    assert visible["raw_samples"]["data"][0]["position_lat"] == 123456
    assert visible["raw_samples"]["data"][0]["position_long"] == 654321
    serialized = repr(visible)
    for private_value in (
        "athlete@example.test",
        "user-private-uuid",
        "account-private-uuid",
        "strap-private-serial",
        "callback",
        "home_lat",
        "home_long",
        "signed_url",
        "s3.example.test",
        "temp_path",
        "/private/tmp",
        "private-fit",
        "token=secret",
    ):
        assert private_value not in serialized


async def test_august9_timestamps_and_zone_seconds_reconcile_with_inclusive_tolerance() -> None:
    activity = _activity(duration_seconds=3231)
    wzd = _wzd()
    wzd["zone_summary_table"] = {
        "Duration [sec]": {"Total": 3230.0, "Zone 1": 848.0, "Zone 2": 1100.0, "Zone 3": 1281.0}
    }
    client = ReadOnlyClient(activity=activity, wzd=wzd, fit=_http_error(404))

    result = await _analyze(client)

    assert result["timestamps"]["utc"] == "2026-08-09T10:31:35Z"
    assert result["timestamps"]["local"] == "2026-08-09T12:31:35+02:00"
    assert result["timestamps"]["consistency"] == {"state": "conflict", "delta_seconds": 7200}
    assert result["summary"]["zones"]["reconciliation"] == {
        "availability": {
            "state": "available",
            "reason": "zone_duration_reconciled",
            "source": "workout_zone_detection",
        },
        "duration_seconds": 3231.0,
        "categorized_seconds": 3229.0,
        "uncategorized_seconds": 2.0,
        "uncategorized_method": "duration_minus_categorized",
        "reconciled_seconds": 3231.0,
        "delta_seconds": 0.0,
        "tolerance_seconds": 2,
        "comparison": "absolute_delta_lte",
        "within_tolerance": True,
    }


async def test_upstream_failures_are_isolated_and_raw_errors_are_not_returned() -> None:
    private_error = RuntimeError("/private/tmp/file.fit?X-Amz-Signature=secret")
    client = ReadOnlyClient(
        activity=private_error,
        profile=private_error,
        processed=private_error,
        new_processed=_http_error(403),
        wzd=private_error,
        fit=private_error,
    )

    result = await _analyze(client, channels=["heart_rate"])

    assert result["activity_id"] == ACTIVITY_ID
    assert result["raw_samples"]["data"] == []
    assert result["capabilities"]["activity_detail"]["reason"] == "upstream_request_failed"
    assert result["capabilities"]["new_processed_data"]["state"] == "permission_denied"
    assert result["capabilities"]["fit_export"]["reason"] == "fit_export_failed"
    serialized = repr(result)
    assert "/private/tmp" not in serialized
    assert "X-Amz-Signature" not in serialized
    assert "secret" not in serialized


def test_nested_threshold_metrics_and_breakpoints_use_safe_projection() -> None:
    module = importlib.import_module("tymewear_mcp.tools.activity_analysis")
    private_url = "https://example.test/callback?token=secret"

    thresholds = module._safe_thresholds(
        {
            "VT1": {
                "ve": private_url,
                "hr": 131,
                "metrics": {
                    "ve": {"value": private_url, "canonical_unit": "L/min"},
                    "hr": {"value": 131, "canonical_unit": "bpm"},
                },
            }
        }
    )
    project_breakpoints = getattr(module, "_safe_breakpoints", None)
    assert project_breakpoints is not None, "breakpoints require an explicit nested projection"
    breakpoints = project_breakpoints(
        {
            "vt1": {
                "availability": {"state": "available", "reason": "threshold_detected", "source": "safe"},
                "time": "1:02",
                "time_seconds": 62,
                "displayed_power_w": 250,
                "metrics": {
                    "elapsed": {"value": 62, "canonical_unit": "s", "source_path": private_url},
                    "secret": private_url,
                },
            }
        }
    )

    assert thresholds["VT1"]["metrics"] == {
        "hr": {"value": 131, "canonical_unit": "bpm"},
    }
    assert breakpoints["vt1"]["time_seconds"] == 62
    assert breakpoints["vt1"]["metrics"] == {
        "elapsed": {"value": 62, "canonical_unit": "s"},
    }
    assert private_url not in repr(thresholds)
    assert private_url not in repr(breakpoints)
