from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext
from starlette.requests import Request

from tymewear_mcp import public as public_mod
from tymewear_mcp import server as server_mod
from tymewear_mcp.public import PublicServerConfig, StaticBearerTokenVerifier, build_public_app

TEST_BEARER_TOKEN = "test-public-bearer-token-32-chars"
TEST_AUTHORIZATION = f"Bearer {TEST_BEARER_TOKEN}"


def _request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (name.lower().encode("ascii"), value.encode("ascii"))
        for name, value in (headers or {}).items()
    ]
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": raw_headers,
        "scheme": "https",
        "server": ("mcp.example.com", 443),
        "client": ("203.0.113.10", 50000),
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def reset_public_mode():
    server_mod.disable_public_mode()
    yield
    server_mod.disable_public_mode()


@pytest.fixture
def public_mode(monkeypatch):
    monkeypatch.setattr(server_mod, "_public_mode", True)
    monkeypatch.setattr(server_mod, "_client", None)
    yield
    monkeypatch.setattr(server_mod, "_public_mode", False)


def _set_request_context(request: Request):
    return request_ctx.set(
        RequestContext(
            request_id="test-request",
            meta=None,
            session=object(),
            lifespan_context={},
            request=request,
        )
    )


def _assert_public_security_headers(response: httpx.Response, *, hsts: bool = True) -> None:
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    if hsts:
        assert response.headers["strict-transport-security"] == "max-age=31536000"
    else:
        assert "strict-transport-security" not in response.headers


def test_public_config_requires_bearer_tokens():
    with pytest.raises(ValueError, match="TYMEWEAR_PUBLIC_BEARER_TOKENS"):
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp",
            bearer_tokens=[],
            allowed_hosts=["mcp.example.com"],
            allowed_origins=["https://mcp.example.com"],
        )


def test_public_config_rejects_short_bearer_tokens():
    with pytest.raises(ValueError, match="at least 32 characters"):
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp",
            bearer_tokens=["short-token"],
            allowed_hosts=["mcp.example.com"],
            allowed_origins=["https://mcp.example.com"],
        )


def test_public_config_derives_public_url_from_vercel_env():
    config = PublicServerConfig.from_env(
        {
            "VERCEL_URL": "tymewear-mcp-public-abc.vercel.app",
            "TYMEWEAR_PUBLIC_BEARER_TOKENS": TEST_BEARER_TOKEN,
        }
    )

    assert config.public_url == "https://tymewear-mcp-public-abc.vercel.app/mcp"
    assert config.allowed_hosts == ["tymewear-mcp-public-abc.vercel.app"]
    assert config.allowed_origins == ["https://tymewear-mcp-public-abc.vercel.app"]


def test_public_config_rejects_public_url_query_fragment_and_path_mismatch():
    with pytest.raises(ValueError, match="must not include params, query strings, or fragments"):
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp?token=leak",
            bearer_tokens=[TEST_BEARER_TOKEN],
            allowed_hosts=["mcp.example.com"],
            allowed_origins=["https://mcp.example.com"],
        )

    with pytest.raises(ValueError, match="path must match"):
        PublicServerConfig(
            public_url="https://mcp.example.com/not-mcp",
            bearer_tokens=[TEST_BEARER_TOKEN],
            allowed_hosts=["mcp.example.com"],
            allowed_origins=["https://mcp.example.com"],
        )


def test_public_config_rejects_invalid_mcp_path():
    with pytest.raises(ValueError, match="mcp_path"):
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp",
            bearer_tokens=[TEST_BEARER_TOKEN],
            allowed_hosts=["mcp.example.com"],
            allowed_origins=["https://mcp.example.com"],
            mcp_path="mcp",
        )

    with pytest.raises(ValueError, match="query strings"):
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp",
            bearer_tokens=[TEST_BEARER_TOKEN],
            allowed_hosts=["mcp.example.com"],
            allowed_origins=["https://mcp.example.com"],
            mcp_path="/mcp?debug=true",
        )


