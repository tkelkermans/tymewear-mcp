"""tw_auth_status tool."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from tymewear_mcp.client.http import TymeClient

logger = logging.getLogger(__name__)


async def auth_status(client: TymeClient) -> dict[str, Any]:
    """Check authentication status and token validity."""
    try:
        profile = await client.get("/v2/api/profile/")
        return {
            "status": "authenticated",
            "user_type": profile.get("user_type"),
            "subscription_tier": profile.get("subscription_tier"),
        }
    except httpx.HTTPStatusError as e:
        logger.debug("Auth check failed", exc_info=True)
        return {"status": "error", "message": f"Authentication failed (HTTP {e.response.status_code})"}
    except Exception:
        logger.debug("Auth check failed", exc_info=True)
        return {"status": "error", "message": "Authentication failed"}
