from __future__ import annotations

import gzip
import importlib
import importlib.util
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from garmin_fit_sdk import Encoder

from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.tools import exports as exports_mod


def _response(
    content: bytes,
    *,
    content_type: str = "application/octet-stream",
    status_code: int = 200,
) -> httpx.Response:
    return httpx.Response(status_code, content=content, headers={"content-type": content_type})


async def _fetch_fit_bytes(client: Any, activity_id: str, **kwargs: Any) -> bytes:
    fetch = getattr(exports_mod, "fetch_fit_bytes", None)
    assert fetch is not None, "fetch_fit_bytes must provide the in-memory export boundary"
    return await fetch(client, activity_id, **kwargs)


def _fit_timeseries_module():
    spec = importlib.util.find_spec("tymewear_mcp.tools.fit_timeseries")
    assert spec is not None, "fit_timeseries must provide the in-memory decoder"
    return importlib.import_module("tymewear_mcp.tools.fit_timeseries")


def _encoded_fit() -> bytes:
    developer_data_id = {
        "mesg_num": 207,
        "developer_data_index": 0,
        "application_id": [1] * 16,
    }
    field_description = {
        "mesg_num": 206,
        "developer_data_index": 0,
        "field_definition_number": 0,
        "fit_base_type_id": 136,
        "field_name": "tyme_minute_volume",
        "units": "L/min",
    }
    encoder = Encoder()
    encoder.add_developer_field(0, developer_data_id, field_description)
    encoder.write_mesg(developer_data_id)
    encoder.write_mesg(field_description)
    encoder.write_mesg(
        {
            "mesg_num": 20,
            "timestamp": datetime(2026, 8, 9, 10, 31, 35, tzinfo=timezone.utc),
            "heart_rate": 142,
            "power": 275,
            "cadence": 88,
            "position_lat": 123456,
            "position_long": 654321,
            "developer_fields": {0: 42.5},
        }
    )
    encoder.write_mesg(
        {
            "mesg_num": 20,
            "timestamp": datetime(2026, 8, 9, 10, 31, 36, tzinfo=timezone.utc),
            "heart_rate": 143,
            "power": 280,
            "cadence": 89,
            "developer_fields": {0: 43.5},
        }
    )
    return encoder.close()


class _CountingStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.chunks_read = 0

    async def __aiter__(self):
        for chunk in self.chunks:
            self.chunks_read += 1
            yield chunk


