"""Public Streamable HTTP deployment support."""

from __future__ import annotations

import hmac
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse

from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.routes import build_resource_metadata_url, create_protected_resource_routes
from mcp.server.lowlevel.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.datastructures import MutableHeaders
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Message, Receive, Scope, Send

from tymewear_mcp.auth.oidc import OIDCTokenVerifier
from tymewear_mcp.tools._privacy import project_public_payload

DEFAULT_PUBLIC_MCP_PATH = "/mcp"
DEFAULT_PUBLIC_SCOPE = "tymewear:mcp"
HSTS_HEADER_VALUE = "max-age=31536000"
PUBLIC_TOKEN_ENV = "TYMEWEAR_PUBLIC_BEARER_TOKENS"
LEGACY_PUBLIC_TOKEN_ENV = "TYMEWEAR_PUBLIC_BEARER_TOKEN"
PUBLIC_ALLOW_MUTATIONS_ENV = "TYMEWEAR_PUBLIC_ALLOW_MUTATIONS"
PUBLIC_MAX_BODY_BYTES_ENV = "TYMEWEAR_PUBLIC_MAX_BODY_BYTES"
UPSTREAM_TOKEN_HEADER = "x-tymewear-token"
UPSTREAM_AUTHORIZATION_HEADER = "x-tymewear-authorization"
MAX_UPSTREAM_TOKEN_LENGTH = 4096
MIN_PUBLIC_BEARER_TOKEN_LENGTH = 32
DEFAULT_PUBLIC_MAX_BODY_BYTES = 1_048_576
_ACTIVITY_OBJECT_TOOLS = frozenset(
    {
        "tw_get_activities",
        "tw_get_activity",
        "tw_get_activity_status",
        "tw_get_pinned_activity",
        "tw_pin_activity",
    }
)


class PublicCredentialError(RuntimeError):
    """Raised when a public request lacks usable request-scoped upstream credentials."""


def project_public_tool_result(
    tool_name: str,
    value: Any,
    *,
    include_location: bool = False,
) -> Any:
    """Apply the public response policy for one named tool."""
    compact_analysis = tool_name == "tw_get_activity_analysis"
    return project_public_payload(
        value,
        compact_analysis=compact_analysis,
        allow_analysis_location=compact_analysis and include_location is True,
        preserve_activity_ids=tool_name in _ACTIVITY_OBJECT_TOOLS,
    )


def _split_tokens(value: str | None) -> list[str]:
    if value is None:
        return []
    return [token.strip() for token in value.split(",") if token.strip()]


