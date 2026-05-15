# src/tymewear_mcp/cli.py
"""CLI commands for tymewear-mcp."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from collections.abc import Callable

from tymewear_mcp.auth.storage import CredentialStorage


def cmd_auth(args: argparse.Namespace) -> None:
    """Store credentials for Tyme Wear API."""
    email = args.email or input("Email: ")
    password = args.password or getpass.getpass("Password: ")

    storage = CredentialStorage()
    storage.save(email, password)
    print("Credentials saved successfully.")

    import asyncio

    from tymewear_mcp.client.http import TymeClient

    async def validate() -> bool:
        client = TymeClient(credentials={"email": email, "password": password})
        try:
            await client._ensure_token()
            print("Authentication verified.")
            return True
        except Exception:
            print("Warning: Could not verify credentials against the API.")
            print("Credentials saved anyway — they may work if the API is temporarily unavailable.")
            return False
        finally:
            await client.close()

    asyncio.run(validate())


def cmd_auth_status(args: argparse.Namespace) -> None:
    """Check if stored credentials are valid."""
    storage = CredentialStorage()
    creds = storage.load()
    if creds is None:
        print("No credentials found. Run: tymewear-mcp auth")
        sys.exit(1)

    print(f"Credentials found for: {creds['email']}")

    import asyncio

    from tymewear_mcp.client.http import TymeClient

    async def check() -> None:
        client = TymeClient(credentials=creds)
        try:
            await client._ensure_token()
            print("Status: authenticated")
        except Exception:
            print("Status: authentication failed")
            sys.exit(1)
        finally:
            await client.close()

    asyncio.run(check())


def cmd_auth_clear(args: argparse.Namespace) -> None:
    """Remove stored credentials."""
    storage = CredentialStorage()
    storage.clear()
    print("Credentials cleared.")


def cmd_config(args: argparse.Namespace) -> None:
    """Output Claude Desktop configuration snippet."""
    import shutil

    exe = shutil.which("tymewear-mcp")
    if exe is None:
        exe = "/path/to/.venv/bin/tymewear-mcp"

    config = {
        "mcpServers": {
            "tymewear": {
                "command": exe,
                "args": ["serve"],
            }
        }
    }
    print(json.dumps(config, indent=2))


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the MCP server."""
    from tymewear_mcp.server import run_server

    run_server()


def cmd_serve_public(args: argparse.Namespace) -> None:
    """Start the public Streamable HTTP MCP server."""
    import uvicorn

    from tymewear_mcp.public import PublicServerConfig, build_public_app

    config = PublicServerConfig.from_env(
        public_url=args.public_url,
        allowed_hosts=args.allowed_host,
        allowed_origins=args.allowed_origin,
        issuer_url=args.issuer_url,
        mcp_path=args.path,
        json_response=args.json_response,
        allow_mutations=args.allow_mutations,
        max_body_bytes=args.max_body_bytes,
    )
    app = build_public_app(config)
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


def main() -> None:
    parser = argparse.ArgumentParser(prog="tymewear-mcp", description="Tyme Wear MCP Server")
    subparsers = parser.add_subparsers(dest="command")

    auth_parser = subparsers.add_parser("auth", help="Store Tyme Wear credentials")
    auth_parser.add_argument("--email", help="Tyme Wear account email")
    auth_parser.add_argument(
        "--password",
        help="Tyme Wear account password (WARNING: visible in shell history — prefer interactive prompt)",
    )

    subparsers.add_parser("auth-status", help="Check authentication status")
    subparsers.add_parser("auth-clear", help="Remove stored credentials")
    subparsers.add_parser("config", help="Output Claude Desktop config snippet")
    subparsers.add_parser("serve", help="Start MCP server")
    public_parser = subparsers.add_parser("serve-public", help="Start public Streamable HTTP MCP server")
    public_parser.add_argument("--host", default="127.0.0.1", help="Bind host for the HTTP server")
    public_parser.add_argument("--port", type=int, default=8000, help="Bind port for the HTTP server")
    public_parser.add_argument(
        "--public-url",
        help="Canonical public MCP URL, for example https://mcp.example.com/mcp "
        "(or set TYMEWEAR_PUBLIC_URL)",
    )
    public_parser.add_argument("--path", default="/mcp", help="MCP Streamable HTTP path")
    public_parser.add_argument(
        "--issuer-url",
        help="OAuth authorization server issuer URL for protected resource metadata "
        "(or set TYMEWEAR_PUBLIC_ISSUER_URL)",
    )
    public_parser.add_argument(
        "--allowed-host",
        action="append",
        help="Allowed Host header value. Repeat for multiple hosts. Defaults to the host in --public-url.",
    )
    public_parser.add_argument(
        "--allowed-origin",
        action="append",
        help="Allowed Origin header value. Repeat for multiple origins. Defaults to the origin in --public-url.",
    )
    public_parser.add_argument(
        "--json-response",
        action="store_true",
        help="Use JSON responses for Streamable HTTP requests instead of SSE streams.",
    )
    public_parser.add_argument(
        "--allow-mutations",
        action="store_true",
        help="Expose public profile/activity mutation tools. Public deployments are read-only by default.",
    )
    public_parser.add_argument(
        "--max-body-bytes",
        type=int,
        help="Maximum accepted public HTTP request body size in bytes "
        "(or set TYMEWEAR_PUBLIC_MAX_BODY_BYTES). Defaults to 1048576.",
    )
    public_parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="uvicorn log level",
    )
    subparsers.add_parser("help", help="Show help")

    args = parser.parse_args()

    commands: dict[str, Callable[[argparse.Namespace], None]] = {
        "auth": cmd_auth,
        "auth-status": cmd_auth_status,
        "auth-clear": cmd_auth_clear,
        "config": cmd_config,
        "serve": cmd_serve,
        "serve-public": cmd_serve_public,
        "help": lambda _: parser.print_help(),
    }

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    commands[args.command](args)
