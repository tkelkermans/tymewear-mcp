#!/usr/bin/env python3
"""Verify a deployed public Tymewear MCP endpoint without printing secrets."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

PROTOCOL_VERSION = "2025-06-18"
PUBLIC_DISABLED_TOOL_NAMES = {
    "tw_delete_activity",
    "tw_export_activity_strap_files",
    "tw_export_csv",
    "tw_export_csv_full",
    "tw_export_fit",
    "tw_pin_activity",
    "tw_respond_max_value",
    "tw_tag_new_zone",
    "tw_tag_threshold",
    "tw_update_profile",
}
EXPECTED_PUBLIC_SECURITY_HEADERS = {
    "cache-control": "no-store",
    "pragma": "no-cache",
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "x-robots-tag": "noindex, nofollow",
}


def _first_token(value: str | None) -> str | None:
    if value is None:
        return None
    for token in value.split(","):
        token = token.strip()
        if token:
            return token
    return None


def _token_from_file(path: str) -> str:
    try:
        contents = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"could not read bearer token file: {path}") from exc

    token = _first_token(contents)
    if token is None:
        raise ValueError(f"bearer token file did not contain a token: {path}")
    return token


def _health_url(mcp_url: str) -> str:
    parsed = urlparse(mcp_url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError("Public MCP URL must be an absolute http(s) URL")
    if parsed.params or parsed.query or parsed.fragment:
        raise ValueError("Public MCP URL must not include params, query strings, or fragments")
    return urlunparse((parsed.scheme, parsed.netloc, "/healthz", "", "", ""))


def _expects_hsts(mcp_url: str) -> bool:
    return urlparse(mcp_url).scheme == "https"


def _verify_public_security_headers(response: httpx.Response, *, expect_hsts: bool) -> None:
    for name, expected in EXPECTED_PUBLIC_SECURITY_HEADERS.items():
        actual = response.headers.get(name)
        if actual != expected:
            raise RuntimeError(f"{response.request.url} header {name!r} was {actual!r}, expected {expected!r}")

    hsts = response.headers.get("strict-transport-security")
    if expect_hsts:
        if hsts is None or "max-age=" not in hsts.lower():
            raise RuntimeError(f"{response.request.url} did not include a usable Strict-Transport-Security header")
    elif hsts is not None:
        raise RuntimeError(f"{response.request.url} included Strict-Transport-Security on a non-HTTPS URL")


def _json_rpc_body(response: httpx.Response) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("JSON-RPC response was not an object")
        return data

    if content_type.startswith("text/event-stream"):
        return _json_from_sse(response.text)

    raise ValueError(f"Unexpected response content type: {content_type}")


def _json_from_sse(body: str) -> dict[str, Any]:
    event_data: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.rstrip("\r")
        if not line:
            if event_data:
                return _loads_event_data(event_data)
            continue
        if line.startswith("data:"):
            event_data.append(line[5:].lstrip())

    if event_data:
        return _loads_event_data(event_data)
    raise ValueError("SSE response did not include a data event")


def _loads_event_data(event_data: list[str]) -> dict[str, Any]:
    data = json.loads("\n".join(event_data))
    if not isinstance(data, dict):
        raise ValueError("SSE JSON-RPC data was not an object")
    return data


def _initialize_payload() -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "public-endpoint-verifier", "version": "1.0.0"},
        },
    }


def _json_rpc_headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _exposed_disabled_public_tools(tool_names: set[str]) -> list[str]:
    return sorted(PUBLIC_DISABLED_TOOL_NAMES.intersection(tool_names))


def verify_public_endpoint(mcp_url: str, bearer_token: str, timeout: float) -> None:
    health_url = _health_url(mcp_url)
    expect_hsts = _expects_hsts(mcp_url)
    with httpx.Client(timeout=timeout) as client:
        health = client.get(health_url)
        health.raise_for_status()
        if health.json() != {"status": "ok"}:
            raise RuntimeError("/healthz did not return the expected public health payload")
        _verify_public_security_headers(health, expect_hsts=expect_hsts)
        print(f"ok healthz {health_url}")

        unauthenticated = client.post(
            mcp_url,
            json={"jsonrpc": "2.0", "id": 0, "method": "tools/list"},
            headers=_json_rpc_headers(),
        )
        if unauthenticated.status_code != 401:
            raise RuntimeError(f"unauthenticated /mcp returned {unauthenticated.status_code}, expected 401")
        _verify_public_security_headers(unauthenticated, expect_hsts=expect_hsts)
        print("ok unauthenticated /mcp rejected with 401")

        initialized = client.post(
            mcp_url,
            json=_initialize_payload(),
            headers=_json_rpc_headers(bearer_token),
        )
        initialized.raise_for_status()
        _verify_public_security_headers(initialized, expect_hsts=expect_hsts)
        initialized_body = _json_rpc_body(initialized)
        result = initialized_body.get("result", {})
        if result.get("protocolVersion") != PROTOCOL_VERSION:
            raise RuntimeError("authenticated initialize returned an unexpected protocol version")
        if result.get("serverInfo", {}).get("name") != "tymewear-mcp":
            raise RuntimeError("authenticated initialize did not return the Tymewear MCP server name")
        print("ok authenticated /mcp initialize")

        tools = client.post(
            mcp_url,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers=_json_rpc_headers(bearer_token),
        )
        tools.raise_for_status()
        _verify_public_security_headers(tools, expect_hsts=expect_hsts)
        tools_body = _json_rpc_body(tools)
        tool_names = {
            name for tool in tools_body.get("result", {}).get("tools", []) if isinstance(name := tool.get("name"), str)
        }
        if "tw_get_profile" not in tool_names:
            raise RuntimeError("authenticated tools/list did not include expected Tymewear tools")
        exposed_blocked_tools = _exposed_disabled_public_tools(tool_names)
        if exposed_blocked_tools:
            names = ", ".join(exposed_blocked_tools)
            raise RuntimeError(f"authenticated tools/list exposed public-disabled tools: {names}")
        print("ok authenticated /mcp tools/list")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=os.environ.get("TYMEWEAR_PUBLIC_URL"),
        help="Public MCP URL, for example https://example.vercel.app/mcp "
        "(defaults to TYMEWEAR_PUBLIC_URL)",
    )
    parser.add_argument(
        "--bearer-token",
        default=_first_token(os.environ.get("TYMEWEAR_PUBLIC_BEARER_TOKEN"))
        or _first_token(os.environ.get("TYMEWEAR_PUBLIC_BEARER_TOKENS")),
        help="MCP bearer token. Prefer TYMEWEAR_PUBLIC_BEARER_TOKEN or TYMEWEAR_PUBLIC_BEARER_TOKENS.",
    )
    parser.add_argument(
        "--bearer-token-file",
        help="File containing the MCP bearer token. Takes precedence over --bearer-token and env vars.",
    )
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if not args.url:
        print("missing --url or TYMEWEAR_PUBLIC_URL", file=sys.stderr)
        return 2
    try:
        bearer_token = _token_from_file(args.bearer_token_file) if args.bearer_token_file else args.bearer_token
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not bearer_token:
        print("missing --bearer-token, --bearer-token-file, or TYMEWEAR_PUBLIC_BEARER_TOKEN(S)", file=sys.stderr)
        return 2

    try:
        verify_public_endpoint(args.url, bearer_token, args.timeout)
    except Exception as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
