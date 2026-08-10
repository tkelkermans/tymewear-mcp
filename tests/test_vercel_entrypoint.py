from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from starlette.applications import Starlette


def _load_entrypoint_module(name: str):
    entrypoint = Path(__file__).resolve().parents[1] / "main.py"
    spec = importlib.util.spec_from_file_location(name, entrypoint)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vercel_entrypoint_imports_public_app_from_vercel_env(monkeypatch):
    monkeypatch.delenv("TYMEWEAR_PUBLIC_URL", raising=False)
    monkeypatch.delenv("VERCEL_PROJECT_PRODUCTION_URL", raising=False)
    monkeypatch.setenv("VERCEL_URL", "tymewear-mcp-public-abc.vercel.app")
    monkeypatch.setenv("TYMEWEAR_PUBLIC_BEARER_TOKENS", "test-public-bearer-token-32-chars")

    module = _load_entrypoint_module("vercel_entrypoint_test")

    assert isinstance(module.app, Starlette)


def test_vercel_entrypoint_fails_closed_without_public_bearer_token(monkeypatch):
    monkeypatch.delenv("TYMEWEAR_PUBLIC_URL", raising=False)
    monkeypatch.delenv("VERCEL_PROJECT_PRODUCTION_URL", raising=False)
    monkeypatch.delenv("TYMEWEAR_PUBLIC_BEARER_TOKENS", raising=False)
    monkeypatch.delenv("TYMEWEAR_PUBLIC_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("VERCEL_URL", "tymewear-mcp-public-abc.vercel.app")

    with pytest.raises(ValueError, match="TYMEWEAR_PUBLIC_BEARER_TOKENS"):
        _load_entrypoint_module("vercel_entrypoint_missing_token_test")


def test_vercel_json_does_not_rewrite_public_routes_to_the_entrypoint():
    root = Path(__file__).resolve().parents[1]
    vercel_config = json.loads((root / "vercel.json").read_text())

    assert "functions" not in vercel_config
    assert "rewrites" not in vercel_config
    assert not (root / "api" / "index.py").exists()
