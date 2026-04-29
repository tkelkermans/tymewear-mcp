"""Tests for breathing data tools."""

from unittest.mock import AsyncMock

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
        assert result["total_records"] == 5
        assert "averages" in result
        assert "peaks" in result

    async def test_window_mode(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=SAMPLE_TIMESERIES)
        mock_client.sanitize = lambda d: d
        result = await get_processed_data(mock_client, "abc-123", mode="window", window_start=1, window_end=3)
        assert result["total_records"] == 5
        assert len(result["data"]) == 3

    async def test_full_mode(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=SAMPLE_TIMESERIES)
        mock_client.sanitize = lambda d: d
        result = await get_processed_data(mock_client, "abc-123", mode="full")
        assert len(result["data"]) == 5


class TestGetNewProcessedData:
    async def test_returns_data(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=SAMPLE_TIMESERIES)
        mock_client.sanitize = lambda d: d
        await get_new_processed_data(mock_client, "abc-123")
        mock_client.get.assert_called_once_with("/v2/api/activities/abc-123/new-processed-data/")

    async def test_handles_not_found(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"detail": "Not found."})
        mock_client.sanitize = lambda d: d
        result = await get_new_processed_data(mock_client, "abc-123")
        assert result.get("detail") == "Not found."