def test_public_config_defaults_to_read_only_and_accepts_mutation_opt_in():
    default_config = PublicServerConfig.from_env(
        {
            "VERCEL_URL": "tymewear-mcp-public-abc.vercel.app",
            "TYMEWEAR_PUBLIC_BEARER_TOKENS": TEST_BEARER_TOKEN,
        }
    )
    env_config = PublicServerConfig.from_env(
        {
            "VERCEL_URL": "tymewear-mcp-public-abc.vercel.app",
            "TYMEWEAR_PUBLIC_BEARER_TOKENS": TEST_BEARER_TOKEN,
            "TYMEWEAR_PUBLIC_ALLOW_MUTATIONS": "true",
        }
    )
    explicit_config = PublicServerConfig.from_env(
        {
            "VERCEL_URL": "tymewear-mcp-public-abc.vercel.app",
            "TYMEWEAR_PUBLIC_BEARER_TOKENS": TEST_BEARER_TOKEN,
            "TYMEWEAR_PUBLIC_ALLOW_MUTATIONS": "false",
        },
        allow_mutations=True,
    )

    assert default_config.allow_mutations is False
    assert env_config.allow_mutations is True
    assert explicit_config.allow_mutations is True


def test_public_config_reads_max_body_bytes_from_env():
    config = PublicServerConfig.from_env(
        {
            "VERCEL_URL": "tymewear-mcp-public-abc.vercel.app",
            "TYMEWEAR_PUBLIC_BEARER_TOKENS": TEST_BEARER_TOKEN,
            "TYMEWEAR_PUBLIC_MAX_BODY_BYTES": "2048",
        }
    )

    assert config.max_body_bytes == 2048


def test_public_config_rejects_invalid_max_body_bytes_env():
    with pytest.raises(ValueError, match="TYMEWEAR_PUBLIC_MAX_BODY_BYTES"):
        PublicServerConfig.from_env(
            {
                "VERCEL_URL": "tymewear-mcp-public-abc.vercel.app",
                "TYMEWEAR_PUBLIC_BEARER_TOKENS": TEST_BEARER_TOKEN,
                "TYMEWEAR_PUBLIC_MAX_BODY_BYTES": "0",
            }
        )


def test_public_config_rejects_wildcard_allowed_hosts_and_origins():
    with pytest.raises(ValueError, match="TYMEWEAR_PUBLIC_ALLOWED_HOSTS"):
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp",
            bearer_tokens=[TEST_BEARER_TOKEN],
            allowed_hosts=["*"],
            allowed_origins=["https://mcp.example.com"],
        )

    with pytest.raises(ValueError, match="TYMEWEAR_PUBLIC_ALLOWED_ORIGINS"):
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp",
            bearer_tokens=[TEST_BEARER_TOKEN],
            allowed_hosts=["mcp.example.com"],
            allowed_origins=["*"],
        )


def test_public_config_rejects_malformed_allowed_hosts_and_origins():
    with pytest.raises(ValueError, match="TYMEWEAR_PUBLIC_ALLOWED_HOSTS"):
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp",
            bearer_tokens=[TEST_BEARER_TOKEN],
            allowed_hosts=["https://mcp.example.com"],
            allowed_origins=["https://mcp.example.com"],
        )

    with pytest.raises(ValueError, match="TYMEWEAR_PUBLIC_ALLOWED_HOSTS"):
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp",
            bearer_tokens=[TEST_BEARER_TOKEN],
            allowed_hosts=["mcp.example.com/path"],
            allowed_origins=["https://mcp.example.com"],
        )

    with pytest.raises(ValueError, match="TYMEWEAR_PUBLIC_ALLOWED_ORIGINS"):
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp",
            bearer_tokens=[TEST_BEARER_TOKEN],
            allowed_hosts=["mcp.example.com"],
            allowed_origins=["mcp.example.com"],
        )

    with pytest.raises(ValueError, match="TYMEWEAR_PUBLIC_ALLOWED_ORIGINS"):
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp",
            bearer_tokens=[TEST_BEARER_TOKEN],
            allowed_hosts=["mcp.example.com"],
            allowed_origins=["https://*.example.com"],
        )

    with pytest.raises(ValueError, match="TYMEWEAR_PUBLIC_ALLOWED_ORIGINS"):
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp",
            bearer_tokens=[TEST_BEARER_TOKEN],
            allowed_hosts=["mcp.example.com"],
            allowed_origins=["https://mcp.example.com/path"],
        )


