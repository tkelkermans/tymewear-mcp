"""Unified credential storage with keyring -> encrypted file -> env var fallback."""

from __future__ import annotations

import logging
import os

from tymewear_mcp.auth.encrypted import EncryptedStorage
from tymewear_mcp.auth.keyring import KeyringStorage

logger = logging.getLogger(__name__)


class CredentialStorage:
    def __init__(self) -> None:
        self._keyring = KeyringStorage()
        self._encrypted = EncryptedStorage()

    def load(self) -> dict[str, str] | None:
        creds = self._keyring.load()
        if creds is not None:
            logger.debug("Loaded credentials from system keyring")
            return creds
        creds = self._encrypted.load()
        if creds is not None:
            logger.debug("Loaded credentials from encrypted file")
            return creds
        email = os.environ.get("TYMEWEAR_EMAIL")
        password = os.environ.get("TYMEWEAR_PASSWORD")
        if email and password:
            logger.debug("Loaded credentials from environment variables")
            return {"email": email, "password": password}
        return None

    def save(self, email: str, password: str) -> None:
        try:
            self._keyring.save(email, password)
            logger.debug("Saved credentials to system keyring")
        except Exception:
            logger.debug("Failed to save to keyring", exc_info=True)
        self._encrypted.save(email, password)
        logger.debug("Saved credentials to encrypted file")

    def clear(self) -> None:
        try:
            self._keyring.clear()
        except Exception:
            logger.debug("Failed to clear keyring", exc_info=True)
        self._encrypted.clear()
