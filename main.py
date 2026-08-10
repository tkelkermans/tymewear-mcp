"""Vercel ASGI entrypoint for the public Tymewear MCP server."""

from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tymewear_mcp.public import PublicServerConfig, build_public_app  # noqa: E402

app = build_public_app(PublicServerConfig.from_env())
