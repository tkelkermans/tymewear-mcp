from unittest.mock import AsyncMock, PropertyMock
from pathlib import Path
import pytest
from httpx import Response, Headers
from tymewear_mcp.tools.exports import export_csv, export_csv_full, export_fit, EXPORT_DIR


def _make_csv_response(content: str = "time,ve,hr\n1,30.5,120\n2,31.0,122\n") -> Response:
    resp = Response(
        status_code=200,
        content=content.encode(),
        headers=Headers({"content-type": "text/csv", "content-disposition": 'attachment; filename="activity.csv"'}),
    )
    return resp


def _make_fit_response(content: bytes = b"\x0e\x10\x00\x00") -> Response:
    resp = Response(
        status_code=200,
        content=content,
        headers=Headers({"content-type": "application/octet-stream", "content-disposition": 'attachment; filename="activity.fit"'}),
    )
    return resp


def _make_json_response(data: dict) -> Response:
    import json
    resp = Response(
        status_code=200,
        content=json.dumps(data).encode(),
        headers=Headers({"content-type": "application/json"}),
    )
    return resp


class TestExportCsv:
    async def test_export_file_response(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tymewear_mcp.tools.exports.EXPORT_DIR", tmp_path)
        mock_client = AsyncMock()
        mock_client.post_raw = AsyncMock(return_value=_make_csv_response())
        result = await export_csv(mock_client, "abc-12345")
        mock_client.post_raw.assert_called_once_with("/v2/api/activities/export-csv/", json={"activity_id": "abc-12345"})
        assert result["format"] == "CSV"
        assert result["total_rows"] == 2
        assert Path(result["file_path"]).exists()

    async def test_export_json_response(self):
        mock_client = AsyncMock()
        mock_client.post_raw = AsyncMock(return_value=_make_json_response({"url": "https://s3.example.com/file.csv"}))
        mock_client.sanitize = lambda d: d
        result = await export_csv(mock_client, "abc-123")
        assert result == {"url": "https://s3.example.com/file.csv"}


class TestExportCsvFull:
    async def test_export_file_response(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tymewear_mcp.tools.exports.EXPORT_DIR", tmp_path)
        mock_client = AsyncMock()
        mock_client.post_raw = AsyncMock(return_value=_make_csv_response())
        result = await export_csv_full(mock_client, "abc-12345")
        mock_client.post_raw.assert_called_once_with("/v2/api/activities/export-csv-full/", json={"activity_id": "abc-12345"})
        assert result["format"] == "CSV"
        assert Path(result["file_path"]).exists()


class TestExportFit:
    async def test_export_file_response(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tymewear_mcp.tools.exports.EXPORT_DIR", tmp_path)
        mock_client = AsyncMock()
        mock_client.post_raw = AsyncMock(return_value=_make_fit_response())
        result = await export_fit(mock_client, "abc-12345")
        mock_client.post_raw.assert_called_once_with("/v2/api/activities/export-fit/", json={"activity_id": "abc-12345"})
        assert result["format"] == "FIT"
        assert result["file_size_bytes"] == 4
        assert Path(result["file_path"]).exists()

    async def test_export_json_response(self):
        mock_client = AsyncMock()
        mock_client.post_raw = AsyncMock(return_value=_make_json_response({"url": "https://s3.example.com/file.fit"}))
        mock_client.sanitize = lambda d: d
        result = await export_fit(mock_client, "abc-123")
        assert result == {"url": "https://s3.example.com/file.fit"}

    async def test_export_fit_falls_back_to_dashboard_get(self, tmp_path, monkeypatch):
        import httpx

        monkeypatch.setattr("tymewear_mcp.tools.exports.EXPORT_DIR", tmp_path)
        request = httpx.Request("POST", "https://api.tymewear.com/v2/api/activities/export-fit/")
        response = httpx.Response(404, json={"detail": "Not found."}, request=request)
        mock_client = AsyncMock()
        mock_client.post_raw = AsyncMock(side_effect=httpx.HTTPStatusError("Not found", request=request, response=response))
        mock_client.get_raw = AsyncMock(return_value=_make_fit_response())

        result = await export_fit(mock_client, "abc-12345")

        mock_client.post_raw.assert_called_once_with("/v2/api/activities/export-fit/", json={"activity_id": "abc-12345"})
        mock_client.get_raw.assert_called_once_with("/api/activities/abc-12345/fit/")
        assert result["format"] == "FIT"
        assert Path(result["file_path"]).exists()
