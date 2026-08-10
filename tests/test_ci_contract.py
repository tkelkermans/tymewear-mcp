from __future__ import annotations

import re
from pathlib import Path

import tomllib
from packaging.requirements import Requirement
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_dependency_accepts_mcp_1_and_rejects_breaking_mcp_2() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    requirements = [Requirement(item) for item in project["project"]["dependencies"]]
    mcp = next(requirement for requirement in requirements if requirement.name == "mcp")

    assert Version("1.29.0") in mcp.specifier
    assert Version("2.0.0") not in mcp.specifier


def test_ci_uses_the_checked_lock_for_install_and_every_python_gate() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    test_job_match = re.search(
        r"(?ms)^  test:\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)",
        workflow,
    )
    assert test_job_match is not None
    test_job = test_job_match.group("body")

    assert (
        "uses: astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9 # v9.0.0"
        in test_job
    )
    assert 'version: "0.12.1"' in test_job
    assert "run: uv sync --locked --extra dev" in test_job
    assert "run: uv run --locked ruff check src/ tests/" in test_job
    assert "run: uv run --locked mypy src/" in test_job
    assert "run: uv run --locked pytest -q" in test_job

    assert "pip install" not in test_job


def test_ci_delegates_deployment_to_native_vercel_git_integration() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()

    assert re.search(r"(?m)^  deploy:$", workflow) is None
    assert "VERCEL_TOKEN" not in workflow
    assert "vercel deploy" not in workflow
