"""Tests for tw_auth_status tool."""

from unittest.mock import AsyncMock

from tymewear_mcp.tools.auth_status import auth_status


class TestAuthStatus:
    async def test_returns_authenticated_when_token_valid(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"id": 1, "email": "a@b.com"})
        mock_client.sanitize = lambda d: {k: v for k, v in d.items() if k != "email"}

        result = await auth_status(mock_client)
        assert result["status"] == "authenticated"

    async def test_returns_error_when_auth_fails(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("connection failed"))

        result = await auth_status(mock_client)
        assert result["status"] == "error"
        assert result["message"] == "Authentication failed"
