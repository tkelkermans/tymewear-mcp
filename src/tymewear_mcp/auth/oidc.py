"""OIDC bearer-token verifier for the public MCP (managed-provider auth).

Validates JWT access tokens issued by an external OAuth provider (e.g. WorkOS,
Stytch) against the provider JWKS, then enforces an email allowlist. The server
acts as an OAuth *protected resource*; it does not issue tokens itself. When the
access token omits an ``email`` claim, the provider userinfo endpoint is queried.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

import httpx
import jwt
from mcp.server.auth.provider import AccessToken

logger = logging.getLogger(__name__)

_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384"]
_DISCOVERY_TIMEOUT = 10.0


def _discover_config(issuer: str) -> dict[str, Any]:
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    resp = httpx.get(url, timeout=_DISCOVERY_TIMEOUT)
    resp.raise_for_status()
    return dict(resp.json())


class OIDCTokenVerifier:
    """Validate provider-issued JWT access tokens and enforce an email allowlist."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        allowed_emails: Iterable[str],
        resource_url: str,
        scopes: Iterable[str],
        signing_key_resolver: Callable[[str], Any],
        userinfo_resolver: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._allowed = {email.strip().lower() for email in allowed_emails if email.strip()}
        self._resource_url = resource_url
        self._scopes = list(scopes)
        self._resolve_key = signing_key_resolver
        self._resolve_userinfo = userinfo_resolver

    @classmethod
    def from_issuer(
        cls,
        *,
        issuer: str,
        audience: str,
        allowed_emails: Iterable[str],
        resource_url: str,
        scopes: Iterable[str],
        jwks_uri: str | None = None,
        userinfo_endpoint: str | None = None,
    ) -> OIDCTokenVerifier:
        """Build a verifier that resolves keys/userinfo from the provider.

        Discovery is lazy (on first token) so app construction never blocks on the
        network during a serverless cold start.
        """
        cache: dict[str, Any] = {"jwk": None, "config": None}

        def _config() -> dict[str, Any]:
            if cache["config"] is None:
                cache["config"] = _discover_config(issuer)
            config: dict[str, Any] = cache["config"]
            return config

        def key_resolver(token: str) -> Any:
            if cache["jwk"] is None:
                uri = jwks_uri or _config().get("jwks_uri")
                if not uri:
                    raise ValueError("OIDC discovery returned no jwks_uri")
                cache["jwk"] = jwt.PyJWKClient(uri)
            return cache["jwk"].get_signing_key_from_jwt(token).key

        def userinfo_resolver(token: str) -> dict[str, Any]:
            url = userinfo_endpoint or _config().get("userinfo_endpoint")
            if not url:
                return {}
            resp = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=_DISCOVERY_TIMEOUT)
            resp.raise_for_status()
            return dict(resp.json())

        return cls(
            issuer=issuer,
            audience=audience,
            allowed_emails=allowed_emails,
            resource_url=resource_url,
            scopes=scopes,
            signing_key_resolver=key_resolver,
            userinfo_resolver=userinfo_resolver,
        )

    def _email_from_userinfo(self, token: str) -> str | None:
        if self._resolve_userinfo is None:
            return None
        try:
            info = self._resolve_userinfo(token)
        except Exception:
            logger.info("OIDC userinfo lookup failed")
            return None
        email = info.get("email") if isinstance(info, dict) else None
        return str(email).strip().lower() if email else None

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            key = self._resolve_key(token)
            claims = jwt.decode(
                token,
                key,
                algorithms=_ALGORITHMS,
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iss", "aud"]},
            )
        except Exception as exc:
            self._log_decode_failure(token, exc)
            return None
        email = str(claims.get("email") or "").strip().lower()
        if not email:
            email = self._email_from_userinfo(token) or ""
        if not email or email not in self._allowed:
            logger.info("OIDC token rejected: email not in allowlist")
            return None
        return AccessToken(
            token="[redacted]",
            client_id=str(claims.get("sub") or "oidc-user"),
            scopes=self._scopes,
            resource=self._resource_url,
        )

    @staticmethod
    def _log_decode_failure(token: str, exc: Exception) -> None:
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
            logger.info(
                "OIDC token rejected: %s (iss=%r aud=%r)",
                type(exc).__name__,
                unverified.get("iss"),
                unverified.get("aud"),
            )
        except Exception:
            logger.info("OIDC token rejected: %s", type(exc).__name__)
