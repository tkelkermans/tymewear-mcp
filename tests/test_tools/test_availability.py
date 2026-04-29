from __future__ import annotations

import httpx

from tymewear_mcp.tools._availability import feature_unavailable, unavailable_from_http_error


def test_feature_unavailable_shape():
    result = feature_unavailable("raw_data_access_disabled", 403, "Raw data is disabled")

    assert result == {
        "available": False,
        "reason": "raw_data_access_disabled",
        "status_code": 403,
        "detail": "Raw data is disabled",
    }


def test_unavailable_from_403_response():
    request = httpx.Request("GET", "https://api.tymewear.com/v2/api/activities/abc/strap-files/")
    response = httpx.Response(403, json={"detail": "Forbidden"}, request=request)
    error = httpx.HTTPStatusError("Forbidden", request=request, response=response)

    result = unavailable_from_http_error(error, default_reason="feature_not_available")

    assert result["available"] is False
    assert result["reason"] == "feature_not_available"
    assert result["status_code"] == 403
    assert result["detail"] == "Forbidden"


def test_unavailable_from_404_response():
    request = httpx.Request("GET", "https://api.tymewear.com/v2/api/activities/abc/workout-zone-detection/")
    response = httpx.Response(404, json={"detail": "Not found."}, request=request)
    error = httpx.HTTPStatusError("Not found", request=request, response=response)

    result = unavailable_from_http_error(error, default_reason="not_found")

    assert result["reason"] == "not_found"
    assert result["status_code"] == 404
    assert result["detail"] == "Not found."
