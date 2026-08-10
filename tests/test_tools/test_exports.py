import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import Headers, Response

from tymewear_mcp.tools.exports import export_csv, export_csv_full, export_fit


def _make_csv_response(
    content: str = "time,ve,hr\n1,30.5,120\n2,31.0,122\n",
    filename: str = "activity.csv",
) -> Response:
    resp = Response(
        status_code=200,
        content=content.encode(),
        headers=Headers({"content-type": "text/csv", "content-disposition": f'attachment; filename="{filename}"'}),
    )
    return resp


def _make_fit_response(content: bytes = b"\x0e\x10\x00\x00", filename: str = "activity.fit") -> Response:
    resp = Response(
        status_code=200,
        content=content,
        headers=Headers(
            {
                "content-type": "application/octet-stream",
                "content-disposition": f'attachment; filename="{filename}"',
            }
        ),
    )
    return resp


def _make_json_response(data: dict) -> Response:
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
        mock_client.post_raw.assert_called_once_with(
            "/v2/api/activities/export-csv/", json={"activity_id": "abc-12345"}
        )
        assert result["format"] == "CSV"
        assert result["total_rows"] == 2
        assert Path(result["file_path"]).exists()

    async def test_export_json_response(self):
        mock_client = AsyncMock()
        mock_client.post_raw = AsyncMock(return_value=_make_json_response({"url": "https://s3.example.com/file.csv"}))
        mock_client.sanitize = lambda d: d
        result = await export_csv(mock_client, "abc-123")
        assert result == {"url": "https://s3.example.com/file.csv"}

    @pytest.mark.parametrize("filename", ["../../evil.csv", r"..\evil.csv"])
    async def test_export_filename_cannot_escape_export_dir(self, tmp_path, monkeypatch, filename):
        export_dir = tmp_path / "exports" / "nested"
        monkeypatch.setattr("tymewear_mcp.tools.exports.EXPORT_DIR", export_dir)
        mock_client = AsyncMock()
        mock_client.post_raw = AsyncMock(return_value=_make_csv_response(filename=filename))

        result = await export_csv(mock_client, "abc-12345")

        filepath = Path(result["file_path"])
        assert filepath == export_dir / "evil.csv"
        assert filepath.exists()


class TestExportCsvFull:
    async def test_export_file_response(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tymewear_mcp.tools.exports.EXPORT_DIR", tmp_path)
        mock_client = AsyncMock()
        mock_client.post_raw = AsyncMock(return_value=_make_csv_response())
        result = await export_csv_full(mock_client, "abc-12345")
        mock_client.post_raw.assert_called_once_with(
            "/v2/api/activities/export-csv-full/", json={"activity_id": "abc-12345"}
        )
        assert result["format"] == "CSV"
        assert Path(result["file_path"]).exists()


class TestExportFit:
    async def test_export_file_response(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tymewear_mcp.tools.exports.EXPORT_DIR", tmp_path)
        mock_client = AsyncMock()
        mock_client.post_raw = AsyncMock(return_value=_make_fit_response())
        result = await export_fit(mock_client, "abc-12345")
        mock_client.post_raw.assert_called_once_with(
            "/v2/api/activities/export-fit/", json={"activity_id": "abc-12345"}
        )
        assert result["format"] == "FIT"
        assert result["file_size_bytes"] == 4
        assert Path(result["file_path"]).exists()

    async def test_export_json_response(self):
        mock_client = AsyncMock()
        mock_client.post_raw = AsyncMock(return_value=_make_json_response({"url": "https://s3.example.com/file.fit"}))
        mock_client.sanitize = lambda d: d
        result = await export_fit(mock_client, "abc-123")
        assert result == {"url": "https://s3.example.com/file.fit"}

    @pytest.mark.parametrize("filename", ["../../evil.fit", r"..\evil.fit"])
    async def test_export_filename_cannot_escape_export_dir(self, tmp_path, monkeypatch, filename):
        export_dir = tmp_path / "exports" / "nested"
        monkeypatch.setattr("tymewear_mcp.tools.exports.EXPORT_DIR", export_dir)
        mock_client = AsyncMock()
        mock_client.post_raw = AsyncMock(return_value=_make_fit_response(filename=filename))

        result = await export_fit(mock_client, "abc-12345")

        filepath = Path(result["file_path"])
        assert filepath == export_dir / "evil.fit"
        assert filepath.exists()

    @pytest.mark.parametrize("status_code", [403, 404])
    async def test_export_fit_falls_back_to_dashboard_get(self, tmp_path, monkeypatch, status_code):
        monkeypatch.setattr("tymewear_mcp.tools.exports.EXPORT_DIR", tmp_path)
        request = httpx.Request("POST", "https://api.tymewear.com/v2/api/activities/export-fit/")
        response = httpx.Response(status_code, json={"detail": "Not found."}, request=request)
        mock_client = AsyncMock()
        mock_client.post_raw = AsyncMock(
            side_effect=httpx.HTTPStatusError("Not found", request=request, response=response)
        )
        mock_client.get_raw = AsyncMock(return_value=_make_fit_response())

        result = await export_fit(mock_client, "abc-12345")

        mock_client.post_raw.assert_called_once_with(
            "/v2/api/activities/export-fit/", json={"activity_id": "abc-12345"}
        )
        mock_client.get_raw.assert_called_once_with("/api/activities/abc-12345/fit/")
        assert result["format"] == "FIT"
        assert Path(result["file_path"]).exists()

    async def test_export_fit_reraises_unexpected_post_error(self):
        request = httpx.Request("POST", "https://api.tymewear.com/v2/api/activities/export-fit/")
        response = httpx.Response(500, json={"detail": "Server error"}, request=request)
        mock_client = AsyncMock()
        mock_client.post_raw = AsyncMock(
            side_effect=httpx.HTTPStatusError("Server error", request=request, response=response)
        )
        mock_client.get_raw = AsyncMock()

        with pytest.raises(httpx.HTTPStatusError):
            await export_fit(mock_client, "abc-12345")

        mock_client.get_raw.assert_not_called()


def _make_html_response(status: int = 200) -> Response:
    return Response(
        status_code=status,
        content=b"<!DOCTYPE html>\n<html><head><title>404 Not Found</title></head></html>",
        headers=Headers({"content-type": "text/html"}),
    )


class TestExportRejectsHtmlErrorPage:
    async def test_csv_full_html_returns_unavailable(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tymewear_mcp.tools.exports.EXPORT_DIR", tmp_path)
        mock_client = AsyncMock()
        mock_client.post_raw = AsyncMock(return_value=_make_html_response())
        result = await export_csv_full(mock_client, "abc-12345")
        assert result["available"] is False
        assert result["reason"] == "export_unavailable"
        assert not any(tmp_path.iterdir())
