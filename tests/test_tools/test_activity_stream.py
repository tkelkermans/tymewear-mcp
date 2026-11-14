"""Coach stream and interval projections against dashboard units."""

from __future__ import annotations

import pytest

from tymewear_mcp.tools.activity_stream import _project_intervals, _project_stream


def _analysis() -> dict:
    rows = []
    # 14:59, 21:57, 26:26, 37:01, 41:19, 51:58 on a 61:12 ride.
    samples = {
        899: (96.7, 38.8, 255.4, 148, 240),
        1317: (108.6, 44.3, 242.2, 155, 280),
        1586: (52.5, 28.0, 180.0, 130, 140),
        2221: (109.9, 47.1, 235.4, 158, 290),
        2479: (47.5, 26.0, 170.0, 128, 120),
        3118: (108.3, 47.6, 226.0, 157, 275),
    }
    for second, (ve, br, tv, hr, power) in samples.items():
        rows.append(
            {
                "elapsed_seconds": second,
                "ventilation": ve,
                "breathing_rate": br,
                "tidal_volume": tv,
                "heart_rate": hr,
                "power": power,
            }
        )
    available = {"state": "partial", "reason": "channel_samples_have_gaps", "source": "fit_export"}
    channels = {}
    for name, unit in (
        ("ventilation", "L/min"),
        ("breathing_rate", "breaths/min"),
        ("tidal_volume", "vol/breath"),
        ("heart_rate", "bpm"),
        ("power", "W"),
    ):
        channels[name] = {"canonical_unit": unit, "availability": available}
    return {
        "activity_id": "22c58cb1-a717-45fc-9b66-ac87f144626d",
        "channels": channels,
        "raw_samples": {"data": rows},
        "laps": [{"start_seconds": 0, "end_seconds": 180, "source": "fit_lap", "avg_power_w": 217}],
    }


def test_stream_matches_dashboard_hover_samples_and_labels() -> None:
    result = _project_stream(
        _analysis(),
        start_seconds=0,
        end_seconds=None,
        sample_period_seconds=1,
        smoothing_seconds=0,
        offset=0,
        limit=10,
        channels=["ventilation", "breathing_rate", "tidal_volume", "heart_rate", "power"],
    )

    hover = next(row for row in result["samples"] if row["elapsed_seconds"] == 899)
    assert hover == {
        "elapsed_seconds": 899,
        "ventilation": 96.7,
        "breathing_rate": 38.8,
        "tidal_volume": 255.4,
        "heart_rate": 148.0,
        "power": 240.0,
    }
    later = next(row for row in result["samples"] if row["elapsed_seconds"] == 3118)
    assert later["ventilation"] == 108.3
    assert later["breathing_rate"] == 47.6
    assert later["tidal_volume"] == 226.0
    assert result["units"]["ventilation"]["unit"] == "vol/min"
    assert result["units"]["breathing_rate"]["unit"] == "brpm"
    assert result["units"]["tidal_volume"]["unit"] == "vol/breath"
    assert "100 vol" in result["units"]["tidal_volume"]["note"]
    assert result["summary"]["ventilation"]["min"] == 47.5
    assert result["summary"]["ventilation"]["max"] == 109.9
    # 38.8 * 255.4 / 100 is 99.1 against the hovered VE of 96.7. Across the six
    # dashboard points the median gap is about 2 vol/min.
    assert result["ventilation_identity"]["median_abs_error_vol_per_min"] == pytest.approx(2.1, abs=0.15)


def test_litre_tidal_volume_is_shown_as_dashboard_vol_per_breath() -> None:
    analysis = _analysis()
    analysis["channels"]["tidal_volume"]["canonical_unit"] = "L"
    for row in analysis["raw_samples"]["data"]:
        row["tidal_volume"] = row["tidal_volume"] / 100.0

    result = _project_stream(
        analysis,
        start_seconds=1317,
        end_seconds=1317,
        sample_period_seconds=1,
        smoothing_seconds=0,
        offset=0,
        limit=5,
        channels=["ventilation", "breathing_rate", "tidal_volume"],
    )

    assert result["samples"][0]["tidal_volume"] == 242.2
    assert result["samples"][0]["ventilation"] == 108.6
    assert result["conversions"]["tidal_volume"] == "litres_times_100"


