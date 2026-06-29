"""Tests for OAuth-related public-mode wiring: composite verifier + config."""

import pytest

from tymewear_mcp.public import CompositeBearerVerifier, PublicServerConfig


class _StubVerifier:
    def __init__(self, result: object) -> None:
        self._result = result

    async def verify_token(self, _token: str) -> object:
        return self._result


class TestCompositeBearerVerifier:
    async def test_static_match_wins(self):
        v = CompositeBearerVerifier(_StubVerifier("STATIC"), _StubVerifier("OIDC"))
        assert await v.verify_token("tok") == "STATIC"

    async def test_falls_through_to_oidc(self):
        v = CompositeBearerVerifier(_StubVerifier(None), _StubVerifier("OIDC"))
        assert await v.verify_token("tok") == "OIDC"

    async def test_both_miss_returns_none(self):
        v = CompositeBearerVerifier(_StubVerifier(None), _StubVerifier(None))
        assert await v.verify_token("tok") is None

    async def test_no_oidc_static_miss_returns_none(self):
        v = CompositeBearerVerifier(_StubVerifier(None), None)
        assert await v.verify_token("tok") is None


def _env(**extra: str) -> dict[str, str]:
    base = {
        "TYMEWEAR_PUBLIC_URL": "https://tymewear-mcp.vercel.app/mcp",
        "TYMEWEAR_PUBLIC_BEARER_TOKENS": "x" * 32,
    }
    base.update(extra)
    return base


class TestPublicConfigOAuth:
    def test_parses_oidc_env(self):
        cfg = PublicServerConfig.from_env(
            _env(
                TYMEWEAR_PUBLIC_ISSUER_URL="https://auth.example.com",
                TYMEWEAR_OIDC_AUDIENCE="https://tymewear-mcp.vercel.app/mcp",
                TYMEWEAR_ALLOWED_EMAILS="a@example.com, b@example.com",
            )
        )
        assert cfg.issuer_url == "https://auth.example.com"
        assert cfg.oidc_audience == "https://tymewear-mcp.vercel.app/mcp"
        assert cfg.allowed_emails == ["a@example.com", "b@example.com"]

    def test_audience_defaults_to_public_url(self):
        cfg = PublicServerConfig.from_env(
            _env(
                TYMEWEAR_PUBLIC_ISSUER_URL="https://auth.example.com",
                TYMEWEAR_ALLOWED_EMAILS="a@example.com",
            )
        )
        assert cfg.oidc_audience == "https://tymewear-mcp.vercel.app/mcp"

    def test_issuer_without_allowlist_rejected(self):
        with pytest.raises(ValueError, match="ALLOWED_EMAILS"):
            PublicServerConfig.from_env(_env(TYMEWEAR_PUBLIC_ISSUER_URL="https://auth.example.com"))

    def test_no_issuer_means_no_oidc(self):
        cfg = PublicServerConfig.from_env(_env())
        assert cfg.issuer_url is None
        assert cfg.allowed_emails == []


class TestPublicConfigScopes:
    def test_oidc_default_scopes_when_issuer_set(self):
        cfg = PublicServerConfig.from_env(
            _env(TYMEWEAR_PUBLIC_ISSUER_URL="https://auth.example.com", TYMEWEAR_ALLOWED_EMAILS="a@example.com")
        )
        assert cfg.scopes == ["openid", "profile", "email"]

    def test_default_scope_without_issuer(self):
        assert PublicServerConfig.from_env(_env()).scopes == ["tymewear:mcp"]

    def test_scopes_override(self):
        cfg = PublicServerConfig.from_env(
            _env(
                TYMEWEAR_PUBLIC_ISSUER_URL="https://auth.example.com",
                TYMEWEAR_ALLOWED_EMAILS="a@example.com",
                TYMEWEAR_OIDC_SCOPES="openid email",
            )
        )
        assert cfg.scopes == ["openid", "email"]