def test_public_config_accepts_explicit_host_pattern_and_localhost_origin():
    config = PublicServerConfig(
        public_url="https://mcp.example.com/mcp",
        bearer_tokens=[TEST_BEARER_TOKEN],
        allowed_hosts=["*.example.com", "localhost:*"],
        allowed_origins=["https://mcp.example.com", "http://localhost:8000"],
    )

    assert config.allowed_hosts == ["*.example.com", "localhost:*"]
    assert config.allowed_origins == ["https://mcp.example.com", "http://localhost:8000"]


async def test_static_bearer_verifier_accepts_configured_token():
    fallback_token = "fallback-public-bearer-token-32x"
    verifier = StaticBearerTokenVerifier(
        bearer_tokens=[fallback_token, TEST_BEARER_TOKEN],
        resource_url="https://mcp.example.com/mcp",
        scopes=["tymewear:mcp"],
    )

    accepted = await verifier.verify_token(TEST_BEARER_TOKEN)
    rejected = await verifier.verify_token("wrong-token")

    assert accepted is not None
    assert accepted.client_id == "tymewear-public-client"
    assert accepted.scopes == ["tymewear:mcp"]
    assert accepted.resource == "https://mcp.example.com/mcp"
    assert rejected is None


async def test_public_app_health_is_public():
    app = build_public_app(
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp",
            bearer_tokens=[TEST_BEARER_TOKEN],
            allowed_hosts=["mcp.example.com"],
            allowed_origins=["https://mcp.example.com"],
        )
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://mcp.example.com") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    _assert_public_security_headers(response)


async def test_public_app_allows_localhost_public_url_with_port():
    app = build_public_app(
        PublicServerConfig(
            public_url="http://localhost:8000/mcp",
            bearer_tokens=[TEST_BEARER_TOKEN],
        )
    )

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000") as client:
            health = await client.get("/healthz")
            mcp = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "test-client", "version": "1.0.0"},
                    },
                },
                headers={
                    "Authorization": TEST_AUTHORIZATION,
                    "Accept": "application/json, text/event-stream",
                },
            )

    assert health.status_code == 200
    assert mcp.status_code == 200
    _assert_public_security_headers(health, hsts=False)


async def test_public_app_rejects_untrusted_host_for_health_and_mcp():
    app = build_public_app(
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp",
            bearer_tokens=[TEST_BEARER_TOKEN],
            allowed_hosts=["mcp.example.com"],
            allowed_origins=["https://mcp.example.com"],
        )
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://evil.example.net") as client:
        health = await client.get("/healthz")
        mcp = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={
                "Authorization": TEST_AUTHORIZATION,
                "Accept": "application/json, text/event-stream",
            },
        )

    assert health.status_code == 400
    assert mcp.status_code == 400
    _assert_public_security_headers(health)
    _assert_public_security_headers(mcp)


async def test_public_app_rejects_untrusted_origin_and_accepts_allowed_origin():
    app = build_public_app(
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp",
            bearer_tokens=[TEST_BEARER_TOKEN],
            allowed_hosts=["mcp.example.com"],
            allowed_origins=["https://mcp.example.com"],
        )
    )
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
    }

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://mcp.example.com") as client:
            rejected = await client.post(
                "/mcp",
                json=payload,
                headers={
                    "Authorization": TEST_AUTHORIZATION,
                    "Accept": "application/json, text/event-stream",
                    "Origin": "https://evil.example.net",
                },
            )
            accepted = await client.post(
                "/mcp",
                json=payload,
                headers={
                    "Authorization": TEST_AUTHORIZATION,
                    "Accept": "application/json, text/event-stream",
                    "Origin": "https://mcp.example.com",
                },
            )

    assert rejected.status_code == 403
    assert accepted.status_code == 200
    _assert_public_security_headers(rejected)
    _assert_public_security_headers(accepted)


async def test_public_app_rejects_mcp_request_without_bearer_token():
    app = build_public_app(
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp",
            bearer_tokens=[TEST_BEARER_TOKEN],
            allowed_hosts=["mcp.example.com"],
            allowed_origins=["https://mcp.example.com"],
        )
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://mcp.example.com") as client:
        response = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Bearer")
    _assert_public_security_headers(response)


