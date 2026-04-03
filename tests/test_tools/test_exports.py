from unittest.mock import AsyncMock
import pytest
from tymewear_mcp.tools.exports import export_csv, export_csv_full, export_fit


class TestExportCsv:
    async def test_export(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value={"url": "https://s3.example.com/file.csv"})
        mock_client.sanitize = lambda d: d
        result = await export_csv(mock_client, "abc-123")
        mock_client.post.assert_called_once_with("/v2/api/activities/export-csv/", json={"activity_id": "abc-123"})


class TestExportCsvFull:
    async def test_export(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value={"url": "https://s3.example.com/file-full.csv"})
        mock_client.sanitize = lambda d: d
        result = await export_csv_full(mock_client, "abc-123")
        mock_client.post.assert_called_once_with("/v2/api/activities/export-csv-full/", json={"activity_id": "abc-123"})


class TestExportFit:
    async def test_export(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value={"url": "https://s3.example.com/file.fit"})
        mock_client.sanitize = lambda d: d
        result = await export_fit(mock_client, "abc-123")
        mock_client.post.assert_called_once_with("/v2/api/activities/export-fit/", json={"activity_id": "abc-123"})
