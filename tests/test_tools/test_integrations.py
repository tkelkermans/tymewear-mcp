from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from tymewear_mcp.tools._validation import IntegrationInput
from tymewear_mcp.tools.integrations import get_integration, get_integration_health, get_integrations


def test_integration_input_accepts_slug() -> None:
    params = IntegrationInput.model_validate({"integration_id": "garmin"})
    assert params.integration_id == "garmin"


@pytest.mark.parametrize("integration_id", ["", "garmin/health"])
def test_integration_input_rejects_invalid_id(integration_id: str) -> None:
    with pytest.raises(ValidationError):
        IntegrationInput.model_validate({"integration_id": integration_id})


async def test_get_integrations() -> None:
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=[{"slug": "garmin", "token": "secret"}])
    mock_client.sanitize = lambda data: [{"slug": item["slug"]} for item in data]

    result = await get_integrations(mock_client)

    mock_client.get.assert_called_once_with("/v2/api/integrations/")
    assert result == {"available": True, "data": [{"slug": "garmin"}]}


async def test_get_integrations_payload_cannot_override_availability() -> None:
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value={"available": False, "slug": "garmin"})
    mock_client.sanitize = lambda data: data

    result = await get_integrations(mock_client)

    assert result == {"available": True, "slug": "garmin"}


async def test_get_integration_detail() -> None:
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value={"slug": "garmin", "token": "secret"})
    mock_client.sanitize = lambda data: {"slug": data["slug"]}

    result = await get_integration(mock_client, "garmin")

    mock_client.get.assert_called_once_with("/v2/api/integrations/garmin/")
    assert result == {"available": True, "slug": "garmin"}


async def test_get_integration_404() -> None:
    request = httpx.Request("GET", "https://api.tymewear.com/v2/api/integrations/garmin/")
    response = httpx.Response(404, json={"detail": "Not found"}, request=request)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError("Not found", request=request, response=response))

    result = await get_integration(mock_client, "garmin")

    assert result["available"] is False
    assert result["reason"] == "not_found"


async def test_get_integration_403() -> None:
    request = httpx.Request("GET", "https://api.tymewear.com/v2/api/integrations/garmin/")
    response = httpx.Response(403, json={"detail": "Upgrade required"}, request=request)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError("Forbidden", request=request, response=response))

    result = await get_integration(mock_client, "garmin")

    assert result["available"] is False
    assert result["reason"] == "feature_not_available"


def _assert_unreported_operational_capabilities(result: dict[str, object]) -> None:
    capabilities = result["capabilities"]
    assert isinstance(capabilities, dict)
    assert capabilities == {
        "sync_history": {
            "state": "unavailable",
            "reason": "sync_history_not_reported",
            "source": "integration_health",
        },
        "replay": {
            "state": "not_applicable",
            "reason": "replay_not_supported",
            "source": "integration_health",
        },
        "last_success_history": {
            "state": "unavailable",
            "reason": "last_success_history_not_reported",
            "source": "integration_health",
        },
        "cursor_watermark": {
            "state": "unavailable",
            "reason": "cursor_watermark_not_reported",
            "source": "integration_health",
        },
        "backlog": {
            "state": "unavailable",
            "reason": "backlog_not_reported",
            "source": "integration_health",
        },
        "failed_items": {
            "state": "unavailable",
            "reason": "failed_items_not_reported",
            "source": "integration_health",
        },
        "retries": {
            "state": "unavailable",
            "reason": "retries_not_reported",
            "source": "integration_health",
        },
        "next_retry": {
            "state": "unavailable",
            "reason": "next_retry_not_reported",
            "source": "integration_health",
        },
    }


async def test_get_integration_health_normalizes_explicit_current_green_state() -> None:
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value={
            "status": "healthy",
            "connected": True,
            "authenticated": True,
            "checked_at": "2026-08-09T10:45:00Z",
            "error": None,
            "token": "secret",
        }
    )
    mock_client.sanitize = lambda data: {key: value for key, value in data.items() if key != "token"}
    mock_client.post.side_effect = AssertionError("mutation POST is unsupported")
    mock_client.patch.side_effect = AssertionError("mutation PATCH is unsupported")
    mock_client.delete.side_effect = AssertionError("mutation DELETE is unsupported")

    result = await get_integration_health(mock_client, "garmin")

    mock_client.get.assert_called_once_with("/v2/api/integrations/garmin/health/")
    assert result["integration_id"] == "garmin"
    assert result["availability"] == {
        "state": "available",
        "reason": "current_snapshot_available",
        "source": "integration_health",
    }
    assert result["connection_state"] == "connected"
    assert result["auth_state"] == "authenticated"
    assert result["ingestion_state"] == "healthy"
    assert result["checked"] == {
        "availability": {
            "state": "available",
            "reason": "current_check_reported",
            "source": "integration_health.checked_at",
        },
        "value": "2026-08-09T10:45:00Z",
    }
    assert result["error"] == {
        "availability": {
            "state": "available",
            "reason": "no_current_error",
            "source": "integration_health.error",
        },
        "present": False,
    }
    _assert_unreported_operational_capabilities(result)
    mock_client.post.assert_not_awaited()
    mock_client.patch.assert_not_awaited()
    mock_client.delete.assert_not_awaited()


async def test_get_integration_health_normalizes_observed_august9_shape_without_inventing_auth() -> None:
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value={"is_connected": True, "is_healthy": True, "error": None})
    mock_client.sanitize = lambda data: data

    result = await get_integration_health(mock_client, "garmin")

    assert result["availability"] == {
        "state": "partial",
        "reason": "current_snapshot_incomplete",
        "source": "integration_health",
    }
    assert result["connection_state"] == "connected"
    assert result["auth_state"] == "unknown"
    assert result["ingestion_state"] == "healthy"
    assert result["error"]["present"] is False


