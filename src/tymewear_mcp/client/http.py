"""Async HTTP client for Tyme Wear API."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from httpx import Response

logger = logging.getLogger(__name__)

BASE_URL = "https://api.tymewear.com"
RATE_LIMIT_MS = 150
DEFAULT_TIMEOUT = 30.0
SENSITIVE_KEYS = {"token", "password", "credential", "secret", "access_token", "refresh_token", "key", "authorization"}
SENSITIVE_KEY_PARTS = frozenset({"token", "password", "credential", "secret", "key", "authorization", "signature"})
REDACTED_VALUE = "[REDACTED]"


def _is_sensitive_key(key: str) -> bool:
    snake_like = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    lowered = snake_like.lower()
    if lowered in SENSITIVE_KEYS:
        return True
    parts = [part for part in re.split(r"[^a-z0-9]+", lowered) if part]
    return any(part in SENSITIVE_KEY_PARTS for part in parts)


def _sanitize_url(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.query:
        return value

    query = [
        (key, REDACTED_VALUE if _is_sensitive_key(key) else param_value)
        for key, param_value in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


class TymeClient:
    """Async HTTP client with token caching and auto re-authentication."""

    def __init__(self, credentials: dict[str, str] | None = None, *, access_token: str | None = None) -> None:
        if credentials is None and access_token is None:
            raise ValueError("TymeClient requires credentials or an access token")
        if credentials is not None and access_token is not None:
            raise ValueError("TymeClient accepts either credentials or an access token, not both")
        self._credentials = credentials
        self._token: str | None = access_token
        self._http = httpx.AsyncClient(base_url=BASE_URL, timeout=DEFAULT_TIMEOUT)
        self._last_request_time: float = 0.0
        self._auth_lock = asyncio.Lock()

    async def close(self) -> None:
        await self._http.aclose()

    async def _ensure_token(self) -> str:
        if self._token is not None:
            return self._token
        async with self._auth_lock:
            if self._token is not None:
                return self._token
            await self._signin()
            assert self._token is not None
            return self._token

    async def _signin(self) -> None:
        if self._credentials is None:
            raise RuntimeError("TymeClient access-token mode cannot sign in with stored credentials")
        logger.debug("Signing in to Tyme Wear API")
        resp = await self._http.post(
            "/api/session/signin/",
            json={"username": self._credentials["email"], "password": self._credentials["password"]},
        )
        if resp.status_code >= 400:
            resp.raise_for_status()
        data = resp.json()
        self._token = data["token"]
        logger.debug("Sign-in successful")

    async def _refresh(self) -> bool:
        try:
            resp = await self._http.post("/api/session/refresh/", headers=self._auth_headers())
            if resp.status_code == 200:
                data = resp.json()
                self._token = data.get("token", self._token)
                return True
        except Exception:
            logger.debug("Token refresh failed", exc_info=True)
        return False

    def _auth_headers(self) -> dict[str, str]:
        headers = {"X-Source": "v2", "Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Token {self._token}"
        return headers

    async def _rate_limit(self) -> None:
        now = time.monotonic()
        elapsed_ms = (now - self._last_request_time) * 1000
        if elapsed_ms < RATE_LIMIT_MS:
            await asyncio.sleep((RATE_LIMIT_MS - elapsed_ms) / 1000)
        self._last_request_time = time.monotonic()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        await self._rate_limit()
        await self._ensure_token()
        headers = self._auth_headers()
        kwargs.setdefault("headers", {}).update(headers)

        resp = await getattr(self._http, method)(path, **kwargs)

        if resp.status_code == 401:
            logger.debug("Got 401, attempting re-authentication")
            async with self._auth_lock:
                refreshed = await self._refresh()
                if not refreshed:
                    self._token = None
                    if self._credentials is None:
                        resp.raise_for_status()
                    await self._signin()
            kwargs["headers"].update(self._auth_headers())
            await self._rate_limit()
            resp = await getattr(self._http, method)(path, **kwargs)

        if resp.status_code >= 400:
            resp.raise_for_status()
        if resp.status_code == 204:
            return None
        return resp.json()

    async def _request_raw(self, method: str, path: str, **kwargs: Any) -> Response:
        """Make an authenticated request and return the raw httpx Response."""
        await self._rate_limit()
        await self._ensure_token()
        headers = self._auth_headers()
        kwargs.setdefault("headers", {}).update(headers)

        resp = await getattr(self._http, method)(path, **kwargs)

        if resp.status_code == 401:
            logger.debug("Got 401, attempting re-authentication")
            async with self._auth_lock:
                refreshed = await self._refresh()
                if not refreshed:
                    self._token = None
                    if self._credentials is None:
                        resp.raise_for_status()
                    await self._signin()
            kwargs["headers"].update(self._auth_headers())
            await self._rate_limit()
            resp = await getattr(self._http, method)(path, **kwargs)

        if resp.status_code >= 400:
            resp.raise_for_status()
        return cast(Response, resp)

    async def get(self, path: str, **kwargs: Any) -> Any:
        return await self._request("get", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> Any:
        return await self._request("post", path, **kwargs)

    async def post_raw(self, path: str, **kwargs: Any) -> Response:
        return await self._request_raw("post", path, **kwargs)

    async def get_raw(self, path: str, **kwargs: Any) -> Response:
        return await self._request_raw("get", path, **kwargs)

    @asynccontextmanager
    async def stream_raw(self, method: str, path: str, **kwargs: Any) -> AsyncIterator[Response]:
        """Stream an authenticated raw response without buffering its body."""
        await self._rate_limit()
        await self._ensure_token()
        headers = self._auth_headers()
        kwargs.setdefault("headers", {}).update(headers)

        request = self._http.build_request(method, path, **kwargs)
        resp = await self._http.send(request, stream=True)
        if resp.status_code == 401:
            await resp.aclose()
            async with self._auth_lock:
                refreshed = await self._refresh()
                if not refreshed:
                    self._token = None
                    if self._credentials is None:
                        resp.raise_for_status()
                    await self._signin()
            kwargs["headers"].update(self._auth_headers())
            await self._rate_limit()
            request = self._http.build_request(method, path, **kwargs)
            resp = await self._http.send(request, stream=True)

        try:
            if resp.status_code >= 400:
                resp.raise_for_status()
            yield resp
        finally:
            await resp.aclose()

    async def patch(self, path: str, **kwargs: Any) -> Any:
        return await self._request("patch", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> Any:
        return await self._request("delete", path, **kwargs)

    @staticmethod
    def sanitize(data: Any) -> Any:
        if isinstance(data, dict):
            return {k: TymeClient.sanitize(v) for k, v in data.items() if not _is_sensitive_key(k)}
        if isinstance(data, list):
            return [TymeClient.sanitize(item) for item in data]
        if isinstance(data, str):
            return _sanitize_url(data)
        return data
