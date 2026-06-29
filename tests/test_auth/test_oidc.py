"""Tests for the OIDC token verifier (provider JWT validation + email allowlist)."""

import datetime

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from tymewear_mcp.auth.oidc import OIDCTokenVerifier

ISSUER = "https://auth.example.com"
AUD = "https://tymewear-mcp.vercel.app/mcp"
ALLOWED = ["Tristan@example.com", "coach@example.com"]


@pytest.fixture
def keypair():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


def _verifier(public_key):
    return OIDCTokenVerifier(
        issuer=ISSUER,
        audience=AUD,
        allowed_emails=ALLOWED,
        resource_url=AUD,
        scopes=["tymewear:mcp"],
        signing_key_resolver=lambda _token: public_key,
    )


def _token(priv, **overrides):
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "iss": ISSUER,
        "aud": AUD,
        "sub": "user-1",
        "email": "coach@example.com",
        "iat": now,
        "exp": now + datetime.timedelta(hours=1),
    }
    payload.update(overrides)
    return jwt.encode(payload, priv, algorithm="RS256")


class TestOIDCTokenVerifier:
    async def test_valid_token_accepted(self, keypair):
        priv, pub = keypair
        result = await _verifier(pub).verify_token(_token(priv))
        assert result is not None
        assert result.scopes == ["tymewear:mcp"]
        assert result.resource == AUD

    async def test_allowlist_is_case_insensitive(self, keypair):
        priv, pub = keypair
        # token email differs in case from the configured allowlist entry
        result = await _verifier(pub).verify_token(_token(priv, email="TRISTAN@example.com"))
        assert result is not None

    async def test_email_not_allowlisted_rejected(self, keypair):
        priv, pub = keypair
        assert await _verifier(pub).verify_token(_token(priv, email="stranger@example.com")) is None

    async def test_missing_email_rejected(self, keypair):
        priv, pub = keypair
        tok = jwt.encode(
            {"iss": ISSUER, "aud": AUD, "sub": "x",
             "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)},
            priv, algorithm="RS256",
        )
        assert await _verifier(pub).verify_token(tok) is None

    async def test_expired_rejected(self, keypair):
        priv, pub = keypair
        now = datetime.datetime.now(datetime.timezone.utc)
        assert await _verifier(pub).verify_token(_token(priv, exp=now - datetime.timedelta(hours=1))) is None

    async def test_wrong_audience_rejected(self, keypair):
        priv, pub = keypair
        assert await _verifier(pub).verify_token(_token(priv, aud="https://evil.example.com")) is None

    async def test_wrong_issuer_rejected(self, keypair):
        priv, pub = keypair
        assert await _verifier(pub).verify_token(_token(priv, iss="https://evil.example.com")) is None

    async def test_bad_signature_rejected(self, keypair):
        priv, pub = keypair
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        assert await _verifier(pub).verify_token(_token(other)) is None

    async def test_garbage_rejected(self, keypair):
        _priv, pub = keypair
        assert await _verifier(pub).verify_token("not-a-jwt") is None
