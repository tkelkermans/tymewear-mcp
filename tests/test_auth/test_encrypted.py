"""Tests for AES-256-GCM encrypted file storage."""

import os

from tymewear_mcp.auth.encrypted import EncryptedStorage


class TestEncryptedStorage:
    def test_save_and_load(self, tmp_path):
        path = tmp_path / "creds.enc"
        storage = EncryptedStorage(str(path))
        storage.save("user@test.com", "secret123")
        assert path.exists()
        raw = path.read_bytes()
        assert b"user@test.com" not in raw
        assert b"secret123" not in raw
        creds = storage.load()
        assert creds == {"email": "user@test.com", "password": "secret123"}

    def test_load_returns_none_when_no_file(self, tmp_path):
        path = tmp_path / "nonexistent.enc"
        storage = EncryptedStorage(str(path))
        assert storage.load() is None

    def test_load_returns_none_on_corrupt_file(self, tmp_path):
        path = tmp_path / "corrupt.enc"
        path.write_bytes(b"garbage data that is not valid encryption")
        storage = EncryptedStorage(str(path))
        assert storage.load() is None

    def test_clear_removes_file(self, tmp_path):
        path = tmp_path / "creds.enc"
        storage = EncryptedStorage(str(path))
        storage.save("a@b.com", "pass")
        assert path.exists()
        storage.clear()
        assert not path.exists()

    def test_file_permissions(self, tmp_path):
        path = tmp_path / "creds.enc"
        storage = EncryptedStorage(str(path))
        storage.save("a@b.com", "pass")
        mode = oct(os.stat(str(path)).st_mode & 0o777)
        assert mode == "0o600"
