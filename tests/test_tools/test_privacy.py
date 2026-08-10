from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

ACTIVITY_ID = "5ca66dc7-c21f-47c6-bd6d-cc7cea8c2b9e"


def _privacy_module() -> Any:
    return importlib.import_module("tymewear_mcp.tools._privacy")


def _public_module() -> Any:
    return importlib.import_module("tymewear_mcp.public")


def test_public_projector_removes_nested_private_values_without_mutating_input() -> None:
    payload: dict[Any, Any] = {
        "activity_id": ACTIVITY_ID,
        "availability": {
            "state": "partial",
            "reason": "partial_analysis_available",
            "source": "activity_analysis",
        },
        "metric": 42.5,
        "email": "athlete@example.test",
        "user_uuid": "91f58f70-f70c-42d4-8d31-2eff3b765111",
        "account_id": "private-account-id",
        "profile": {
            "id": "44b83d59-5cb4-42c4-a134-20b65f3d377c",
            "email_address": "coach@example.test",
            "safe_metric": 17,
        },
        "device": {"identifier": "strap-id", "serial_number": "strap-serial"},
        "callback_url": "https://example.test/callback?token=private",
        "download_url": "https://example.test/export.fit?X-Amz-Signature=private",
        "signed_url": "s3://private-bucket/activity.fit",
        "artifact": "/private/tmp/activity.fit",
        "query": "access_token=private",
        "nested": [
            {"power": 250, "email": "nested@example.test", 7: "non-string-key"},
            b"private bytes",
            Path("/tmp/private.fit"),
        ],
    }
    nested_input = payload["nested"]
    profile_input = payload["profile"]

    projected = _privacy_module().project_public_payload(payload)

    assert projected == {
        "activity_id": ACTIVITY_ID,
        "availability": {
            "state": "partial",
            "reason": "partial_analysis_available",
            "source": "activity_analysis",
        },
        "metric": 42.5,
        "profile": {"safe_metric": 17},
        "device": {},
        "nested": [{"power": 250}],
    }
    assert payload["nested"] is nested_input
    assert payload["profile"] is profile_input
    assert payload["email"] == "athlete@example.test"
    json.dumps(projected, allow_nan=False)


def test_public_projector_is_total_for_cycles_unsupported_values_and_nonfinite_numbers() -> None:
    payload: dict[str, Any] = {
        "ok": True,
        "nan": float("nan"),
        "positive_infinity": float("inf"),
        "negative_infinity": float("-inf"),
        "oversized_integer": 10**10000,
        "unsupported": object(),
    }
    payload["cycle"] = payload

    projected = _privacy_module().project_public_payload(payload)

    assert projected == {"ok": True}
    json.dumps(projected, allow_nan=False)


def test_public_projector_drops_source_controlled_sensitive_or_unsafe_keys() -> None:
    payload = {
        "source": "processed_data",
        "provenance": {"selection": "per_channel_per_elapsed_second"},
        "athlete_email_metric": 1,
        "token_value": 2,
        "https://evil.example/path": 3,
        "/tmp/private": 4,
        "unsafe\nkey": 5,
        "x" * 257: 6,
        9: "non-string",
    }

    projected = _privacy_module().project_public_payload(payload)

    assert projected == {
        "source": "processed_data",
        "provenance": {"selection": "per_channel_per_elapsed_second"},
    }


def test_public_projector_applies_semantic_secret_and_locator_checks_to_keys() -> None:
    activity_id = "550e8400-e29b-41d4-a716-446655440000"
    payload = {
        "activity_id": activity_id,
        "safe_metric": 42,
        "coach@example.test": "private email key",
        "access_token=secret": "private credential key",
        "Bearer abc.def.ghi": "private bearer key",
        "91f58f70-f70c-42d4-8d31-2eff3b765111": "private UUID key",
        "decoder failed at /private/var/folders/x.fit": "embedded path key",
        "source /Users/name/file.fit": "embedded home path key",
        "tymewear-production-files.s3.amazonaws.com/private/activity.fit": "bare S3 key",
        "ftp://files.example.test/activity.fit": "generic URI key",
        "ssh://host/private": "generic URI key",
        "data:text/plain;base64,cHJpdmF0ZQ==": "data URI key",
        "AKIAIOSFODNN7EXAMPLE": "access key credential",
    }

    projected = _privacy_module().project_public_payload(payload)

    assert projected == {"activity_id": activity_id, "safe_metric": 42}


def test_public_projector_drops_bare_s3_hosts_and_embedded_absolute_path_values() -> None:
    payload = {
        "safe": "processed_data",
        "sample_a": "tymewear-production-files.s3.amazonaws.com/private/activity.fit",
        "sample_b": "decoder failed at /private/var/folders/x.fit",
        "sample_c": "source /Users/name/file.fit",
        "sample_d": r"decoder failed at C:\Users\name\file.fit",
        "sample_e": "ftp://files.example.test/activity.fit",
        "sample_f": "ssh://host/private",
        "sample_g": "data:text/plain;base64,cHJpdmF0ZQ==",
        "sample_h": "AKIAIOSFODNN7EXAMPLE",
    }

    projected = _privacy_module().project_public_payload(payload)

    assert projected == {"safe": "processed_data"}


