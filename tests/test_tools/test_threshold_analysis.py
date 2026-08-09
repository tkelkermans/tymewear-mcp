"""Tests for per-activity insight extraction."""

from tymewear_mcp.tools.threshold_analysis import (
    _mmss_to_seconds,
    compute_power_at_threshold,
    extract_activity_insights,
)

PROFILE = {
    "bike_ve_target_vt1": 58.7, "bike_ve_target_bp": 77.6,
    "bike_ve_target_vt2": 114.0, "bike_ve_target_vo2max": 158.3,
    "running_ve_target_vt1": 0.0, "running_ve_target_bp": 0.0,
    "running_ve_target_vt2": 0.0, "running_ve_target_vo2max": 0.0,
}

WZD = {
    "thresholds_zone": {
        "VT1": {"HR": 131.0, "VE": 60.68, "confidence": "high"},
        "VT2": {"HR": 155.0, "VE": 113.32, "confidence": "high"},
        "_quality": {"fit_r2": 0.965, "reason": "", "per_threshold_confidence": {"VT1": "high", "VT2": "high"}},
    },
    "zone_summary_table": {"Duration [sec]": {"Total": 3231.0, "Zone 1": 848.0}},
    "min_max_used": {"HR_max": 179.0, "VE_max": 194.3},
    "steady_state_intensity": {"VT1": {"power": 132.9}, "VT2": {"power": 263.6}},
}

# metrics layout: index 12 = instant power, 13 = HR, 24/25 = rounded power, 26 = precise power
def _metrics(instant, hr, rounded, precise):
    arr = [None] * 28
    arr[12], arr[13], arr[24], arr[25], arr[26] = instant, hr, rounded, rounded, precise
    return arr


TEST_ACTIVITY = {
    "id": "e4", "name": "Ramp", "sport": "2", "sport_display": "Bike", "data_type": "tyme-wear",
    "type_display": "Threshold Test",
    "duration": "53:48", "duration_seconds": 3228, "kcal_expenditure": 644.0,
    "time_stamp": "2026-06-17T15:47:12Z", "unix_timestamp": 1781704032,
    "tz_name": "CEST", "tz_offset": "2.0",
    "new_zone_fitness_level": "Elite",
    "new_zone_vt1": "37:27", "new_zone_vt2": "44:34", "new_zone_vo2max": "52:23", "new_zone_fatmax": "30:41",
    "new_zone_vt1_metrics": _metrics("236", "151", "250.0", "249.6"),
    "new_zone_vt2_metrics": _metrics("290", "162", "290.0", "289.6"),
    "new_zone_vo2max_metrics": _metrics("335", "172", "350.0", "349.2"),
    "predict_ve_v3": [57.0, 58.0],
    "predict_time_v3": [0.0, 1.0],
    "ext_hr": [150.0, 151.0, 152.0],
    "ext_bike_power": [],
}


def test_mmss():
    assert _mmss_to_seconds("37:27") == 2247
    assert _mmss_to_seconds("") is None
    assert _mmss_to_seconds(None) is None
    assert _mmss_to_seconds("1:02:03") == 3723


def test_insights_complete_test():
    r = extract_activity_insights(WZD, TEST_ACTIVITY, PROFILE)
    # labeled thresholds from workout-zone-detection
    assert r["thresholds"]["VT1"]["ve"] == 60.68
    assert r["thresholds"]["VT1"]["hr"] == 131.0
    assert r["thresholds"]["VT1"]["confidence"] == "high"
    assert r["thresholds"]["VT1"]["steady_state_power_w"] == 132.9
    assert r["thresholds"]["VT2"]["ve"] == 113.32
    # detected breakpoints + displayed power from activity metrics (tests only)
    assert r["detected_breakpoints"]["vt1"]["time_seconds"] == 2247
    assert r["detected_breakpoints"]["vt1"]["displayed_power_w"] == 250.0
    assert r["detected_breakpoints"]["vt1"]["instant_power_w"] == 236.0
    assert r["detected_breakpoints"]["vt2"]["displayed_power_w"] == 290.0
    assert r["breakpoints"]["vt1"]["availability"] == {
        "state": "available",
        "reason": "threshold_detected",
        "source": "activity.new_zone_vt1",
    }
    # context
    assert r["ve_targets"]["vt2"] == 114.0
    assert r["fitness_level"] == "Elite"
    assert r["truncated_test"] is False
    assert r["quality"]["fit_r2"] == 0.965
    assert r["zone_summary"]["Duration [sec]"]["Total"] == 3231.0
    assert r["started_at"] == "2026-06-17T13:47:12Z"
    assert r["timestamps"] == {
        "utc": "2026-06-17T13:47:12Z",
        "local": "2026-06-17T15:47:12+02:00",
        "source": "2026-06-17T15:47:12Z",
        "tz_name": "CEST",
        "offset_minutes": 120,
        "consistency": {"state": "conflict", "delta_seconds": 7200},
    }
    assert r["ve_curve_available"] is True


