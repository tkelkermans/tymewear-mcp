from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext
from starlette.requests import Request

from tymewear_mcp import server as server_mod
from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.public import PublicCredentialError, PublicServerConfig, StaticBearerTokenVerifier, build_public_app

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


async def test_public_mode_list_tools_can_expose_mutations_when_explicitly_enabled(monkeypatch):
    monkeypatch.setattr(server_mod, "_public_mode", True)
    monkeypatch.setattr(server_mod, "_public_allow_mutations", True)

    tools = await server_mod.list_tools()
    names = {tool.name for tool in tools}

    assert "tw_update_profile" in names
    assert "tw_delete_activity" in names
    assert "tw_export_csv" not in names


async def test_public_mode_get_client_uses_request_token_without_storage(public_mode, monkeypatch):
    storage = AsyncMock(side_effect=AssertionError("public mode must not load local credentials"))
    monkeypatch.setattr(server_mod, "CredentialStorage", storage)
    token = _set_request_context(_request({"X-Tymewear-Token": "upstream-token"}))

    try:
        client = server_mod._get_client()
        assert isinstance(client, TymeClient)
        assert await client._ensure_token() == "upstream-token"
        storage.assert_not_called()
    finally:
        await client.close()
        request_ctx.reset(token)


def test_public_mode_requires_request_upstream_token(public_mode, monkeypatch):
    storage = AsyncMock(side_effect=AssertionError("public mode must not load local credentials"))
    monkeypatch.setattr(server_mod, "CredentialStorage", storage)
    token = _set_request_context(_request())

    try:
        with pytest.raises(PublicCredentialError, match="X-Tymewear-Token"):
            server_mod._get_client()
        storage.assert_not_called()
    finally:
        request_ctx.reset(token)


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Tymewear-Token": "leaky-upstream-token-value\r\nnext-header"},
        {"X-Tymewear-Token": f"leaky-upstream-token-value{'x' * 4096}"},
        {"X-Tymewear-Authorization": "Token leaky-upstream-token-value\r\nnext-header"},
        {"X-Tymewear-Authorization": f"Token leaky-upstream-token-value{'x' * 4096}"},
    ],
)
async def test_public_mode_invalid_upstream_token_errors_do_not_echo_token(
    public_mode,
    monkeypatch,
    headers: dict[str, str],
):
    storage = AsyncMock(side_effect=AssertionError("public mode must not load local credentials"))
    monkeypatch.setattr(server_mod, "CredentialStorage", storage)
    token = _set_request_context(_request(headers))

    try:
        result = await server_mod.call_tool("tw_get_profile", {})
    finally:
        request_ctx.reset(token)

    payload = json.loads(result[0].text)
    assert payload == {
        "isError": True,
        "error_code": "TYMEWEAR_UPSTREAM_TOKEN_REQUIRED",
        "message": "Public mode received an invalid Tyme Wear upstream token.",
    }
    assert "leaky-upstream-token-value" not in result[0].text
    storage.assert_not_called()


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
    storage = AsyncMock(side_effect=AssertionError("public mode must not load local credentials"))
    monkeypatch.setattr(server_mod, "CredentialStorage", storage)
    token = _set_request_context(_request({"X-Tymewear-Token": "upstream-token"}))

    try:
        result = await server_mod.call_tool("tw_get_activity", {})
    finally:
        request_ctx.reset(token)

    payload = json.loads(result[0].text)
    assert payload == {
        "isError": True,
        "error_code": "INVALID_TOOL_ARGUMENTS",
        "message": "Invalid tool arguments.",
    }
    assert "activity_id" not in result[0].text
    storage.assert_not_called()


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
