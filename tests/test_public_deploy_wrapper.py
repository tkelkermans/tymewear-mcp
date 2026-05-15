from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "deploy_public_vercel.sh"


def _run_wrapper(
    tmp_path: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "NO_UPDATE_NOTIFIER": "1",
        "PYTHON": sys.executable,
    }
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=tmp_path,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )


def _write_fake_vercel(bin_dir: Path, body: str) -> Path:
    executable = bin_dir / "vercel"
    executable.write_text(f"#!/usr/bin/env bash\nset -euo pipefail\n{body}\n", encoding="utf-8")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable


def _write_fake_python(path: Path, log_file: Path) -> Path:
    path.write_text(
        f"#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' \"$*\" >> {log_file!s}\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _write_token_file(path: Path, content: str = "x" * 32 + "\n", mode: int = 0o600) -> Path:
    path.write_text(content, encoding="utf-8")
    path.chmod(mode)
    return path


def test_deploy_wrapper_requires_token_file_argument(tmp_path):
    result = _run_wrapper(tmp_path)

    assert result.returncode == 2
    assert "missing --token-file" in result.stderr


def test_deploy_wrapper_rejects_short_bearer_tokens_before_vercel_lookup(tmp_path):
    token_file = _write_token_file(tmp_path / "token", "too-short\n")

    result = _run_wrapper(tmp_path, "--token-file", str(token_file))

    assert result.returncode == 2
    assert "all bearer tokens must be at least 32 characters" in result.stderr


def test_deploy_wrapper_rejects_group_or_other_accessible_token_files(tmp_path):
    token_file = _write_token_file(tmp_path / "token", mode=0o644)

    result = _run_wrapper(tmp_path, "--token-file", str(token_file))

    assert result.returncode == 2
    assert "token file must not be accessible by group or others" in result.stderr


def test_deploy_wrapper_requires_vercel_project_link_before_vercel_calls(tmp_path):
    token_file = _write_token_file(tmp_path / "token")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "vercel-called"
    _write_fake_vercel(bin_dir, f"touch {marker!s}")

    result = _run_wrapper(
        tmp_path,
        "--token-file",
        str(token_file),
        extra_env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
    )

    assert result.returncode == 2
    assert "Vercel project is not linked" in result.stderr
    assert not marker.exists()


def test_deploy_wrapper_accepts_repo_level_vercel_link(tmp_path):
    token_file = _write_token_file(tmp_path / "token")
    (tmp_path / ".vercel").mkdir()
    (tmp_path / ".vercel" / "repo.json").write_text("{}", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_file = tmp_path / "vercel.log"
    _write_fake_vercel(
        bin_dir,
        f"""
printf '%s\\n' "$*" >> {log_file!s}
if [ "${{1:-}}" = "env" ]; then
  cat >/dev/null
elif [ "${{1:-}}" = "deploy" ]; then
  printf '%s\\n' "Production: https://tymewear-public.example.vercel.app"
fi
""",
    )

    result = _run_wrapper(
        tmp_path,
        "--token-file",
        str(token_file),
        "--skip-verify",
        extra_env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
    )

    assert result.returncode == 0
    assert "Deploying public Tymewear MCP to Vercel production" in result.stdout
    assert log_file.read_text(encoding="utf-8").splitlines() == [
        "env add TYMEWEAR_PUBLIC_BEARER_TOKENS production --sensitive --yes --non-interactive",
        "deploy --prod --yes --non-interactive",
    ]


def test_deploy_wrapper_verifies_inferred_deployment_mcp_url(tmp_path):
    token_file = _write_token_file(tmp_path / "token")
    (tmp_path / ".vercel").mkdir()
    (tmp_path / ".vercel" / "project.json").write_text("{}", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_vercel(
        bin_dir,
        """
if [ "${1:-}" = "env" ]; then
  cat >/dev/null
elif [ "${1:-}" = "deploy" ]; then
  printf '%s\\n' "Production: https://tymewear-public.example.vercel.app"
fi
""",
    )
    python_log = tmp_path / "python.log"
    fake_python = _write_fake_python(tmp_path / "python", python_log)

    result = _run_wrapper(
        tmp_path,
        "--token-file",
        str(token_file),
        extra_env={
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "PYTHON": str(fake_python),
        },
    )

    assert result.returncode == 0
    assert "Verifying public MCP endpoint at https://tymewear-public.example.vercel.app/mcp" in result.stdout
    assert python_log.read_text(encoding="utf-8").strip() == (
        "scripts/verify_public_endpoint.py --url https://tymewear-public.example.vercel.app/mcp "
        f"--bearer-token-file {token_file!s}"
    )


def test_deploy_wrapper_verifies_explicit_mcp_url_override(tmp_path):
    token_file = _write_token_file(tmp_path / "token")
    (tmp_path / ".vercel").mkdir()
    (tmp_path / ".vercel" / "project.json").write_text("{}", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_vercel(
        bin_dir,
        """
if [ "${1:-}" = "env" ]; then
  cat >/dev/null
elif [ "${1:-}" = "deploy" ]; then
  printf '%s\\n' "https://deployment-without-production-line.vercel.app"
fi
""",
    )
    python_log = tmp_path / "python.log"
    fake_python = _write_fake_python(tmp_path / "python", python_log)

    result = _run_wrapper(
        tmp_path,
        "--token-file",
        str(token_file),
        "--mcp-url",
        "https://mcp.example.com/custom-mcp",
        extra_env={
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "PYTHON": str(fake_python),
        },
    )

    assert result.returncode == 0
    assert "Verifying public MCP endpoint at https://mcp.example.com/custom-mcp" in result.stdout
    assert python_log.read_text(encoding="utf-8").strip() == (
        "scripts/verify_public_endpoint.py --url https://mcp.example.com/custom-mcp "
        f"--bearer-token-file {token_file!s}"
    )