async def test_public_app_rejects_oversized_mcp_request_body():
    app = build_public_app(
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp",
            bearer_tokens=[TEST_BEARER_TOKEN],
            allowed_hosts=["mcp.example.com"],
            allowed_origins=["https://mcp.example.com"],
            max_body_bytes=16,
        )
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://mcp.example.com") as client:
        response = await client.post(
            "/mcp",
            content=b"x" * 17,
            headers={
                "Authorization": TEST_AUTHORIZATION,
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
        )

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large."}
    _assert_public_security_headers(response)


async def test_public_app_rejects_oversized_streaming_mcp_request_body():
    app = build_public_app(
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp",
            bearer_tokens=[TEST_BEARER_TOKEN],
            allowed_hosts=["mcp.example.com"],
            allowed_origins=["https://mcp.example.com"],
            max_body_bytes=16,
        )
    )

    async def body_stream():
        yield b"x" * 8
        yield b"x" * 9

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://mcp.example.com") as client:
            response = await client.post(
                "/mcp",
                content=body_stream(),
                headers={
                    "Authorization": TEST_AUTHORIZATION,
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                },
            )

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large."}
    _assert_public_security_headers(response)


async def test_public_app_accepts_authenticated_initialize_request():
    app = build_public_app(
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp",
            bearer_tokens=[TEST_BEARER_TOKEN],
            allowed_hosts=["mcp.example.com"],
            allowed_origins=["https://mcp.example.com"],
            json_response=True,
        )
    )
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
    }

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://mcp.example.com") as client:
            response = await client.post(
                "/mcp",
                json=payload,
                headers={
                    "Authorization": TEST_AUTHORIZATION,
                    "Accept": "application/json, text/event-stream",
                },
            )

    assert response.status_code == 200
    _assert_public_security_headers(response)
    body = response.json()
    assert body["result"]["serverInfo"]["name"] == "tymewear-mcp"
    assert body["result"]["protocolVersion"] == "2025-06-18"


