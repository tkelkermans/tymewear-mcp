"""System keyring credential storage."""

from __future__ import annotations

import json
import logging

import keyring

logger = logging.getLogger(__name__)

SERVICE_NAME = "tymewear-mcp"
ACCOUNT_NAME = "credentials"


class KeyringStorage:
    def save(self, email: str, password: str) -> None:
        data = json.dumps({"email": email, "password": password})
        keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, data)

    def load(self) -> dict[str, str] | None:
        try:
            raw = keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            logger.debug("Failed to load from keyring", exc_info=True)
            return None

    def clear(self) -> None:
        keyring.delete_password(SERVICE_NAME, ACCOUNT_NAME)