def test_insights_add_metric_units_source_paths_and_methods_without_removing_scalars():
    r = extract_activity_insights(WZD, TEST_ACTIVITY, PROFILE)

    assert r["thresholds"]["VT1"]["ve"] == 60.68
    assert r["thresholds"]["VT1"]["hr"] == 131.0
    assert r["thresholds"]["VT1"]["steady_state_power_w"] == 132.9
    assert r["thresholds"]["VT1"]["metrics"] == {
        "ve": {
            "value": 60.68,
            "canonical_unit": "L/min",
            "source_path": "wzd.thresholds_zone.VT1.VE",
            "method": "workout_zone_detection",
        },
        "hr": {
            "value": 131.0,
            "canonical_unit": "bpm",
            "source_path": "wzd.thresholds_zone.VT1.HR",
            "method": "workout_zone_detection",
        },
        "steady_state_power": {
            "value": 132.9,
            "canonical_unit": "W",
            "source_path": "wzd.steady_state_intensity.VT1.power",
            "method": "workout_zone_detection_steady_state",
        },
    }
    assert r["metrics"] == {
        "elapsed": {
            "value": 3228,
            "canonical_unit": "s",
            "source_path": "activity.duration_seconds",
            "method": "reported",
        },
        "energy": {
            "value": 644.0,
            "canonical_unit": "kcal",
            "source_path": "activity.kcal_expenditure",
            "method": "reported",
        },
    }
    assert r["breakpoints"]["vt1"]["metrics"]["elapsed"] == {
        "value": 2247,
        "canonical_unit": "s",
        "source_path": "activity.new_zone_vt1",
        "method": "detected_breakpoint",
    }
    assert r["breakpoints"]["vt1"]["metrics"]["displayed_power"] == {
        "value": 250.0,
        "canonical_unit": "W",
        "source_path": "activity.new_zone_vt1_metrics[24]",
        "method": "positional_metric_array",
    }


def test_power_note_reports_vendor_paths_without_claiming_measurement_method():
    r = extract_activity_insights(WZD, TEST_ACTIVITY, PROFILE)

    note = r["note"]
    assert "vendor-reported" in note
    assert "wzd.steady_state_intensity" in note
    assert "positional activity metric arrays" in note
    assert "does not verify the upstream calculation or measurement method" in note
    assert "measured, not estimated" not in note


def test_model_input_bounds_are_not_presented_as_activity_extrema():
    r = extract_activity_insights(WZD, TEST_ACTIVITY, PROFILE)

    assert "min_max" not in r
    assert r["model_input_bounds"] == {
        "values": {"HR_max": 179.0, "VE_max": 194.3},
        "source_path": "wzd.min_max_used",
        "method": "model_calibration_input",
        "interpretation": "model_calibration_bounds_not_activity_extrema",
    }


def test_raw_channel_completeness_uses_arrays_and_omitted_lengths_including_zero():
    activity = {
        **TEST_ACTIVITY,
        "predict_ve_v3": [57.0, 58.0],
        "ext_hr": [],
        "_omitted_fields": {
            "predict_time_v3": {"type": "list", "length": 3228},
            "ext_bike_power": {"type": "list", "length": 0},
        },
    }
    activity.pop("predict_time_v3")
    activity.pop("ext_bike_power")

    r = extract_activity_insights(WZD, activity, PROFILE)

    assert r["raw_channel_completeness"] == {
        "method": "activity_array_inventory",
        "channels": {
            "ventilation": {
                "state": "observed",
                "sample_count": 2,
                "source_path": "activity.predict_ve_v3",
                "method": "array_length",
            },
            "elapsed": {
                "state": "observed",
                "sample_count": 3228,
                "source_path": "activity.predict_time_v3",
                "method": "omitted_field_length",
            },
            "heart_rate": {
                "state": "reported_empty",
                "sample_count": 0,
                "source_path": "activity.ext_hr",
                "method": "array_length",
            },
            "power": {
                "state": "reported_empty",
                "sample_count": 0,
                "source_path": "activity.ext_bike_power",
                "method": "omitted_field_length",
            },
        },
    }
    assert r["quality"]["fit_r2"] == 0.965


