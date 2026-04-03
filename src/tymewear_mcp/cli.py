# src/tymewear_mcp/cli.py
"""CLI commands for tymewear-mcp."""

from __future__ import annotations

import argparse
import getpass
import json
import sys

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
    subparsers.add_parser("help", help="Show help")

    args = parser.parse_args()

    commands = {
        "auth": cmd_auth,
        "auth-status": cmd_auth_status,
        "auth-clear": cmd_auth_clear,
        "config": cmd_config,
        "serve": cmd_serve,
        "help": lambda _: parser.print_help(),
    }

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    commands[args.command](args)