def test_missing_channel_explains_the_gap() -> None:
    analysis = _analysis()
    analysis["channels"]["ventilation"] = {
        "canonical_unit": "L/min",
        "availability": {
            "state": "unavailable",
            "reason": "requested_channel_not_available",
            "source": "activity_analysis",
        },
        "detail": "No ventilation samples were found in processed data, new processed data, or the FIT export.",
    }
    for row in analysis["raw_samples"]["data"]:
        row.pop("ventilation", None)

    result = _project_stream(
        analysis,
        start_seconds=0,
        end_seconds=None,
        sample_period_seconds=1,
        smoothing_seconds=0,
        offset=0,
        limit=10,
        channels=["ventilation"],
    )

    assert result["samples"] == []
    assert result["availability"]["reason"] == "stream_channels_missing"
    assert "No ventilation samples" in result["channels"]["ventilation"]["detail"]
    assert result["channels"]["ventilation"]["availability"]["reason"] == "requested_channel_not_available"


def test_supplied_interval_and_power_segments() -> None:
    analysis = _analysis()
    # Replace the sparse ride with a short power workout so segments are contiguous.
    rows = []
    for second, power in enumerate([100, 100, 100, 100, 320, 320, 320, 310, 100, 100, 100, 100]):
        rows.append(
            {
                "elapsed_seconds": second,
                "ventilation": 110.0 if power > 250 else 50.0,
                "breathing_rate": 45.0 if power > 250 else 25.0,
                "tidal_volume": 240.0 if power > 250 else 180.0,
                "heart_rate": 160 if power > 250 else 120,
                "power": power,
            }
        )
    analysis["raw_samples"]["data"] = rows
    result = _project_intervals(
        analysis,
        intervals=[{"start_seconds": 4, "end_seconds": 7, "label": "over"}],
        detect="power",
        work_power_w=250,
        min_segment_seconds=3,
    )

    supplied = next(item for item in result["intervals"] if item["source"] == "supplied")
    assert supplied["stats"]["ventilation"]["avg"] == 110.0
    assert supplied["stats"]["ventilation"]["min"] == 110.0
    assert supplied["stats"]["ventilation"]["max"] == 110.0
    assert supplied["stats"]["power"]["end"] == 310
    assert supplied["stats"]["heart_rate"]["max"] == 160
    work = [item for item in result["intervals"] if item["source"] == "power_work"]
    recovery = [item for item in result["intervals"] if item["source"] == "power_recovery"]
    assert work == [
        {
            "label": "work_1",
            "source": "power_work",
            "start_seconds": 4,
            "end_seconds": 7,
            "stats": supplied["stats"],
        }
    ]
    assert [item["start_seconds"] for item in recovery] == [0, 8]
    assert result["units"]["tidal_volume"] == "vol/breath"


def test_lap_detection_uses_fit_laps() -> None:
    result = _project_intervals(
        _analysis(),
        intervals=None,
        detect="laps",
        work_power_w=None,
        min_segment_seconds=30,
    )

    assert result["intervals"][0]["source"] == "fit_lap"
    assert result["intervals"][0]["start_seconds"] == 0
    assert result["intervals"][0]["end_seconds"] == 180
    assert result["intervals"][0]["stats"]["ventilation"]["sample_count"] == 0
    assert "No VE" in result["intervals"][0]["detail"]


def test_missing_laps_are_an_explicit_error() -> None:
    analysis = _analysis()
    analysis["laps"] = []
    result = _project_intervals(
        analysis,
        intervals=None,
        detect="laps",
        work_power_w=None,
        min_segment_seconds=30,
    )

    assert result["availability"]["reason"] == "intervals_not_found"
    assert result["intervals"][0]["detail"] == "This activity's FIT export has no lap messages."


