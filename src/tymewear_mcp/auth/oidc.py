"""OIDC bearer-token verifier for the public MCP (managed-provider auth).

Validates JWT access tokens issued by an external OAuth provider (e.g. WorkOS,
Stytch) against the provider JWKS, then enforces an email allowlist. The server
acts as an OAuth *protected resource*; it does not issue tokens itself.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

import httpx
import jwt
from mcp.server.auth.provider import AccessToken

_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384"]
_DISCOVERY_TIMEOUT = 10.0


def _discover_jwks_uri(issuer: str) -> str:
    config_url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    resp = httpx.get(config_url, timeout=_DISCOVERY_TIMEOUT)
    resp.raise_for_status()
    jwks_uri = resp.json().get("jwks_uri")
    if not jwks_uri:
        raise ValueError(f"OIDC discovery at {config_url} did not return a jwks_uri")
    return str(jwks_uri)


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
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._allowed = {email.strip().lower() for email in allowed_emails if email.strip()}
        self._resource_url = resource_url
        self._scopes = list(scopes)
        self._resolve_key = signing_key_resolver

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
    ) -> OIDCTokenVerifier:
        """Build a verifier that fetches signing keys from the provider JWKS.

        JWKS discovery is lazy (on first token) so app construction never blocks
        on the network during a serverless cold start.
        """
        cache: dict[str, Any] = {"client": None}

        def resolver(token: str) -> Any:
            if cache["client"] is None:
                uri = jwks_uri or _discover_jwks_uri(issuer)
                cache["client"] = jwt.PyJWKClient(uri)
            return cache["client"].get_signing_key_from_jwt(token).key

        return cls(
            issuer=issuer,
            audience=audience,
            allowed_emails=allowed_emails,
            resource_url=resource_url,
            scopes=scopes,
            signing_key_resolver=resolver,
        )

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
        except Exception:
            return None
        email = str(claims.get("email") or "").strip().lower()
        if not email or email not in self._allowed:
            return None
        return AccessToken(
            token="[redacted]",
            client_id=str(claims.get("sub") or "oidc-user"),
            scopes=self._scopes,
            resource=self._resource_url,
        )