class TestFetchFitBytes:
    async def test_returns_posted_fit_body_without_writing_to_disk(self, tmp_path, monkeypatch):
        monkeypatch.setattr(exports_mod, "EXPORT_DIR", tmp_path)
        client = AsyncMock()
        client.post_raw.return_value = _response(b"direct-fit")

        result = await _fetch_fit_bytes(client, "activity-123")

        assert result == b"direct-fit"
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.parametrize("status_code", [403, 404])
    async def test_falls_back_to_dashboard_fit_endpoint(self, status_code):
        request = httpx.Request("POST", "https://api.tymewear.com/v2/api/activities/export-fit/")
        denied = httpx.Response(status_code, request=request)
        client = AsyncMock()
        client.post_raw.side_effect = httpx.HTTPStatusError("unavailable", request=request, response=denied)
        client.get_raw.return_value = _response(b"dashboard-fit")

        result = await _fetch_fit_bytes(client, "activity-123")

        assert result == b"dashboard-fit"
        client.get_raw.assert_awaited_once_with("/api/activities/activity-123/fit/")

    async def test_resolves_allowlisted_https_signed_url(self):
        client = AsyncMock()
        client.post_raw.return_value = _response(
            b'{"url":"https://tymewear-production-files.s3.amazonaws.com/exports/activity.fit?signature=secret"}',
            content_type="application/json",
        )
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"signed-fit", request=request))
        async with httpx.AsyncClient(transport=transport) as download_client:
            result = await _fetch_fit_bytes(client, "activity-123", download_client=download_client)

        assert result == b"signed-fit"

    @pytest.mark.parametrize(
        "url",
        [
            "http://downloads.tymewear.com/activity.fit",
            "https://api.tymewear.com/activity.fit",
            "https://downloads.tymewear.com/activity.fit",
            "https://attacker.example/activity.fit",
            "https://user:password@tymewear-production-files.s3.amazonaws.com/activity.fit",
            "https://tymewear-production-files.s3.amazonaws.com:444/activity.fit",
            "https://tymewear-production-files.s3.amazonaws.com:not-a-port/activity.fit",
            "https://tymewear-production-files.s3.amazonaws.com/activity.fit#secret",
            "https://tymewear-production-files.s3.amazonaws.com.evil.example/activity.fit",
        ],
    )
    async def test_rejects_unsafe_signed_url(self, url):
        client = AsyncMock()
        client.post_raw.return_value = _response(
            ("{\"url\":\"" + url + "\"}").encode(),
            content_type="application/json",
        )

        with pytest.raises(ValueError, match="FIT download URL"):
            await _fetch_fit_bytes(client, "activity-123")

    async def test_allows_one_allowlisted_redirect(self):
        client = AsyncMock()
        client.post_raw.return_value = _response(
            b'{"url":"https://tymewear-production-files.s3.amazonaws.com/first.fit"}',
            content_type="application/json",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/first.fit":
                return httpx.Response(
                    302,
                    headers={"location": "https://tymewear-production-files.s3.amazonaws.com/final.fit"},
                    request=request,
                )
            return httpx.Response(200, content=b"redirected-fit", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as download_client:
            result = await _fetch_fit_bytes(client, "activity-123", download_client=download_client)

        assert result == b"redirected-fit"

    async def test_rejects_second_redirect(self):
        client = AsyncMock()
        client.post_raw.return_value = _response(
            b'{"url":"https://tymewear-production-files.s3.amazonaws.com/first.fit"}',
            content_type="application/json",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            next_path = "/second.fit" if request.url.path == "/first.fit" else "/third.fit"
            return httpx.Response(
                302,
                headers={"location": f"https://tymewear-production-files.s3.amazonaws.com{next_path}"},
                request=request,
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as download_client:
            with pytest.raises(ValueError, match="more than one redirect"):
                await _fetch_fit_bytes(client, "activity-123", download_client=download_client)

    async def test_rejects_redirect_to_a_different_host(self):
        client = AsyncMock()
        client.post_raw.return_value = _response(
            b'{"url":"https://tymewear-production-files.s3.amazonaws.com/first.fit"}',
            content_type="application/json",
        )
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                302,
                headers={"location": "https://api.tymewear.com/final.fit"},
                request=request,
            )
        )

        async with httpx.AsyncClient(transport=transport) as download_client:
            with pytest.raises(ValueError, match="FIT download URL"):
                await _fetch_fit_bytes(client, "activity-123", download_client=download_client)

    async def test_rejects_oversized_direct_response(self, monkeypatch):
        monkeypatch.setattr(exports_mod, "MAX_FIT_RESPONSE_BYTES", 4, raising=False)
        client = AsyncMock()
        client.post_raw.return_value = _response(b"12345")

        with pytest.raises(ValueError, match="size limit"):
            await _fetch_fit_bytes(client, "activity-123")

    async def test_stops_reading_direct_response_when_transport_limit_is_crossed(self, monkeypatch):
        monkeypatch.setattr(exports_mod, "MAX_FIT_RESPONSE_BYTES", 5)
        response_stream = _CountingStream([b"1234", b"5678", b"must-not-be-read"])
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "application/octet-stream"},
                stream=response_stream,
                request=request,
            )
        )
        client = TymeClient(access_token="test-token")
        await client._http.aclose()
        client._http = httpx.AsyncClient(base_url="https://api.tymewear.com", transport=transport)

        try:
            with pytest.raises(ValueError, match="size limit"):
                await _fetch_fit_bytes(client, "activity-123")
        finally:
            await client.close()

        assert response_stream.chunks_read == 2

    async def test_signed_download_raises_for_404(self):
        client = AsyncMock()
        client.post_raw.return_value = _response(
            b'{"url":"https://tymewear-production-files.s3.amazonaws.com/missing.fit"}',
            content_type="application/json",
        )
        transport = httpx.MockTransport(lambda request: httpx.Response(404, request=request))

        async with httpx.AsyncClient(transport=transport) as download_client:
            with pytest.raises(httpx.HTTPStatusError):
                await _fetch_fit_bytes(client, "activity-123", download_client=download_client)


