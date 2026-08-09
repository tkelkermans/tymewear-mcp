"""Tests for breathing data tools."""

from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from tymewear_mcp.tools._validation import GetProcessedDataInput
from tymewear_mcp.tools.breathing_data import get_new_processed_data, get_processed_data

SAMPLE_TIMESERIES = [
    {"time": 0, "br": 15.2, "tv": 1.8, "ve": 27.4, "hr": 120, "power": 180, "zone": 1},
    {"time": 1, "br": 16.0, "tv": 1.9, "ve": 30.4, "hr": 125, "power": 190, "zone": 1},
    {"time": 2, "br": 18.5, "tv": 2.1, "ve": 38.9, "hr": 140, "power": 220, "zone": 2},
    {"time": 3, "br": 22.0, "tv": 2.5, "ve": 55.0, "hr": 155, "power": 260, "zone": 2},
    {"time": 4, "br": 28.0, "tv": 2.8, "ve": 78.4, "hr": 170, "power": 300, "zone": 3},
]


class TestGetProcessedData:
    async def test_summary_mode(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=SAMPLE_TIMESERIES)
        mock_client.sanitize = lambda d: d
        result = await get_processed_data(mock_client, "abc-123", mode="summary")
        assert result["available"] is True
        assert result["availability"] == {
            "state": "available",
            "reason": "data_available",
            "source": "processed_data",
        }
        assert result["total_records"] == 5
        assert "averages" in result
        assert "peaks" in result

    async def test_window_mode_filters_inclusive_elapsed_time_not_list_indexes(self):
        mock_client = AsyncMock()
        sparse_timeseries = [
            {"time": 5, "ve": 20.0},
            {"time": 20, "ve": 30.0},
            {"time": 30, "ve": 40.0},
            {"time": 45, "ve": 50.0},
        ]
        mock_client.get = AsyncMock(return_value=sparse_timeseries)
        mock_client.sanitize = lambda d: d
        result = await get_processed_data(mock_client, "abc-123", mode="window", window_start=20, window_end=30)
        assert result["total_records"] == 4
        assert result["data"] == sparse_timeseries[1:3]

    async def test_full_mode(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=SAMPLE_TIMESERIES)
        mock_client.sanitize = lambda d: d
        result = await get_processed_data(mock_client, "abc-123", mode="full")
        assert len(result["data"]) == 5

    @pytest.mark.parametrize("wrapper", ["data", "results", "records", "samples"])
    async def test_common_dict_wrappers_are_normalized(self, wrapper):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={wrapper: SAMPLE_TIMESERIES, "count": 5})
        mock_client.sanitize = lambda d: d

        result = await get_processed_data(mock_client, "abc-123", mode="full")

        assert result["data"] == SAMPLE_TIMESERIES
        assert result["total_records"] == 5

    async def test_channel_inventory_reports_canonical_units_and_coverage(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=[
                {"time": 0, "ve": 20.0, "hr": 120, "cadence": None},
                {"time": 2, "ve": None, "hr": 130, "cadence": 85},
            ]
        )
        mock_client.sanitize = lambda d: d

        result = await get_processed_data(mock_client, "abc-123", mode="summary")

        assert result["channels"] == {
            "cadence": {"canonical_unit": "rpm", "samples": 1, "coverage": 0.5},
            "hr": {"canonical_unit": "bpm", "samples": 2, "coverage": 1.0},
            "ve": {"canonical_unit": "L/min", "samples": 1, "coverage": 0.5},
        }


class TestGetNewProcessedData:
    async def test_returns_tagged_normalized_data(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"results": SAMPLE_TIMESERIES})
        mock_client.sanitize = lambda d: d
        result = await get_new_processed_data(mock_client, "abc-123")

        assert result["available"] is True
        assert result["availability"] == {
            "state": "available",
            "reason": "data_available",
            "source": "new_processed_data",
        }
        assert result["data"] == SAMPLE_TIMESERIES
        assert result["total_records"] == 5
        mock_client.get.assert_called_once_with("/v2/api/activities/abc-123/new-processed-data/")

def _http_error(status: int, detail: str = "Private upstream detail") -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://api.tymewear.com/x")
    resp = httpx.Response(status, json={"detail": detail}, request=req)
    return httpx.HTTPStatusError("err", request=req, response=resp)


class TestProcessedDataUnavailable:
    async def test_processed_data_404_graceful(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=_http_error(404))
        mock_client.sanitize = lambda d: d
        result = await get_processed_data(mock_client, "abc-123", mode="summary")
        assert result["available"] is False
        assert result["reason"] == "processed_data_not_available"
        assert result["status_code"] == 404
        assert result["availability"] == {
            "state": "unavailable",
            "reason": "processed_data_not_available",
            "source": "processed_data",
            "http_status": 404,
        }
        assert "detail" not in result
        assert "Private upstream detail" not in repr(result)

    async def test_new_processed_data_404_graceful(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=_http_error(404))
        mock_client.sanitize = lambda d: d
        result = await get_new_processed_data(mock_client, "abc-123")
        assert result["available"] is False
        assert result["reason"] == "new_processed_data_not_available"
        assert result["availability"]["source"] == "new_processed_data"


class TestProcessedDataInputValidation:
    @pytest.mark.parametrize(
        "values",
        [
            {"mode": "window"},
            {"mode": "window", "window_start": 10},
            {"mode": "window", "window_end": 10},
        ],
    )
    def test_window_mode_requires_both_bounds(self, values):
        with pytest.raises(ValidationError):
            GetProcessedDataInput(activity_id="abc-123", **values)

    @pytest.mark.parametrize("field", ["window_start", "window_end"])
    def test_window_bounds_cannot_be_negative(self, field):
        values = {"mode": "window", "window_start": 0, "window_end": 10, field: -1}

        with pytest.raises(ValidationError):
            GetProcessedDataInput(activity_id="abc-123", **values)

    def test_window_end_cannot_precede_start(self):
        with pytest.raises(ValidationError):
            GetProcessedDataInput(activity_id="abc-123", mode="window", window_start=11, window_end=10)

    @pytest.mark.parametrize("mode", ["summary", "full"])
    def test_non_window_modes_reject_window_bounds(self, mode):
        with pytest.raises(ValidationError):
            GetProcessedDataInput(activity_id="abc-123", mode=mode, window_start=0, window_end=10)
