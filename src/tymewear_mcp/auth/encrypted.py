"""AES-256-GCM encrypted file credential storage."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import platform
import secrets
from typing import cast

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

ITERATIONS = 600_000
KEY_LENGTH = 32
NONCE_LENGTH = 12
SALT_LENGTH = 16


def _machine_id() -> str:
    """Get a platform-specific machine identifier for key derivation salt."""
    system = platform.system()
    try:
        if system == "Darwin":
            import subprocess

            result = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split('"')[-2]
        elif system == "Linux":
            with open("/etc/machine-id") as f:
                return f.read().strip()
        elif system == "Windows":
            import winreg

            with winreg.OpenKey(  # type: ignore[attr-defined]
                winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"  # type: ignore[attr-defined]
            ) as key:
                return cast(str, winreg.QueryValueEx(key, "MachineGuid")[0])  # type: ignore[attr-defined]
    except Exception:
        logger.info("Could not read platform machine ID; using hostname-based fallback")
    return ""


def _machine_salt() -> bytes:
    parts = [platform.node(), platform.machine(), platform.system()]
    machine_id = _machine_id()
    if machine_id:
        parts.append(machine_id)
    return hashlib.sha256("|".join(parts).encode()).digest()


class EncryptedStorage:
    def __init__(self, path: str | None = None) -> None:
        if path is None:
            config_dir = os.path.expanduser("~/.config/tymewear-mcp")
            os.makedirs(config_dir, exist_ok=True)
            path = os.path.join(config_dir, "credentials.enc")
        self._path = path

    def _derive_key(self, salt: bytes) -> bytes:
        machine_salt = _machine_salt()
        combined_salt = salt + machine_salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=KEY_LENGTH,
            salt=combined_salt, iterations=ITERATIONS,
        )
        return kdf.derive(b"tymewear-mcp-credential-encryption")

    def save(self, email: str, password: str) -> None:
        salt = secrets.token_bytes(SALT_LENGTH)
        key = self._derive_key(salt)
        nonce = secrets.token_bytes(NONCE_LENGTH)
        plaintext = json.dumps({"email": email, "password": password}).encode()
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        data = salt + nonce + ciphertext
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "wb") as f:
            f.write(data)
        os.chmod(self._path, 0o600)

    def load(self) -> dict[str, str] | None:
        try:
            with open(self._path, "rb") as f:
                data = f.read()
            if len(data) < SALT_LENGTH + NONCE_LENGTH + 1:
                return None
            salt = data[:SALT_LENGTH]
            nonce = data[SALT_LENGTH:SALT_LENGTH + NONCE_LENGTH]
            ciphertext = data[SALT_LENGTH + NONCE_LENGTH:]
            key = self._derive_key(salt)
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return cast(dict[str, str], json.loads(plaintext))
        except FileNotFoundError:
            return None
        except Exception:
            logger.debug("Failed to decrypt credentials file", exc_info=True)
            return None

    def clear(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            os.remove(self._path)