class TestDecodeFitTimeseries:
    def test_normalizes_decoded_messages_with_declared_developer_names_and_units(self):
        mod = _fit_timeseries_module()
        normalize = getattr(mod, "normalize_fit_messages", None)
        assert normalize is not None, "decoded FIT messages need a pure normalization boundary"
        started_at = datetime(2026, 8, 9, 10, 31, 35, tzinfo=timezone.utc)
        messages = {
            "field_description_mesgs": [
                {"key": 0, "field_name": "tyme_minute_volume", "units": "L/min"},
            ],
            "record_mesgs": [
                {
                    "timestamp": started_at,
                    "heart_rate": 142,
                    "power": 275,
                    "cadence": 88,
                    "position_lat": 123456,
                    "position_long": 654321,
                    "developer_fields": {0: 42.5},
                },
                {
                    "timestamp": started_at + timedelta(seconds=1),
                    "heart_rate": 143,
                    "power": 280,
                    "cadence": 89,
                    "developer_fields": {0: 43.5},
                },
            ],
        }

        result = normalize(messages, decoder_warnings=[])

        assert result["availability"] == {
            "state": "available",
            "reason": "data_available",
            "source": "fit_export",
        }
        assert result["data"] == [
            {
                "elapsed_seconds": 0,
                "timestamp": "2026-08-09T10:31:35Z",
                "heart_rate": 142,
                "power": 275,
                "cadence": 88,
                "tyme_minute_volume": 42.5,
            },
            {
                "elapsed_seconds": 1,
                "timestamp": "2026-08-09T10:31:36Z",
                "heart_rate": 143,
                "power": 280,
                "cadence": 89,
                "tyme_minute_volume": 43.5,
            },
        ]
        assert result["channels"]["tyme_minute_volume"] == {
            "source_unit": "L/min",
            "canonical_unit": "L/min",
            "scale": 1,
            "sample_count": 2,
            "expected_count": 2,
            "coverage_pct": 100.0,
            "provenance": {"source": "fit_export", "field": "tyme_minute_volume"},
        }
        assert "position_lat" not in result["data"][0]
        assert "position_long" not in result["data"][0]

    def test_decodes_sdk_encoded_fit_and_pages_records(self):
        mod = _fit_timeseries_module()
        decode = getattr(mod, "decode_fit_timeseries", None)
        assert decode is not None, "FIT bytes need an official-SDK decoder"

        result = decode(_encoded_fit(), offset=1, limit=1)

        assert result["total_records"] == 2
        assert result["returned_records"] == 1
        assert result["offset"] == 1
        assert result["limit"] == 1
        assert result["has_more"] is False
        assert result["next_offset"] is None
        assert result["data"] == [
            {
                "elapsed_seconds": 1,
                "timestamp": "2026-08-09T10:31:36Z",
                "heart_rate": 143,
                "power": 280,
                "cadence": 89,
                "tyme_minute_volume": 43.5,
            }
        ]

    def test_location_requires_explicit_opt_in(self):
        mod = _fit_timeseries_module()
        decode = getattr(mod, "decode_fit_timeseries", None)
        assert decode is not None

        result = decode(_encoded_fit(), include_location=True)

        assert result["data"][0]["position_lat"] == 123456
        assert result["data"][0]["position_long"] == 654321
        assert result["channels"]["position_lat"]["canonical_unit"] == "semicircles"

    def test_developer_coordinates_and_collision_renames_require_location_opt_in(self):
        mod = _fit_timeseries_module()
        normalize = getattr(mod, "normalize_fit_messages", None)
        assert normalize is not None
        messages = {
            "field_description_mesgs": [
                {"key": 0, "field_name": "position_lat", "units": "degrees"},
                {"key": 1, "field_name": "latitude", "units": "degrees"},
                {"key": 2, "field_name": "gpsLatitude", "units": "degrees"},
            ],
            "record_mesgs": [
                {
                    "timestamp": datetime(2026, 8, 9, 10, 31, 35, tzinfo=timezone.utc),
                    "position_lat": 123456,
                    "developer_fields": {0: 46.102, 1: 46.103, 2: 46.104},
                }
            ],
        }

        hidden = normalize(messages, decoder_warnings=[])
        included = normalize(messages, decoder_warnings=[], include_location=True)

        assert hidden["data"] == [{"elapsed_seconds": 0, "timestamp": "2026-08-09T10:31:35Z"}]
        assert hidden["channels"] == {}
        assert included["data"][0]["position_lat"] == 123456
        assert included["data"][0]["developer_position_lat"] == 46.102
        assert included["data"][0]["latitude"] == 46.103
        assert included["data"][0]["gpsLatitude"] == 46.104
        assert included["channels"]["developer_position_lat"]["source_unit"] == "degrees"
        assert included["channels"]["latitude"]["source_unit"] == "degrees"

    def test_unverified_developer_unit_does_not_claim_canonical_conversion(self):
        mod = _fit_timeseries_module()
        normalize = getattr(mod, "normalize_fit_messages", None)
        assert normalize is not None
        messages = {
            "field_description_mesgs": [
                {"key": 0, "field_name": "tyme_tidal_volume", "units": "vol/br"},
            ],
            "record_mesgs": [
                {
                    "timestamp": datetime(2026, 8, 9, 10, 31, 35, tzinfo=timezone.utc),
                    "developer_fields": {0: 1.2},
                }
            ],
        }

        result = normalize(messages, decoder_warnings=[])

        assert result["channels"]["tyme_tidal_volume"] == {
            "source_unit": "vol/br",
            "canonical_unit": None,
            "scale": None,
            "sample_count": 1,
            "expected_count": 1,
            "coverage_pct": 100.0,
            "provenance": {"source": "fit_export", "field": "tyme_tidal_volume"},
            "conversion": {"state": "unverified", "reason": "source_unit_not_canonical"},
        }

    def test_accepts_gzip_fit_payload(self):
        mod = _fit_timeseries_module()
        decode = getattr(mod, "decode_fit_timeseries", None)
        assert decode is not None

        result = decode(gzip.compress(_encoded_fit()))

        assert result["total_records"] == 2
        assert result["compression"] == "gzip"

    def test_rejects_compressed_and_decompressed_size_limits(self, monkeypatch):
        mod = _fit_timeseries_module()
        decode = getattr(mod, "decode_fit_timeseries", None)
        assert decode is not None
        payload = gzip.compress(_encoded_fit())

        monkeypatch.setattr(mod, "MAX_COMPRESSED_FIT_BYTES", len(payload) - 1)
        with pytest.raises(ValueError, match="compressed size limit"):
            decode(payload)

        monkeypatch.setattr(mod, "MAX_COMPRESSED_FIT_BYTES", len(payload))
        monkeypatch.setattr(mod, "MAX_DECOMPRESSED_FIT_BYTES", len(_encoded_fit()) - 1)
        with pytest.raises(ValueError, match="decompressed size limit"):
            decode(payload)

    def test_malformed_fit_returns_unavailable_capability(self):
        mod = _fit_timeseries_module()
        decode = getattr(mod, "decode_fit_timeseries", None)
        assert decode is not None

        result = decode(b"not-a-fit-file")

        assert result["available"] is False
        assert result["availability"] == {
            "state": "unavailable",
            "reason": "fit_decode_failed",
            "source": "fit_export",
        }
        assert result["data"] == []

    def test_decoder_read_exception_returns_safe_unavailable_capability(self, monkeypatch):
        mod = _fit_timeseries_module()
        decode = getattr(mod, "decode_fit_timeseries", None)
        assert decode is not None

        class RaisingDecoder:
            def __init__(self, stream):
                self.stream = stream

            def is_fit(self):
                return True

            def read(self):
                raise RuntimeError("/private/leak.fit?X-Amz-Signature=secret")

        monkeypatch.setattr(mod, "Decoder", RaisingDecoder)

        try:
            result = decode(b"decoder-fixture")
        except RuntimeError:
            pytest.fail("decoder exception escaped the stable FIT capability boundary")

        assert result["available"] is False
        assert result["availability"] == {
            "state": "unavailable",
            "reason": "fit_decode_failed",
            "source": "fit_export",
        }
        assert result["decoder_warnings"] == [{"type": "RuntimeError"}]
        assert result["data"] == []
        serialized = str(result)
        assert "/private/leak.fit" not in serialized
        assert "X-Amz-Signature" not in serialized
        assert "secret" not in serialized
        assert "decoder-fixture" not in serialized

    def test_decoder_is_fit_exception_uses_same_safe_boundary(self, monkeypatch):
        mod = _fit_timeseries_module()
        decode = getattr(mod, "decode_fit_timeseries", None)
        assert decode is not None

        class RaisingDecoder:
            def __init__(self, stream):
                self.stream = stream

            def is_fit(self):
                raise RuntimeError("https://example.invalid/private.fit?token=secret")

        monkeypatch.setattr(mod, "Decoder", RaisingDecoder)

        try:
            result = decode(b"decoder-fixture")
        except RuntimeError:
            pytest.fail("FIT identification exception escaped the stable capability boundary")

        assert result["availability"]["state"] == "unavailable"
        assert result["availability"]["reason"] == "fit_decode_failed"
        assert result["decoder_warnings"] == [{"type": "RuntimeError"}]
        assert result["data"] == []
        assert "example.invalid" not in str(result)
        assert "secret" not in str(result)

    def test_structurally_valid_fit_without_records_is_available(self):
        mod = _fit_timeseries_module()
        decode = getattr(mod, "decode_fit_timeseries", None)
        assert decode is not None

        result = decode(Encoder().close())

        assert result["available"] is True
        assert result["availability"] == {
            "state": "available",
            "reason": "data_available",
            "source": "fit_export",
        }
        assert result["total_records"] == 0
        assert result["data"] == []

    def test_decoder_warnings_are_safe_and_mark_partial_data(self):
        mod = _fit_timeseries_module()
        normalize = getattr(mod, "normalize_fit_messages", None)
        assert normalize is not None
        messages = {
            "record_mesgs": [
                {
                    "timestamp": datetime(2026, 8, 9, 10, 31, 35, tzinfo=timezone.utc),
                    "heart_rate": 142,
                }
            ]
        }

        result = normalize(messages, decoder_warnings=[ValueError("/private/path and signed URL")])

        assert result["availability"] == {
            "state": "partial",
            "reason": "fit_decoded_with_warnings",
            "source": "fit_export",
        }
        assert result["decoder_warnings"] == [{"type": "ValueError"}]
        assert "/private/path" not in str(result)

    @pytest.mark.parametrize("offset,limit", [(-1, 1), (0, 0), (0, 1001)])
    def test_validates_paging_bounds(self, offset, limit):
        mod = _fit_timeseries_module()
        decode = getattr(mod, "decode_fit_timeseries", None)
        assert decode is not None

        with pytest.raises(ValueError, match="offset|limit"):
            decode(_encoded_fit(), offset=offset, limit=limit)
