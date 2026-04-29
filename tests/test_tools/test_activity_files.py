from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import httpx

from tymewear_mcp.tools.activity_files import (
    export_activity_strap_files,
    get_activity_logs,
    get_activity_strap_files,
    get_activity_workout_zone_detection,
)


def _json_response(data: dict) -> httpx.Response:
    import json

    return httpx.Response(200, content=json.dumps(data).encode(), headers={"content-type": "application/json"})


def _binary_response() -> httpx.Response:
    return httpx.Response(
        200,
        content=b"strap-data",
        headers={
            "content-type": "application/zip",
            "content-disposition": 'attachment; filename="strap-files.zip"',
        },
    )


def _binary_response_with_filename(filename: str) -> httpx.Response:
    return httpx.Response(
        200,
        content=b"strap-data",
        headers={
            "content-type": "application/zip",
            "content-disposition": f'attachment; filename="{filename}"',
        },
    )


class TestActivityFiles:
    async def test_get_activity_logs(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=[{"event": "created", "token": "secret"}])
        mock_client.sanitize = lambda data: [{"event": item["event"]} for item in data]

        result = await get_activity_logs(mock_client, "abc-123")

        mock_client.get.assert_called_once_with("/v2/api/activities/abc-123/logs/")
        assert result == [{"event": "created"}]

    async def test_get_activity_strap_files_json(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"files": [{"name": "raw.bin"}]})
        mock_client.sanitize = lambda data: data

        result = await get_activity_strap_files(mock_client, "abc-123")

        mock_client.get.assert_called_once_with("/v2/api/activities/abc-123/strap-files/")
        assert result == {"available": True, "files": [{"name": "raw.bin"}]}

    async def test_get_activity_strap_files_available_envelope_wins(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"available": False, "files": []})
        mock_client.sanitize = lambda data: data

        result = await get_activity_strap_files(mock_client, "abc-123")

        assert result == {"available": True, "files": []}

    async def test_get_activity_workout_zone_detection(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"thresholds_zone": {"VT1": 62.1}})
        mock_client.sanitize = lambda data: data

        result = await get_activity_workout_zone_detection(mock_client, "abc-123")

        mock_client.get.assert_called_once_with("/v2/api/activities/abc-123/workout-zone-detection/")
        assert result == {"available": True, "thresholds_zone": {"VT1": 62.1}}

    async def test_export_activity_strap_files_saves_binary(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tymewear_mcp.tools.activity_files.EXPORT_DIR", tmp_path)
        mock_client = AsyncMock()
        mock_client.get_raw = AsyncMock(return_value=_binary_response())

        result = await export_activity_strap_files(mock_client, "abc-12345")

        mock_client.get_raw.assert_called_once_with("/v2/api/activities/abc-12345/strap-files/")
        assert result["format"] == "ZIP"
        assert result["file_size_bytes"] == 10
        assert Path(result["file_path"]).exists()

    async def test_export_activity_strap_files_constrains_content_disposition_filename(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tymewear_mcp.tools.activity_files.EXPORT_DIR", tmp_path)
        mock_client = AsyncMock()
        mock_client.get_raw = AsyncMock(return_value=_binary_response_with_filename("../outside.zip"))

        result = await export_activity_strap_files(mock_client, "abc-12345")

        saved_path = Path(result["file_path"])
        assert saved_path.parent == tmp_path
        assert saved_path.name == "outside.zip"
        assert ".." not in saved_path.parts

    async def test_export_activity_strap_files_returns_json_metadata(self):
        mock_client = AsyncMock()
        mock_client.get_raw = AsyncMock(return_value=_json_response({"files": []}))

        result = await export_activity_strap_files(mock_client, "abc-123")

        assert result == {"available": True, "files": []}

    async def test_export_activity_strap_files_json_available_envelope_wins(self):
        mock_client = AsyncMock()
        mock_client.get_raw = AsyncMock(return_value=_json_response({"available": False, "files": []}))

        result = await export_activity_strap_files(mock_client, "abc-123")

        assert result == {"available": True, "files": []}

    async def test_get_activity_workout_zone_detection_available_envelope_wins(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"available": False, "thresholds_zone": {"VT1": 62.1}})
        mock_client.sanitize = lambda data: data

        result = await get_activity_workout_zone_detection(mock_client, "abc-123")

        assert result == {"available": True, "thresholds_zone": {"VT1": 62.1}}

    async def test_get_activity_strap_files_404_is_availability_result(self):
        request = httpx.Request("GET", "https://api.tymewear.com/v2/api/activities/abc/strap-files/")
        response = httpx.Response(404, json={"detail": "Not found."}, request=request)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError("Not found", request=request, response=response))

        result = await get_activity_strap_files(mock_client, "abc")

        assert result["available"] is False
        assert result["reason"] == "not_found"
        assert result["status_code"] == 404