async def test_public_app_advertises_resource_metadata_when_issuer_is_configured():
    app = build_public_app(
        PublicServerConfig(
            public_url="https://mcp.example.com/mcp",
            issuer_url="https://auth.example.com",
            allowed_emails=["coach@example.com"],
            bearer_tokens=[TEST_BEARER_TOKEN],
            allowed_hosts=["mcp.example.com"],
            allowed_origins=["https://mcp.example.com"],
        )
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://mcp.example.com") as client:
        unauthorized = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        metadata = await client.get("/.well-known/oauth-protected-resource/mcp")

    assert unauthorized.status_code == 401
    assert 'resource_metadata="https://mcp.example.com/.well-known/oauth-protected-resource/mcp"' in (
        unauthorized.headers["www-authenticate"]
    )
    assert metadata.status_code == 200
    assert metadata.json()["resource"] == "https://mcp.example.com/mcp"
    assert metadata.json()["authorization_servers"] == ["https://auth.example.com/"]


async def test_public_mode_list_tools_hides_exports_and_mutations_by_default(public_mode):
    tools = await server_mod.list_tools()
    names = {tool.name for tool in tools}

    assert "tw_get_profile" in names
    assert "tw_update_profile" not in names
    assert "tw_delete_activity" not in names
    assert "tw_export_csv" not in names
    assert "tw_get_processed_data" not in names
    assert "tw_get_new_processed_data" not in names
    assert "tw_get_activity_logs" not in names
    assert "tw_get_activity_strap_files" not in names
    assert "tw_get_activity_analysis" in names
    assert "tw_get_activity_workout_zone_detection" in names


async def test_public_mode_list_tools_can_expose_mutations_when_explicitly_enabled(monkeypatch):
    monkeypatch.setattr(server_mod, "_public_mode", True)
    monkeypatch.setattr(server_mod, "_public_allow_mutations", True)

    tools = await server_mod.list_tools()
    names = {tool.name for tool in tools}

    assert "tw_update_profile" in names
    assert "tw_delete_activity" in names
    assert "tw_export_csv" not in names
    assert "tw_get_processed_data" not in names
    assert "tw_get_new_processed_data" not in names
    assert "tw_get_activity_logs" not in names
    assert "tw_get_activity_strap_files" not in names
    assert "tw_get_activity_analysis" in names
    assert "tw_get_activity_workout_zone_detection" in names


async def test_public_mode_disables_disk_export_tools(public_mode, monkeypatch):
    export_csv = AsyncMock(side_effect=AssertionError("public mode must not call disk export implementation"))
    monkeypatch.setattr(server_mod.exports_mod, "export_csv", export_csv)
    storage = AsyncMock(side_effect=AssertionError("public mode must not load local credentials"))
    monkeypatch.setattr(server_mod, "CredentialStorage", storage)
    token = _set_request_context(_request({"X-Tymewear-Token": "upstream-token"}))

    try:
        result = await server_mod.call_tool("tw_export_csv", {"activity_id": "activity-123"})
    finally:
        request_ctx.reset(token)

    payload = json.loads(result[0].text)
    assert payload == {
        "isError": True,
        "error_code": "PUBLIC_EXPORTS_DISABLED",
        "message": "File export tools are disabled in public mode because they would persist end-customer data.",
    }
    export_csv.assert_not_called()
    storage.assert_not_called()


@pytest.mark.parametrize(
    "tool_name",
    [
        "tw_get_processed_data",
        "tw_get_new_processed_data",
        "tw_get_activity_logs",
        "tw_get_activity_strap_files",
    ],
)
async def test_public_mode_disables_raw_activity_reads_before_client_construction(
    public_mode, monkeypatch, tool_name
):
    get_client = AsyncMock(side_effect=AssertionError("disabled public tools must fail before client construction"))
    monkeypatch.setattr(server_mod, "_get_client", get_client)

    result = await server_mod.call_tool(tool_name, {"activity_id": "activity-123"})

    assert json.loads(result[0].text) == {
        "isError": True,
        "error_code": "PUBLIC_RAW_DATA_DISABLED",
        "message": (
            "Raw activity data tools are disabled in public mode. "
            "Use tw_get_activity_analysis for compact projected samples."
        ),
    }
    get_client.assert_not_called()


async def test_public_mode_disables_mutation_tools_by_default(public_mode, monkeypatch):
    delete_activity = AsyncMock(side_effect=AssertionError("public mode must not call mutation implementation"))
    monkeypatch.setattr(server_mod.activities_mod, "delete_activity", delete_activity)
    storage = AsyncMock(side_effect=AssertionError("public mode must not load local credentials"))
    monkeypatch.setattr(server_mod, "CredentialStorage", storage)
    token = _set_request_context(_request({"X-Tymewear-Token": "upstream-token"}))

    try:
        result = await server_mod.call_tool("tw_delete_activity", {"activity_id": "activity-123"})
    finally:
        request_ctx.reset(token)

    payload = json.loads(result[0].text)
    assert payload == {
        "isError": True,
        "error_code": "PUBLIC_MUTATIONS_DISABLED",
        "message": (
            "Mutation tools are disabled in public mode by default. "
            "Enable them explicitly only for trusted deployments."
        ),
    }
    delete_activity.assert_not_called()
    storage.assert_not_called()


async def test_public_mode_returns_structured_validation_errors(public_mode, monkeypatch):
    monkeypatch.setenv("TYMEWEAR_EMAIL", "athlete@example.com")
    monkeypatch.setenv("TYMEWEAR_PASSWORD", "secret")

    result = await server_mod.call_tool("tw_get_activity", {})

    payload = json.loads(result[0].text)
    assert payload == {
        "isError": True,
        "error_code": "INVALID_TOOL_ARGUMENTS",
        "message": "Invalid tool arguments.",
    }
    assert "activity_id" not in result[0].text


async def test_public_mode_returns_unknown_tool_without_upstream_token(public_mode, monkeypatch):
    storage = AsyncMock(side_effect=AssertionError("public mode must not load local credentials"))
    monkeypatch.setattr(server_mod, "CredentialStorage", storage)

    result = await server_mod.call_tool("tw_not_a_tool", {})

    payload = json.loads(result[0].text)
    assert payload == {
        "isError": True,
        "error_code": "UNKNOWN_TOOL",
        "message": "Unknown tool.",
    }
    assert "tw_not_a_tool" not in result[0].text
    storage.assert_not_called()


async def test_public_mode_projects_nested_success_results_before_serialization(public_mode, monkeypatch):
    mock_client = AsyncMock()
    monkeypatch.setattr(server_mod, "_get_client", lambda: mock_client)
    monkeypatch.setattr(
        server_mod.profile_mod,
        "get_profile",
        AsyncMock(
            return_value={
                "id": "private-profile-id",
                "uuid": "7d5d7863-fac6-4fc2-8f96-c37f861c73f4",
                "email": "athlete@example.test",
                "device": {"serial_number": "private-serial"},
                "weight": 72.5,
                "nested": [{"ve": 58.7, "download_url": "https://example.test/file?token=private"}],
                "unsafe_number": float("nan"),
            }
        ),
    )

    result = await server_mod.call_tool("tw_get_profile", {})

    payload = json.loads(result[0].text)
    assert payload == {"device": {}, "weight": 72.5, "nested": [{"ve": 58.7}]}
    assert "athlete@example.test" not in result[0].text
    assert "private" not in result[0].text
    json.dumps(payload, allow_nan=False)


@pytest.mark.parametrize("include_location", [False, True])
async def test_public_mode_allows_location_only_for_explicit_analysis_opt_in(
    public_mode, monkeypatch, include_location
):
    mock_client = AsyncMock()
    monkeypatch.setattr(server_mod, "_get_client", lambda: mock_client)
    route = AsyncMock(
        return_value={
            "activity_id": "activity-123",
            "identity": {"name": "Ride", "home_lat": 46.1, "home_long": 7.1},
            "summary": {"latitude": 46.2, "longitude": 7.2},
            "channels": {
                "position_lat": {"source": "fit_export", "canonical_unit": "semicircles"},
                "position_long": {"source": "fit_export", "canonical_unit": "semicircles"},
                "heart_rate": {"source": "fit_export", "canonical_unit": "bpm"},
            },
            "raw_samples": {
                "data": [
                    {
                        "elapsed_seconds": 0,
                        "position_lat": 550000000,
                        "position_long": 85000000,
                        "latitude": 46.3,
                        "home_lat": 46.1,
                        "heart_rate": 141,
                    }
                ]
            },
        }
    )
    monkeypatch.setattr(server_mod.activity_analysis_mod, "tw_get_activity_analysis", route)

    result = await server_mod.call_tool(
        "tw_get_activity_analysis",
        {"activity_id": "activity-123", "include_location": include_location},
    )

    payload = json.loads(result[0].text)
    assert payload["activity_id"] == "activity-123"
    assert "home_lat" not in result[0].text
    assert "latitude" not in result[0].text
    if include_location:
        assert set(payload["channels"]) == {"position_lat", "position_long", "heart_rate"}
        assert payload["raw_samples"]["data"] == [
            {
                "elapsed_seconds": 0,
                "position_lat": 550000000,
                "position_long": 85000000,
                "heart_rate": 141,
            }
        ]
    else:
        assert set(payload["channels"]) == {"heart_rate"}
        assert payload["raw_samples"]["data"] == [{"elapsed_seconds": 0, "heart_rate": 141}]


async def test_public_mode_never_exposes_location_through_another_tool(public_mode, monkeypatch):
    mock_client = AsyncMock()
    monkeypatch.setattr(server_mod, "_get_client", lambda: mock_client)
    monkeypatch.setattr(
        server_mod.activity_files_mod,
        "get_activity_workout_zone_detection",
        AsyncMock(
            return_value={
                "zone_summary_table": {"Duration [sec]": {"Zone 1": 10}},
                "position_lat": 550000000,
                "position_long": 85000000,
                "raw_samples": {
                    "data": [{"elapsed_seconds": 0, "position_lat": 550000000, "position_long": 85000000}]
                },
            }
        ),
    )

    result = await server_mod.call_tool(
        "tw_get_activity_workout_zone_detection",
        {"activity_id": "activity-123", "include": ["position_lat", "position_long"]},
    )

    payload = json.loads(result[0].text)
    assert payload == {"zone_summary_table": {"Duration [sec]": {"Zone 1": 10}}}
    assert "position_lat" not in result[0].text
    assert "position_long" not in result[0].text


async def test_public_mode_contains_handler_error_without_private_text(public_mode, monkeypatch, caplog):
    mock_client = AsyncMock()
    monkeypatch.setattr(server_mod, "_get_client", lambda: mock_client)
    private_error = "athlete@example.test /private/tmp/file.fit?token=secret"
    monkeypatch.setattr(server_mod.profile_mod, "get_profile", AsyncMock(side_effect=RuntimeError(private_error)))

    with caplog.at_level("ERROR", logger="tymewear_mcp.server"):
        result = await server_mod.call_tool("tw_get_profile", {})

    assert json.loads(result[0].text) == {
        "isError": True,
        "error_code": "PUBLIC_TOOL_FAILED",
        "message": "Public tool request failed.",
    }
    assert "RuntimeError" in caplog.text
    assert "athlete@example.test" not in caplog.text
    assert "/private/tmp" not in caplog.text
    assert "token=secret" not in caplog.text
    mock_client.close.assert_awaited_once()


async def test_public_mode_contains_client_close_error_without_private_text(public_mode, monkeypatch, caplog):
    mock_client = AsyncMock()
    mock_client.close = AsyncMock(side_effect=RuntimeError("/tmp/private?token=secret"))
    monkeypatch.setattr(server_mod, "_get_client", lambda: mock_client)
    monkeypatch.setattr(server_mod.profile_mod, "get_profile", AsyncMock(return_value={"weight": 72.5}))

    with caplog.at_level("ERROR", logger="tymewear_mcp.server"):
        result = await server_mod.call_tool("tw_get_profile", {})

    assert json.loads(result[0].text) == {
        "isError": True,
        "error_code": "PUBLIC_TOOL_FAILED",
        "message": "Public tool request failed.",
    }
    assert "RuntimeError" in caplog.text
    assert "/tmp/private" not in caplog.text
    assert "token=secret" not in caplog.text


async def test_local_mode_preserves_handler_exception_behavior(monkeypatch):
    mock_client = AsyncMock()
    monkeypatch.setattr(server_mod, "_get_client", lambda: mock_client)
    monkeypatch.setattr(server_mod.profile_mod, "get_profile", AsyncMock(side_effect=RuntimeError("local failure")))

    with pytest.raises(RuntimeError, match="local failure"):
        await server_mod.call_tool("tw_get_profile", {})

    mock_client.close.assert_not_called()


async def test_public_mode_returns_private_text_free_credential_error(public_mode, monkeypatch):
    monkeypatch.setattr(
        server_mod,
        "_get_client",
        lambda: (_ for _ in ()).throw(
            public_mod.PublicCredentialError("athlete@example.test /tmp/token-file?token=secret")
        ),
    )

    result = await server_mod.call_tool("tw_get_profile", {})

    assert json.loads(result[0].text) == {
        "isError": True,
        "error_code": "TYMEWEAR_UPSTREAM_TOKEN_REQUIRED",
        "message": "Public Tyme Wear credentials are unavailable.",
    }
    assert "athlete@example.test" not in result[0].text
    assert "/tmp" not in result[0].text
    assert "token=secret" not in result[0].text


async def test_public_mode_projects_early_disabled_and_unknown_results(public_mode, monkeypatch):
    calls = []

    def project(tool_name, value, *, include_location=False):
        calls.append((tool_name, include_location, value["error_code"]))
        return {**value, "projected": True}

    monkeypatch.setattr(server_mod, "project_public_tool_result", project, raising=False)
    get_client = AsyncMock(side_effect=AssertionError("early public errors must not construct a client"))
    monkeypatch.setattr(server_mod, "_get_client", get_client)

    disabled = await server_mod.call_tool("tw_get_processed_data", {"activity_id": "activity-123"})
    unknown = await server_mod.call_tool("tw_not_a_tool", {})

    assert json.loads(disabled[0].text)["projected"] is True
    assert json.loads(unknown[0].text)["projected"] is True
    assert calls == [
        ("tw_get_processed_data", False, "PUBLIC_RAW_DATA_DISABLED"),
        ("tw_not_a_tool", False, "UNKNOWN_TOOL"),
    ]
    get_client.assert_not_called()


async def test_public_mode_contains_projection_failure_with_stable_error(public_mode, monkeypatch, caplog):
    get_client = AsyncMock(side_effect=AssertionError("disabled tool must not construct a client"))
    monkeypatch.setattr(server_mod, "_get_client", get_client)
    monkeypatch.setattr(
        server_mod,
        "project_public_tool_result",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("athlete@example.test /private/tmp/result?token=secret")
        ),
    )

    malicious_tool_name = "athlete@example.test /private/tmp/result?token=secret"
    with caplog.at_level("ERROR", logger="tymewear_mcp.server"):
        result = await server_mod.call_tool(malicious_tool_name, {})

    assert json.loads(result[0].text) == {
        "isError": True,
        "error_code": "PUBLIC_TOOL_FAILED",
        "message": "Public tool request failed.",
    }
    assert "RuntimeError" in caplog.text
    assert "athlete@example.test" not in caplog.text
    assert "/private/tmp" not in caplog.text
    assert "token=secret" not in caplog.text
    get_client.assert_not_called()
