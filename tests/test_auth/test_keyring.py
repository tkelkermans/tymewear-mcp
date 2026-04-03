"""Tests for system keyring credential storage."""

from unittest.mock import patch

from tymewear_mcp.auth.keyring import KeyringStorage

SERVICE_NAME = "tymewear-mcp"


class TestKeyringStorage:
    def test_save_and_load(self):
        with patch("tymewear_mcp.auth.keyring.keyring") as mock_kr:
            mock_kr.get_password.return_value = '{"email": "a@b.com", "password": "pass123"}'
            storage = KeyringStorage()
            storage.save("a@b.com", "pass123")
            mock_kr.set_password.assert_called_once()
            creds = storage.load()
            assert creds == {"email": "a@b.com", "password": "pass123"}

    def test_load_returns_none_when_empty(self):
        with patch("tymewear_mcp.auth.keyring.keyring") as mock_kr:
            mock_kr.get_password.return_value = None
            storage = KeyringStorage()
            assert storage.load() is None

    def test_clear(self):
        with patch("tymewear_mcp.auth.keyring.keyring") as mock_kr:
            storage = KeyringStorage()
            storage.clear()
            mock_kr.delete_password.assert_called_once_with(SERVICE_NAME, "credentials")

    def test_load_returns_none_on_keyring_error(self):
        with patch("tymewear_mcp.auth.keyring.keyring") as mock_kr:
            mock_kr.get_password.side_effect = Exception("keyring broken")
            storage = KeyringStorage()
            assert storage.load() is None
