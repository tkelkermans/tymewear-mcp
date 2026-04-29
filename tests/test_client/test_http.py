"""Tests for TymeClient async HTTP wrapper."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from tymewear_mcp.client.http import TymeClient


@pytest.fixture
def mock_credentials():
    return {"email": "test@example.com", "password": "testpass"}


class TestTymeClient:
    async def test_authenticates_on_first_request(self, mock_credentials):
        client = TymeClient(credentials=mock_credentials)
        signin_response = httpx.Response(200, json={"token": "abc123"})

        with patch.object(client, "_http") as mock_http:
            mock_http.post = AsyncMock(return_value=signin_response)
            await client._ensure_token()
            mock_http.post.assert_called_once()
            call_args = mock_http.post.call_args
            assert "/api/session/signin/" in str(call_args)

        await client.close()

    async def test_get_includes_auth_header(self, mock_credentials):
        client = TymeClient(credentials=mock_credentials)
        client._token = "mytoken"

        api_response = httpx.Response(200, json={"id": 1})
        with patch.object(client, "_http") as mock_http:
            mock_http.get = AsyncMock(return_value=api_response)
            result = await client.get("/v2/api/profile/")
            call_kwargs = mock_http.get.call_args[1]
            assert call_kwargs["headers"]["Authorization"] == "Token mytoken"
            assert call_kwargs["headers"]["X-Source"] == "v2"

        await client.close()

    async def test_reauth_on_401(self, mock_credentials):
        client = TymeClient(credentials=mock_credentials)
        client._token = "expired_token"

        resp_401 = httpx.Response(401, json={"detail": "Invalid token"})
        resp_ok = httpx.Response(200, json={"id": 1})
        signin_resp = httpx.Response(200, json={"token": "newtoken"})

        call_count = 0

        async def mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return resp_401
            return resp_ok

        with patch.object(client, "_http") as mock_http:
            mock_http.get = AsyncMock(side_effect=mock_get)
            mock_http.post = AsyncMock(return_value=signin_resp)
            result = await client.get("/v2/api/profile/")
            assert result == {"id": 1}
            assert client._token == "newtoken"

        await client.close()

    async def test_sanitize_result(self, mock_credentials):
        client = TymeClient(credentials=mock_credentials)
        data = {"id": 1, "token": "secret", "password": "hidden", "name": "visible"}
        sanitized = client.sanitize(data)
        assert "token" not in sanitized
        assert "password" not in sanitized
        assert sanitized["name"] == "visible"
        assert sanitized["id"] == 1
        await client.close()

    async def test_rate_limiting(self, mock_credentials):
        import time

        client = TymeClient(credentials=mock_credentials)
        client._token = "tok"

        resp = httpx.Response(200, json={"ok": True})
        with patch.object(client, "_http") as mock_http:
            mock_http.get = AsyncMock(return_value=resp)

            start = time.monotonic()
            await client.get("/a/")
            await client.get("/b/")
            elapsed = time.monotonic() - start
            assert elapsed >= 0.1

        await client.close()


async def test_get_raw_returns_response():
    client = TymeClient({"email": "test@example.com", "password": "secret"})
    client._token = "token"
    raw_response = httpx.Response(200, content=b"fit-bytes")

    with patch.object(client, "_http") as mock_http:
        mock_http.get = AsyncMock(return_value=raw_response)
        result = await client.get_raw("/api/activities/abc/fit/")

    assert result is raw_response
    mock_http.get.assert_called_once()

    await client.close()
