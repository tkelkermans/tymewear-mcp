from __future__ import annotations

import httpx
import pytest

from tymewear_mcp.tools import _availability
from tymewear_mcp.tools._availability import feature_unavailable, unavailable_from_http_error


@pytest.mark.parametrize(
    ("state", "available"),
    [
        ("available", True),
        ("partial", True),
        ("not_applicable", False),
        ("not_computed", False),
        ("sync_pending", False),
        ("unavailable", False),
        ("permission_denied", False),
    ],
)
def test_availability_envelope_supports_each_stable_state(state, available):
    result = _availability.availability_envelope(
        state=state,
        reason="stable_reason",
        source="processed_data",
    )

    assert result == {
        "availability": {
            "state": state,
            "reason": "stable_reason",
            "source": "processed_data",
        },
        "available": available,
    }


def test_feature_available_uses_tagged_envelope():
    result = _availability.feature_available(source="processed_data")

    assert result == {
        "availability": {
            "state": "available",
            "reason": "data_available",
            "source": "processed_data",
        },
        "available": True,
    }


def test_feature_unavailable_uses_tagged_envelope_and_legacy_keys():
    result = feature_unavailable(
        "raw_data_access_disabled",
        403,
        "Private upstream explanation",
        source="strap_files",
    )

    assert result == {
        "availability": {
            "state": "permission_denied",
            "reason": "raw_data_access_disabled",
            "source": "strap_files",
            "http_status": 403,
        },
        "available": False,
        "reason": "raw_data_access_disabled",
        "status_code": 403,
    }


def test_unavailable_from_403_response():
    request = httpx.Request("GET", "https://api.tymewear.com/v2/api/activities/abc/strap-files/")
    response = httpx.Response(403, json={"detail": "Forbidden"}, request=request)
    error = httpx.HTTPStatusError("Forbidden", request=request, response=response)

    result = unavailable_from_http_error(
        error,
        default_reason="feature_not_available",
        source="processed_data",
    )

    assert result["available"] is False
    assert result["reason"] == "feature_not_available"
    assert result["status_code"] == 403
    assert result["availability"] == {
        "state": "permission_denied",
        "reason": "feature_not_available",
        "source": "processed_data",
        "http_status": 403,
    }
    assert "detail" not in result
    assert "Forbidden" not in repr(result)


def test_unavailable_from_404_response():
    request = httpx.Request("GET", "https://api.tymewear.com/v2/api/activities/abc/workout-zone-detection/")
    response = httpx.Response(404, json={"detail": "Not found."}, request=request)
    error = httpx.HTTPStatusError("Not found", request=request, response=response)

    result = unavailable_from_http_error(error, default_reason="not_found", source="processed_data")

    assert result["reason"] == "not_found"
    assert result["status_code"] == 404
    assert result["availability"] == {
        "state": "unavailable",
        "reason": "not_found",
        "source": "processed_data",
        "http_status": 404,
    }
    assert "detail" not in result
