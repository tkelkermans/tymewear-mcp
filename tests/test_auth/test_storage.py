"""Tests for unified credential storage."""

import os
from unittest.mock import patch

from tymewear_mcp.auth.storage import CredentialStorage


class TestCredentialStorage:
    def test_load_from_keyring_first(self):
        with (
            patch("tymewear_mcp.auth.storage.KeyringStorage") as MockKr,
            patch("tymewear_mcp.auth.storage.EncryptedStorage") as MockEnc,
        ):
            MockKr.return_value.load.return_value = {"email": "a@b.com", "password": "fromkeyring"}
            storage = CredentialStorage()
            creds = storage.load()
            assert creds == {"email": "a@b.com", "password": "fromkeyring"}
            MockEnc.return_value.load.assert_not_called()

    def test_fallback_to_encrypted(self):
        with (
            patch("tymewear_mcp.auth.storage.KeyringStorage") as MockKr,
            patch("tymewear_mcp.auth.storage.EncryptedStorage") as MockEnc,
        ):
            MockKr.return_value.load.return_value = None
            MockEnc.return_value.load.return_value = {"email": "a@b.com", "password": "fromfile"}
            storage = CredentialStorage()
            creds = storage.load()
            assert creds == {"email": "a@b.com", "password": "fromfile"}

    def test_fallback_to_env_vars(self):
        with (
            patch("tymewear_mcp.auth.storage.KeyringStorage") as MockKr,
            patch("tymewear_mcp.auth.storage.EncryptedStorage") as MockEnc,
            patch.dict("os.environ", {"TYMEWEAR_EMAIL": "env@test.com", "TYMEWEAR_PASSWORD": "envpass"}),
        ):
            MockKr.return_value.load.return_value = None
            MockEnc.return_value.load.return_value = None
            storage = CredentialStorage()
            creds = storage.load()
            assert creds == {"email": "env@test.com", "password": "envpass"}

    def test_returns_none_when_nothing_available(self):
        with (
            patch("tymewear_mcp.auth.storage.KeyringStorage") as MockKr,
            patch("tymewear_mcp.auth.storage.EncryptedStorage") as MockEnc,
        ):
            MockKr.return_value.load.return_value = None
            MockEnc.return_value.load.return_value = None
            storage = CredentialStorage()
            os.environ.pop("TYMEWEAR_EMAIL", None)
            os.environ.pop("TYMEWEAR_PASSWORD", None)
            creds = storage.load()
            assert creds is None

    def test_save_writes_to_both(self):
        with (
            patch("tymewear_mcp.auth.storage.KeyringStorage") as MockKr,
            patch("tymewear_mcp.auth.storage.EncryptedStorage") as MockEnc,
        ):
            storage = CredentialStorage()
            storage.save("a@b.com", "pass")
            MockKr.return_value.save.assert_called_once_with("a@b.com", "pass")
            MockEnc.return_value.save.assert_called_once_with("a@b.com", "pass")

    def test_save_continues_if_keyring_fails(self):
        with (
            patch("tymewear_mcp.auth.storage.KeyringStorage") as MockKr,
            patch("tymewear_mcp.auth.storage.EncryptedStorage") as MockEnc,
        ):
            MockKr.return_value.save.side_effect = Exception("keyring broken")
            storage = CredentialStorage()
            storage.save("a@b.com", "pass")
            MockEnc.return_value.save.assert_called_once_with("a@b.com", "pass")
