"""Tests for per-activity insight extraction."""

from tymewear_mcp.tools.threshold_analysis import _mmss_to_seconds, extract_activity_insights

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
    "duration": "53:48", "time_stamp": "2026-06-17T15:47:12Z", "unix_timestamp": 1781704032,
    "new_zone_fitness_level": "Elite",
    "new_zone_vt1": "37:27", "new_zone_vt2": "44:34", "new_zone_vo2max": "52:23", "new_zone_fatmax": "30:41",
    "new_zone_vt1_metrics": _metrics("236", "151", "250.0", "249.6"),
    "new_zone_vt2_metrics": _metrics("290", "162", "290.0", "289.6"),
    "new_zone_vo2max_metrics": _metrics("335", "172", "350.0", "349.2"),
    "predict_ve_v3": [57.0, 58.0],
}


def test_mmss():
    assert _mmss_to_seconds("37:27") == 2247
    assert _mmss_to_seconds("") is None
    assert _mmss_to_seconds(None) is None
    assert _mmss_to_seconds("1:02:03") == 3723


def test_insights_complete_test():
    r = extract_activity_insights(WZD, TEST_ACTIVITY, PROFILE)
    # labeled thresholds from workout-zone-detection
    assert r["thresholds"]["VT1"] == {"ve": 60.68, "hr": 131.0, "confidence": "high", "estimated_power_w": 132.9}
    assert r["thresholds"]["VT2"]["ve"] == 113.32
    # detected breakpoints + displayed power from activity metrics (tests only)
    assert r["detected_breakpoints"]["vt1"]["time_seconds"] == 2247
    assert r["detected_breakpoints"]["vt1"]["displayed_power_w"] == 250.0
    assert r["detected_breakpoints"]["vt1"]["instant_power_w"] == 236.0
    assert r["detected_breakpoints"]["vt2"]["displayed_power_w"] == 290.0
    # context
    assert r["ve_targets"]["vt2"] == 114.0
    assert r["fitness_level"] == "Elite"
    assert r["truncated_test"] is False
    assert r["quality"]["fit_r2"] == 0.965
    assert r["zone_summary"]["Duration [sec]"]["Total"] == 3231.0
    assert r["started_at"] == "2026-06-17T15:47:12Z"
    assert r["ve_curve_available"] is True


def test_truncated_test_flagged():
    activity = {
        "id": "x", "sport": "2", "new_zone_vt1": "20:00", "new_zone_vt2": "28:00",
        "new_zone_vo2max": "", "predict_ve_v3": [1.0],
    }
    r = extract_activity_insights({}, activity, PROFILE)
    assert r["truncated_test"] is True
    assert "vo2max" not in r["detected_breakpoints"]


def test_regular_ride_no_breakpoints_but_has_thresholds():
    wzd = {"thresholds_zone": {"VT1": {"HR": 150.0, "VE": 78.89, "confidence": "medium"}}}
    activity = {"id": "r", "sport": "2", "new_zone_vt1": "", "new_zone_vt2": "", "new_zone_vo2max": ""}
    r = extract_activity_insights(wzd, activity, PROFILE)
    assert r["thresholds"]["VT1"]["confidence"] == "medium"
    assert r["thresholds"]["VT1"]["estimated_power_w"] is None
    assert r["detected_breakpoints"] == {}
    assert r["ve_curve_available"] is False
    assert r["truncated_test"] is False