def test_public_projector_rejects_uuid_versions_generically_except_activity_id() -> None:
    activity_id_v7 = "019fa766-9608-7222-a89e-947ab771c665"
    private_profile_v7 = "019fa766-9608-7222-a89e-947ab771c666"
    payload = {
        "activity_id": activity_id_v7,
        "profile": private_profile_v7,
        private_profile_v7: "private UUID key",
        "metric": 42,
    }

    projected = _privacy_module().project_public_payload(payload)

    assert projected == {"activity_id": activity_id_v7, "metric": 42}


def test_public_wrapper_preserves_compact_analysis_contract_and_strips_other_raw_fields() -> None:
    payload = {
        "activity_id": ACTIVITY_ID,
        "availability": {
            "state": "available",
            "reason": "analysis_available",
            "source": "activity_analysis",
        },
        "capabilities": {
            "raw_zone_labels": {
                "state": "not_computed",
                "reason": "raw_zone_labels_not_reported",
                "source": "workout_zone_detection",
            }
        },
        "channels": {
            "heart_rate": {
                "source": "mixed",
                "canonical_unit": "bpm",
                "provenance": {
                    "selection": "per_channel_per_elapsed_second",
                    "source_priority": ["processed_data", "new_processed_data", "fit_export"],
                },
                "availability": {
                    "state": "available",
                    "reason": "channel_data_available",
                    "source": "activity_analysis",
                },
            }
        },
        "raw_samples": {
            "total_records": 1,
            "data": [{"elapsed_seconds": 0, "heart_rate": 141, "raw_bytes": b"private"}],
        },
        "x": [0, 1, 2],
        "predict_ve_v3": [40.0, 41.0],
        "ext_hr": [140, 141],
        "times_zone": [0, 1],
        "rawData": [{"email": "athlete@example.test"}],
        "predictVeV3": [40.0, 41.0],
        "extHr": [140, 141],
    }

    analysis = _public_module().project_public_tool_result("tw_get_activity_analysis", payload)
    ordinary = _public_module().project_public_tool_result("tw_get_activity", payload)

    assert analysis["activity_id"] == ACTIVITY_ID
    assert analysis["availability"] == payload["availability"]
    assert analysis["capabilities"] == payload["capabilities"]
    assert analysis["channels"] == payload["channels"]
    assert analysis["raw_samples"] == {
        "total_records": 1,
        "data": [{"elapsed_seconds": 0, "heart_rate": 141}],
    }
    assert "raw_samples" not in ordinary
    for projected in (analysis, ordinary):
        assert "x" not in projected
        assert "predict_ve_v3" not in projected
        assert "ext_hr" not in projected
        assert "times_zone" not in projected
        assert "rawData" not in projected
        assert "predictVeV3" not in projected
        assert "extHr" not in projected
        json.dumps(projected, allow_nan=False)


def test_public_wrapper_preserves_only_activity_object_id_aliases() -> None:
    first_activity_id = "550e8400-e29b-41d4-a716-446655440000"
    second_activity_id = "5ca66dc7-c21f-47c6-bd6d-cc7cea8c2b9e"
    private_user_id = "91f58f70-f70c-42d4-8d31-2eff3b765111"
    activity = {
        "id": first_activity_id,
        "activity_uuid": first_activity_id,
        "name": "Ride",
        "user": {"id": private_user_id, "display": "Athlete"},
    }
    activities = {
        "results": [
            activity,
            {"activity_uuid": second_activity_id, "name": "Run", "account": {"id": private_user_id}},
        ],
        "next": None,
    }

    projected_activity = _public_module().project_public_tool_result("tw_get_activity", activity)
    projected_activities = _public_module().project_public_tool_result("tw_get_activities", activities)
    projected_profile = _public_module().project_public_tool_result("tw_get_profile", activity)

    assert projected_activity == {
        "id": first_activity_id,
        "activity_uuid": first_activity_id,
        "name": "Ride",
        "user": {"display": "Athlete"},
    }
    assert projected_activities == {
        "results": [
            {
                "id": first_activity_id,
                "activity_uuid": first_activity_id,
                "name": "Ride",
                "user": {"display": "Athlete"},
            },
            {"activity_uuid": second_activity_id, "name": "Run", "account": {}},
        ],
        "next": None,
    }
    assert projected_profile == {"name": "Ride", "user": {"display": "Athlete"}}