def _env_flag(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(value: str | None, *, default: int, name: str) -> int:
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return parsed


def _default_allowed_hosts(public_url: str) -> list[str]:
    parsed = urlparse(public_url)
    return [parsed.netloc] if parsed.netloc else []


def _default_allowed_origins(public_url: str) -> list[str]:
    parsed = urlparse(public_url)
    if parsed.scheme and parsed.netloc:
        return [f"{parsed.scheme}://{parsed.netloc}"]
    return []


def _trusted_host_patterns(allowed_hosts: list[str]) -> list[str]:
    patterns: list[str] = []
    for host in allowed_hosts:
        if host == "*" or host.startswith("*."):
            patterns.append(host)
        elif host.endswith(":*"):
            patterns.append(host[:-2])
        else:
            patterns.append(host.rsplit(":", 1)[0])
    return patterns


def _validate_allowed_hosts(allowed_hosts: list[str]) -> None:
    for host in allowed_hosts:
        host = host.strip()
        if not host:
            raise ValueError("TYMEWEAR_PUBLIC_ALLOWED_HOSTS entries must not be empty")
        if host == "*":
            raise ValueError("TYMEWEAR_PUBLIC_ALLOWED_HOSTS must not contain '*'")
        if "://" in host or "/" in host or "\\" in host or any(char.isspace() for char in host):
            raise ValueError("TYMEWEAR_PUBLIC_ALLOWED_HOSTS entries must be hostnames, not URLs or paths")


def _validate_allowed_origins(allowed_origins: list[str]) -> None:
    for origin in allowed_origins:
        origin = origin.strip()
        parsed = urlparse(origin)
        if not origin:
            raise ValueError("TYMEWEAR_PUBLIC_ALLOWED_ORIGINS entries must not be empty")
        if "*" in origin:
            raise ValueError("TYMEWEAR_PUBLIC_ALLOWED_ORIGINS must not contain wildcards")
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ValueError("TYMEWEAR_PUBLIC_ALLOWED_ORIGINS entries must be absolute http(s) origins")
        if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
            raise ValueError("TYMEWEAR_PUBLIC_ALLOWED_ORIGINS entries must not include paths or query strings")
        localhost = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not localhost:
            raise ValueError("TYMEWEAR_PUBLIC_ALLOWED_ORIGINS must use https except for localhost development")


def _normalize_url_path(path: str) -> str:
    if path in {"", "/"}:
        return "/"
    return path.rstrip("/")


def _validate_public_url(public_url: str, *, name: str = "TYMEWEAR_PUBLIC_URL") -> None:
    parsed = urlparse(public_url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError(f"{name} must be an absolute http(s) URL")
    if parsed.params or parsed.query or parsed.fragment:
        raise ValueError(f"{name} must not include params, query strings, or fragments")
    localhost = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not localhost:
        raise ValueError(f"{name} must use https except for localhost development")


def _validate_mcp_path(mcp_path: str) -> None:
    if not mcp_path.startswith("/"):
        raise ValueError("mcp_path must start with '/'")
    if any(char.isspace() for char in mcp_path) or "?" in mcp_path or "#" in mcp_path:
        raise ValueError("mcp_path must be a URL path without whitespace, query strings, or fragments")


def _validate_public_url_path(public_url: str, mcp_path: str) -> None:
    parsed = urlparse(public_url)
    if _normalize_url_path(parsed.path) != _normalize_url_path(mcp_path):
        raise ValueError("TYMEWEAR_PUBLIC_URL path must match the public MCP route path")


def _public_url_from_env(env: Mapping[str, str], mcp_path: str) -> str | None:
    if env.get("TYMEWEAR_PUBLIC_URL"):
        return env["TYMEWEAR_PUBLIC_URL"]

    for key in ("VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
        host = env.get(key)
        if host:
            host = host.removeprefix("https://").removeprefix("http://").rstrip("/")
            return f"https://{host}{mcp_path}"

    return None


@dataclass
class PublicServerConfig:
    """Configuration for the public Streamable HTTP server."""

    public_url: str
    bearer_tokens: list[str]
    allowed_hosts: list[str] = field(default_factory=list)
    allowed_origins: list[str] = field(default_factory=list)
    mcp_path: str = DEFAULT_PUBLIC_MCP_PATH
    scopes: list[str] = field(default_factory=lambda: [DEFAULT_PUBLIC_SCOPE])
    json_response: bool = False
    issuer_url: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_uri: str | None = None
    allowed_emails: list[str] = field(default_factory=list)
    allow_mutations: bool = False
    max_body_bytes: int = DEFAULT_PUBLIC_MAX_BODY_BYTES

    def __post_init__(self) -> None:
        _validate_mcp_path(self.mcp_path)
        _validate_public_url(self.public_url)
        _validate_public_url_path(self.public_url, self.mcp_path)
        if self.issuer_url is not None:
            _validate_public_url(self.issuer_url, name="TYMEWEAR_PUBLIC_ISSUER_URL")
            self.allowed_emails = [email.strip() for email in self.allowed_emails if email.strip()]
            if not self.allowed_emails:
                raise ValueError(
                    "TYMEWEAR_ALLOWED_EMAILS must list at least one email when TYMEWEAR_PUBLIC_ISSUER_URL is set"
                )
        self.bearer_tokens = [token.strip() for token in self.bearer_tokens if token.strip()]
        if not self.bearer_tokens:
            raise ValueError(f"{PUBLIC_TOKEN_ENV} must contain at least one bearer token")
        if any(len(token) < MIN_PUBLIC_BEARER_TOKEN_LENGTH for token in self.bearer_tokens):
            raise ValueError(
                f"{PUBLIC_TOKEN_ENV} entries must be at least {MIN_PUBLIC_BEARER_TOKEN_LENGTH} characters"
            )
        if self.max_body_bytes <= 0:
            raise ValueError("max_body_bytes must be greater than 0")
        if not self.allowed_hosts:
            self.allowed_hosts = _default_allowed_hosts(self.public_url)
        if not self.allowed_origins:
            self.allowed_origins = _default_allowed_origins(self.public_url)
        _validate_allowed_hosts(self.allowed_hosts)
        _validate_allowed_origins(self.allowed_origins)

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        public_url: str | None = None,
        allowed_hosts: list[str] | None = None,
        allowed_origins: list[str] | None = None,
        issuer_url: str | None = None,
        mcp_path: str = DEFAULT_PUBLIC_MCP_PATH,
        json_response: bool = False,
        allow_mutations: bool | None = None,
        max_body_bytes: int | None = None,
    ) -> PublicServerConfig:
        env = environ or os.environ
        tokens = _split_tokens(env.get(PUBLIC_TOKEN_ENV)) or _split_tokens(env.get(LEGACY_PUBLIC_TOKEN_ENV))
        resolved_public_url = public_url or _public_url_from_env(env, mcp_path)
        if resolved_public_url is None:
            raise ValueError("TYMEWEAR_PUBLIC_URL must be set for public mode outside Vercel")
        resolved_issuer = issuer_url or env.get("TYMEWEAR_PUBLIC_ISSUER_URL")
        scopes_env = env.get("TYMEWEAR_OIDC_SCOPES")
        if scopes_env:
            scopes = scopes_env.replace(",", " ").split()
        elif resolved_issuer:
            # claude.ai requests these from the provider; custom scopes get invalid_scope.
            scopes = ["openid", "profile", "email"]
        else:
            scopes = [DEFAULT_PUBLIC_SCOPE]
        return cls(
            public_url=resolved_public_url,
            bearer_tokens=tokens,
            allowed_hosts=allowed_hosts or _split_tokens(env.get("TYMEWEAR_PUBLIC_ALLOWED_HOSTS")),
            allowed_origins=allowed_origins or _split_tokens(env.get("TYMEWEAR_PUBLIC_ALLOWED_ORIGINS")),
            issuer_url=resolved_issuer,
            scopes=scopes,
            oidc_audience=env.get("TYMEWEAR_OIDC_AUDIENCE"),
            oidc_jwks_uri=env.get("TYMEWEAR_OIDC_JWKS_URL"),
            allowed_emails=_split_tokens(env.get("TYMEWEAR_ALLOWED_EMAILS")),
            mcp_path=mcp_path,
            json_response=json_response,
            allow_mutations=_env_flag(env.get(PUBLIC_ALLOW_MUTATIONS_ENV))
            if allow_mutations is None
            else allow_mutations,
            max_body_bytes=_env_int(
                env.get(PUBLIC_MAX_BODY_BYTES_ENV),
                default=DEFAULT_PUBLIC_MAX_BODY_BYTES,
                name=PUBLIC_MAX_BODY_BYTES_ENV,
            )
            if max_body_bytes is None
            else max_body_bytes,
        )


class StaticBearerTokenVerifier:
    """Validate public MCP bearer tokens against server-side configured secrets."""

    def __init__(self, bearer_tokens: list[str], resource_url: str, scopes: list[str]) -> None:
        self._bearer_tokens = bearer_tokens
        self._resource_url = resource_url
        self._scopes = scopes

    async def verify_token(self, token: str) -> AccessToken | None:
        matched = False
        for expected in self._bearer_tokens:
            if hmac.compare_digest(token, expected):
                matched = True
        if matched:
            return AccessToken(
                token="[redacted]",
                client_id="tymewear-public-client",
                scopes=self._scopes,
                resource=self._resource_url,
            )
        return None


class _BearerVerifier(Protocol):
    async def verify_token(self, token: str) -> AccessToken | None: ...


class CompositeBearerVerifier:
    """Accept a static gateway bearer (header clients) or a provider OIDC JWT (claude.ai)."""

    def __init__(self, static_verifier: _BearerVerifier, oidc_verifier: _BearerVerifier | None = None) -> None:
        self._static = static_verifier
        self._oidc = oidc_verifier

    async def verify_token(self, token: str) -> AccessToken | None:
        result = await self._static.verify_token(token)
        if result is not None:
            return result
        if self._oidc is not None:
            return await self._oidc.verify_token(token)
        return None


class _StreamableHTTPASGIApp:
    def __init__(self, session_manager: StreamableHTTPSessionManager) -> None:
        self._session_manager = session_manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._session_manager.handle_request(scope, receive, send)


class _PublicSecurityHeadersMiddleware:
    def __init__(self, app: Any, hsts_enabled: bool = False) -> None:
        self._app = app
        self._hsts_enabled = hsts_enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
                headers["Pragma"] = "no-cache"
                headers["Referrer-Policy"] = "no-referrer"
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["X-Robots-Tag"] = "noindex, nofollow"
                if self._hsts_enabled:
                    headers["Strict-Transport-Security"] = HSTS_HEADER_VALUE
            await send(message)

        await self._app(scope, receive, send_with_security_headers)


class _PublicBodySizeLimitMiddleware:
    def __init__(self, app: Any, max_body_bytes: int) -> None:
        self._app = app
        self._max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        content_length = _content_length(scope)
        if content_length is not None and content_length > self._max_body_bytes:
            response = JSONResponse(
                {"detail": "Request body too large."},
                status_code=413,
            )
            await response(scope, receive, send)
            return

        total_body_bytes = 0
        body_too_large = False

        async def receive_with_body_limit() -> Message:
            nonlocal body_too_large, total_body_bytes
            message = await receive()
            if message["type"] == "http.request":
                total_body_bytes += len(message.get("body", b""))
                if total_body_bytes > self._max_body_bytes:
                    body_too_large = True
                    return {"type": "http.disconnect"}
            return message

        async def send_with_body_limit(message: Message) -> None:
            if body_too_large:
                return
            await send(message)

        try:
            await self._app(scope, receive_with_body_limit, send_with_body_limit)
        except Exception:
            if not body_too_large:
                raise

        if body_too_large:
            response = JSONResponse(
                {"detail": "Request body too large."},
                status_code=413,
            )
            await response(scope, receive, send)


def _content_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name.lower() == b"content-length":
            try:
                return int(value.decode("ascii"))
            except ValueError:
                return None
    return None


async def _health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def build_public_app(config: PublicServerConfig, mcp_server: Server[Any, Any] | None = None) -> Starlette:
    """Build the public ASGI app without starting a network listener."""
    if mcp_server is None:
        from tymewear_mcp.server import enable_public_mode, server

        enable_public_mode(allow_mutations=config.allow_mutations)
        mcp_server = server

    session_manager = StreamableHTTPSessionManager(
        app=mcp_server,
        json_response=config.json_response,
        stateless=True,
        security_settings=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=config.allowed_hosts,
            allowed_origins=config.allowed_origins,
        ),
    )
    mcp_app = _StreamableHTTPASGIApp(session_manager)
    static_verifier = StaticBearerTokenVerifier(
        bearer_tokens=config.bearer_tokens,
        resource_url=config.public_url,
        scopes=config.scopes,
    )
    oidc_verifier = None
    if config.issuer_url is not None:
        oidc_verifier = OIDCTokenVerifier.from_issuer(
            issuer=config.issuer_url,
            audience=config.oidc_audience,
            allowed_emails=config.allowed_emails,
            resource_url=config.public_url,
            scopes=config.scopes,
            jwks_uri=config.oidc_jwks_uri,
        )
    verifier = CompositeBearerVerifier(static_verifier, oidc_verifier)

    resource_metadata_url = None
    routes = [
        Route("/healthz", endpoint=_health, methods=["GET"]),
    ]
    if config.issuer_url is not None:
        resource_url = AnyHttpUrl(config.public_url)
        resource_metadata_url = build_resource_metadata_url(resource_url)
        routes.extend(
            create_protected_resource_routes(
                resource_url=resource_url,
                authorization_servers=[AnyHttpUrl(config.issuer_url)],
                scopes_supported=config.scopes,
                resource_name="Tymewear MCP",
            )
        )
    routes.append(
        Route(
            config.mcp_path,
            endpoint=RequireAuthMiddleware(mcp_app, config.scopes, resource_metadata_url),
        )
    )
    middleware = [
        Middleware(_PublicSecurityHeadersMiddleware, hsts_enabled=urlparse(config.public_url).scheme == "https"),
        Middleware(TrustedHostMiddleware, allowed_hosts=_trusted_host_patterns(config.allowed_hosts)),
        Middleware(_PublicBodySizeLimitMiddleware, max_body_bytes=config.max_body_bytes),
        Middleware(AuthenticationMiddleware, backend=BearerAuthBackend(verifier)),
        Middleware(AuthContextMiddleware),
    ]
    return Starlette(routes=routes, middleware=middleware, lifespan=lambda _: session_manager.run())


def extract_upstream_token(request: Any) -> str:
    """Extract the request-scoped Tyme Wear token from public-mode headers."""
    headers = getattr(request, "headers", None)
    if headers is None:
        raise PublicCredentialError(
            "Public mode requires X-Tymewear-Token on every tool request; no HTTP request context was available."
        )

    token = headers.get(UPSTREAM_TOKEN_HEADER)
    if token:
        return _validate_upstream_token(token)

    authorization = headers.get(UPSTREAM_AUTHORIZATION_HEADER)
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "token" and value:
            return _validate_upstream_token(value)

    raise PublicCredentialError(
        "Public mode requires X-Tymewear-Token or X-Tymewear-Authorization: Token <token> on every tool request."
    )


def _validate_upstream_token(token: str) -> str:
    token = token.strip()
    if not token:
        raise PublicCredentialError("Public mode received an empty Tyme Wear upstream token.")
    if len(token) > MAX_UPSTREAM_TOKEN_LENGTH or "\r" in token or "\n" in token:
        raise PublicCredentialError("Public mode received an invalid Tyme Wear upstream token.")
    return token
