from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import httpx
import pytest


def _load_verifier() -> ModuleType:
    script = Path(__file__).resolve().parents[1] / "scripts" / "verify_public_endpoint.py"
    spec = importlib.util.spec_from_file_location("verify_public_endpoint", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_verifier_parses_sse_json_rpc_response():
    verifier = _load_verifier()

    body = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'

    assert verifier._json_from_sse(body) == {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}


def test_public_verifier_derives_health_url_from_mcp_url():
    verifier = _load_verifier()

    assert verifier._health_url("https://mcp.example.com/mcp") == "https://mcp.example.com/healthz"


@pytest.mark.parametrize(
    "url",
    [
        "https://mcp.example.com/mcp;leaky-token",
        "https://mcp.example.com/mcp?token=leaky-token",
        "https://mcp.example.com/mcp#leaky-token",
    ],
)
def test_public_verifier_rejects_mcp_urls_with_secret_leaking_parts(url: str):
    verifier = _load_verifier()

    with pytest.raises(ValueError, match="must not include"):
        verifier._health_url(url)


def test_public_verifier_reads_bearer_token_file(tmp_path):
    verifier = _load_verifier()
    token_file = tmp_path / "token"
    token_file.write_text("\n first-token , second-token\n", encoding="utf-8")

    assert verifier._token_from_file(str(token_file)) == "first-token"


def test_public_verifier_accepts_expected_public_security_headers():
    verifier = _load_verifier()
    headers = {
        **verifier.EXPECTED_PUBLIC_SECURITY_HEADERS,
        "strict-transport-security": "max-age=31536000",
    }
    response = httpx.Response(200, headers=headers, request=httpx.Request("GET", "https://mcp.example.com/healthz"))

    verifier._verify_public_security_headers(response, expect_hsts=True)


def test_public_verifier_rejects_missing_public_security_header():
    verifier = _load_verifier()
    headers = {
        **verifier.EXPECTED_PUBLIC_SECURITY_HEADERS,
        "strict-transport-security": "max-age=31536000",
    }
    headers.pop("x-robots-tag")
    response = httpx.Response(200, headers=headers, request=httpx.Request("GET", "https://mcp.example.com/healthz"))

    try:
        verifier._verify_public_security_headers(response, expect_hsts=True)
    except RuntimeError as exc:
        assert "x-robots-tag" in str(exc)
    else:
        raise AssertionError("expected missing public security header to fail verification")


def test_public_verifier_rejects_missing_hsts_for_https():
    verifier = _load_verifier()
    response = httpx.Response(
        200,
        headers=verifier.EXPECTED_PUBLIC_SECURITY_HEADERS,
        request=httpx.Request("GET", "https://mcp.example.com/healthz"),
    )

    try:
        verifier._verify_public_security_headers(response, expect_hsts=True)
    except RuntimeError as exc:
        assert "Strict-Transport-Security" in str(exc)
    else:
        raise AssertionError("expected missing HSTS to fail HTTPS verification")


def test_public_verifier_rejects_hsts_for_http():
    verifier = _load_verifier()
    headers = {
        **verifier.EXPECTED_PUBLIC_SECURITY_HEADERS,
        "strict-transport-security": "max-age=31536000",
    }
    response = httpx.Response(200, headers=headers, request=httpx.Request("GET", "http://localhost:8000/healthz"))

    try:
        verifier._verify_public_security_headers(response, expect_hsts=False)
    except RuntimeError as exc:
        assert "non-HTTPS" in str(exc)
    else:
        raise AssertionError("expected HSTS on HTTP to fail verification")


def test_public_verifier_checks_all_default_public_disabled_tools():
    verifier = _load_verifier()

    expected = {
        "tw_delete_activity",
        "tw_export_activity_strap_files",
        "tw_export_csv",
        "tw_export_csv_full",
        "tw_export_fit",
        "tw_get_activity_logs",
        "tw_get_activity_strap_files",
        "tw_get_new_processed_data",
        "tw_get_processed_data",
        "tw_pin_activity",
        "tw_respond_max_value",
        "tw_tag_new_zone",
        "tw_tag_threshold",
        "tw_update_profile",
    }

    assert expected == verifier.PUBLIC_DISABLED_TOOL_NAMES
    assert verifier._exposed_disabled_public_tools(expected | {"tw_get_profile"}) == sorted(expected)


def test_public_verifier_requires_compact_analysis_and_profile_tools():
    verifier = _load_verifier()

    assert {"tw_get_activity_analysis", "tw_get_profile"} == verifier.REQUIRED_PUBLIC_TOOL_NAMES
    assert verifier._missing_required_public_tools({"tw_get_profile"}) == ["tw_get_activity_analysis"]
    assert verifier._missing_required_public_tools(verifier.REQUIRED_PUBLIC_TOOL_NAMES) == []