@pytest.mark.parametrize("checked_at", [float("nan"), float("inf"), float("-inf")])
async def test_get_integration_health_rejects_nonfinite_numeric_check_time(checked_at: float) -> None:
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value={
            "connected": True,
            "authenticated": True,
            "status": "healthy",
            "checked_at": checked_at,
            "error": None,
        }
    )
    mock_client.sanitize = lambda data: data

    result = await get_integration_health(mock_client, "garmin")

    assert result["checked"] == {
        "availability": {
            "state": "unavailable",
            "reason": "current_check_invalid",
            "source": "integration_health.checked_at",
        }
    }
    assert "nan" not in repr(result).casefold()
    assert "inf" not in repr(result).casefold()


async def test_get_integration_health_reports_current_error_without_raw_text_or_recovery_history() -> None:
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value={
            "connected": True,
            "auth_status": "expired",
            "ingestion_state": "failed",
            "last_checked_at": "2026-08-09T10:46:00Z",
            "error_code": "AUTH_EXPIRED",
            "last_error": "private callback https://example.test/callback?token=secret",
        }
    )
    mock_client.sanitize = lambda data: data

    result = await get_integration_health(mock_client, "garmin")

    assert result["availability"]["state"] == "partial"
    assert result["connection_state"] == "connected"
    assert result["auth_state"] == "expired"
    assert result["ingestion_state"] == "error"
    assert result["checked"]["value"] == "2026-08-09T10:46:00Z"
    assert result["error"] == {
        "availability": {
            "state": "available",
            "reason": "current_error_reported",
            "source": "integration_health.error",
        },
        "present": True,
        "code": "AUTH_EXPIRED",
    }
    assert "callback" not in repr(result)
    assert "token=secret" not in repr(result)
    _assert_unreported_operational_capabilities(result)


async def test_get_integration_health_contains_nested_errors_and_malicious_checked_fields() -> None:
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value={
            "connected": True,
            "authenticated": True,
            "status": "healthy",
            "checked_at": "https://example.test/private?token=secret",
            "error": {"detail": "nested /private/path?token=secret"},
            "last_error": ["another secret"],
            "error_code": "TOKEN_secret_callback",
        }
    )
    mock_client.sanitize = lambda data: data

    result = await get_integration_health(mock_client, "garmin")

    assert result["checked"] == {
        "availability": {
            "state": "unavailable",
            "reason": "current_check_invalid",
            "source": "integration_health.checked_at",
        }
    }
    assert result["error"] == {
        "availability": {
            "state": "available",
            "reason": "current_error_reported",
            "source": "integration_health.error",
        },
        "present": True,
    }
    serialized = repr(result)
    assert "example.test" not in serialized
    assert "/private/path" not in serialized
    assert "TOKEN_secret_callback" not in serialized
    assert "another secret" not in serialized


async def test_get_integration_health_keeps_omitted_current_fields_unknown() -> None:
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value={})
    mock_client.sanitize = lambda data: data

    result = await get_integration_health(mock_client, "garmin")

    assert result["availability"] == {
        "state": "partial",
        "reason": "current_snapshot_incomplete",
        "source": "integration_health",
    }
    assert result["connection_state"] == "unknown"
    assert result["auth_state"] == "unknown"
    assert result["ingestion_state"] == "unknown"
    assert result["checked"]["availability"]["reason"] == "current_check_not_reported"
    assert result["error"]["availability"]["reason"] == "current_error_not_reported"
    _assert_unreported_operational_capabilities(result)


async def test_get_integration_health_404() -> None:
    request = httpx.Request("GET", "https://api.tymewear.com/v2/api/integrations/garmin/health/")
    response = httpx.Response(404, json={"detail": "Not configured"}, request=request)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError("Not configured", request=request, response=response))

    result = await get_integration_health(mock_client, "garmin")

    assert result["available"] is False
    assert result["availability"] == {
        "state": "unavailable",
        "reason": "integration_not_configured",
        "source": "integration_health",
        "http_status": 404,
    }
    assert result["connection_state"] == "unknown"
    assert result["auth_state"] == "unknown"
    assert result["ingestion_state"] == "unknown"
    _assert_unreported_operational_capabilities(result)


async def test_get_integration_health_403() -> None:
    request = httpx.Request("GET", "https://api.tymewear.com/v2/api/integrations/garmin/health/")
    response = httpx.Response(403, json={"detail": "Upgrade required"}, request=request)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError("Forbidden", request=request, response=response))

    result = await get_integration_health(mock_client, "garmin")

    assert result["available"] is False
    assert result["availability"] == {
        "state": "permission_denied",
        "reason": "feature_not_available",
        "source": "integration_health",
        "http_status": 403,
    }
    assert result["connection_state"] == "unknown"
    _assert_unreported_operational_capabilities(result)


async def test_get_integration_health_unexpected_http_status_is_stable_partial_snapshot() -> None:
    request = httpx.Request("GET", "https://api.tymewear.com/v2/api/integrations/garmin/health/")
    response = httpx.Response(500, json={"detail": "Server error"}, request=request)
    error = httpx.HTTPStatusError("Server error /private?token=secret", request=request, response=response)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=error)

    result = await get_integration_health(mock_client, "garmin")

    assert result["available"] is False
    assert result["availability"] == {
        "state": "unavailable",
        "reason": "integration_health_request_failed",
        "source": "integration_health",
        "http_status": 500,
    }
    assert "Server error" not in repr(result)
    assert "token=secret" not in repr(result)
    _assert_unreported_operational_capabilities(result)