def test_truncated_test_flagged():
    activity = {
        "id": "x", "sport": "2", "new_zone_vt1": "20:00", "new_zone_vt2": "28:00",
        "new_zone_vo2max": "", "predict_ve_v3": [1.0], "type_display": "Threshold Test",
    }
    r = extract_activity_insights({}, activity, PROFILE)
    assert r["truncated_test"] is True
    assert "vo2max" not in r["detected_breakpoints"]
    assert r["breakpoints"]["vo2max"]["availability"] == {
        "state": "not_computed",
        "reason": "threshold_not_detected",
        "source": "activity.new_zone_vo2max",
    }
    assert r["breakpoints"]["fatmax"]["availability"] == {
        "state": "not_computed",
        "reason": "threshold_not_detected",
        "source": "activity.new_zone_fatmax",
    }


def test_regular_ride_no_breakpoints_but_has_thresholds():
    wzd = {"thresholds_zone": {"VT1": {"HR": 150.0, "VE": 78.89, "confidence": "medium"}}}
    activity = {
        "id": "r", "sport": "2", "type_display": "Normal Activity",
        "new_zone_vt1": "", "new_zone_vt2": "", "new_zone_vo2max": "",
    }
    r = extract_activity_insights(wzd, activity, PROFILE)
    assert r["thresholds"]["VT1"]["confidence"] == "medium"
    assert r["thresholds"]["VT1"]["steady_state_power_w"] is None
    assert r["detected_breakpoints"] == {}
    for name in ("vt1", "vt2", "vo2max", "fatmax"):
        assert r["breakpoints"][name]["availability"] == {
            "state": "not_computed",
            "reason": "normal_activity",
            "source": f"activity.new_zone_{name}",
        }
    assert r["raw_channel_completeness"]["channels"]["heart_rate"] == {
        "state": "unknown",
        "sample_count": None,
        "source_path": "activity.ext_hr",
        "method": "not_reported",
    }
    assert r["ve_curve_available"] is False
    assert r["truncated_test"] is False


def test_normal_activity_with_ve_samples_still_uses_normal_activity_reason():
    activity = {
        "id": "normal-with-ve",
        "type": "0",
        "predict_ve_v3": [55.0, 56.0],
        "new_zone_vt1": "",
        "new_zone_vt2": "",
        "new_zone_vo2max": "",
        "new_zone_fatmax": "",
    }

    r = extract_activity_insights({}, activity, PROFILE)

    assert r["ve_curve_available"] is True
    for name in ("vt1", "vt2", "vo2max", "fatmax"):
        assert r["breakpoints"][name]["availability"]["reason"] == "normal_activity"
    assert r["truncated_test"] is False


def test_declared_test_without_samples_or_detections_uses_threshold_not_detected_reason():
    activity = {
        "id": "empty-test",
        "type_display": "Bike Threshold Test",
        "predict_ve_v3": [],
        "new_zone_vt1": "",
        "new_zone_vt2": "",
        "new_zone_vo2max": "",
        "new_zone_fatmax": "",
    }

    r = extract_activity_insights({}, activity, PROFILE)

    assert r["ve_curve_available"] is False
    for name in ("vt1", "vt2", "vo2max", "fatmax"):
        assert r["breakpoints"][name]["availability"]["reason"] == "threshold_not_detected"


def test_unknown_activity_type_does_not_guess_from_empty_arrays():
    activity = {
        "id": "unknown",
        "predict_ve_v3": [],
        "new_zone_vt1": "",
        "new_zone_vt2": "",
        "new_zone_vo2max": "",
        "new_zone_fatmax": "",
    }

    r = extract_activity_insights({}, activity, PROFILE)

    for name in ("vt1", "vt2", "vo2max", "fatmax"):
        assert r["breakpoints"][name]["availability"] == {
            "state": "not_computed",
            "reason": "activity_type_unknown",
            "source": f"activity.new_zone_{name}",
        }


def test_power_at_threshold_windowed_mean():
    samples = [[float(t), 100.0 + t] for t in range(0, 120)]  # watts ramps 100..219 with time
    times = {"vt1": 60, "vt2": None}
    r = compute_power_at_threshold(times, samples, window_seconds=5)
    assert r["vt1"]["samples"] == 11  # seconds 55..65 inclusive
    assert r["vt1"]["power_watts"] == 160.0  # mean of 155..165
    assert r["vt1"]["at_seconds"] == 60
    assert r["vt2"] is None


def test_power_at_threshold_no_samples_in_window():
    r = compute_power_at_threshold({"vt1": 5000}, [[0.0, 200.0]], window_seconds=15)
    assert r["vt1"]["power_watts"] is None
    assert r["vt1"]["samples"] == 0


def test_power_at_threshold_ignores_null_watts():
    r = compute_power_at_threshold({"vt1": 10}, [[10.0, None], [11.0, 250.0]], window_seconds=5)
    assert r["vt1"]["power_watts"] == 250.0
    assert r["vt1"]["samples"] == 1