def test_public_wrapper_allows_only_exact_opted_in_analysis_location_paths() -> None:
    payload = {
        "activity_id": ACTIVITY_ID,
        "identity": {
            "name": "Ride",
            "home_lat": 46.1,
            "home_long": 7.1,
            "start_position": [46.1, 7.1],
        },
        "summary": {"latitude": 46.2, "longitude": 7.2},
        "channels": {
            "position_lat": {
                "source": "fit_export",
                "canonical_unit": "semicircles",
                "availability": {"state": "available", "reason": "channel_data_available"},
            },
            "position_long": {
                "source": "fit_export",
                "canonical_unit": "semicircles",
                "availability": {"state": "available", "reason": "channel_data_available"},
            },
            "latitude": {"source": "untrusted"},
            "heart_rate": {"source": "fit_export", "canonical_unit": "bpm"},
        },
        "raw_samples": {
            "data": [
                {
                    "elapsed_seconds": 0,
                    "position_lat": 550000000,
                    "position_long": 85000000,
                    "latitude": 46.3,
                    "longitude": 7.3,
                    "home_lat": 46.1,
                    "heart_rate": 140,
                }
            ]
        },
        "position_lat": 1,
        "position_long": 2,
    }

    opted_in = _public_module().project_public_tool_result(
        "tw_get_activity_analysis", payload, include_location=True
    )
    not_opted_in = _public_module().project_public_tool_result(
        "tw_get_activity_analysis", payload, include_location=False
    )
    nonliteral_opt_in = _public_module().project_public_tool_result(
        "tw_get_activity_analysis", payload, include_location=1
    )
    other_tool = _public_module().project_public_tool_result(
        "tw_get_activity_workout_zone_detection", payload, include_location=True
    )

    assert opted_in["channels"] == {
        "position_lat": payload["channels"]["position_lat"],
        "position_long": payload["channels"]["position_long"],
        "heart_rate": payload["channels"]["heart_rate"],
    }
    assert opted_in["raw_samples"]["data"] == [
        {
            "elapsed_seconds": 0,
            "position_lat": 550000000,
            "position_long": 85000000,
            "heart_rate": 140,
        }
    ]
    serialized = json.dumps(opted_in, allow_nan=False)
    assert "home_lat" not in serialized
    assert "latitude" not in serialized
    assert '"position_lat": 1' not in serialized
    assert '"position_long": 2' not in serialized
    assert "start_position" not in serialized

    for projected in (not_opted_in, nonliteral_opt_in):
        assert set(projected["channels"]) == {"heart_rate"}
        assert projected["raw_samples"]["data"] == [{"elapsed_seconds": 0, "heart_rate": 140}]
    assert "raw_samples" not in other_tool
    assert "position_lat" not in json.dumps(other_tool)
    assert "position_long" not in json.dumps(other_tool)


def test_public_wrapper_rejects_malformed_location_channel_and_sample_shapes() -> None:
    payload = {
        "channels": {
            "position_lat": 46.1,
            "position_long": [7.1],
            "heart_rate": {"source": "fit_export", "canonical_unit": "bpm"},
        },
        "raw_samples": {
            "data": [
                {
                    "elapsed_seconds": 0,
                    "position_lat": {"value": 46.1},
                    "position_long": [7.1],
                    "heart_rate": 140,
                }
            ]
        },
    }

    projected = _public_module().project_public_tool_result(
        "tw_get_activity_analysis", payload, include_location=True
    )

    assert projected == {
        "channels": {"heart_rate": {"source": "fit_export", "canonical_unit": "bpm"}},
        "raw_samples": {"data": [{"elapsed_seconds": 0, "heart_rate": 140}]},
    }


def test_public_wrapper_whitelists_location_channel_metadata_without_coordinate_values() -> None:
    metadata = {
        "source": "fit_export",
        "source_unit": "semicircles",
        "canonical_unit": "semicircles",
        "scale": 1,
        "sample_count": 2,
        "expected_count": 2,
        "coverage_pct": 100.0,
        "provenance": {
            "selection": "per_channel_per_elapsed_second",
            "source_priority": ["fit_export"],
            "selected_sample_counts": {"fit_export": 2},
            "fields": {"fit_export": ["position_lat"]},
        },
        "availability": {
            "state": "available",
            "reason": "channel_data_available",
            "source": "fit_export",
        },
        "value": 46.1,
        "samples": [46.1, 46.2],
    }
    payload = {
        "channels": {"position_lat": metadata},
        "raw_samples": {"data": [{"elapsed_seconds": 0, "position_lat": 550000000}]},
    }

    projected = _public_module().project_public_tool_result(
        "tw_get_activity_analysis", payload, include_location=True
    )

    expected_metadata = {key: value for key, value in metadata.items() if key not in {"value", "samples"}}
    assert projected == {
        "channels": {"position_lat": expected_metadata},
        "raw_samples": {"data": [{"elapsed_seconds": 0, "position_lat": 550000000}]},
    }
