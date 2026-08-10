# Public Tymewear MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a public Streamable HTTP deployment mode for Tymewear MCP that does not store end-customer data.

**Architecture:** Preserve the current stdio server for local use. Add a stateless Streamable HTTP ASGI app with mandatory bearer auth, request-scoped Tyme Wear upstream tokens, and public-mode export blocking.
Public deployments are read-only by default: mutation tools are hidden and blocked unless explicitly enabled by the operator.

**Tech Stack:** Python 3.10+, MCP Python SDK Streamable HTTP, Starlette, uvicorn, httpx, Pydantic, pytest, ruff, mypy.

---

### Task 1: Public Transport And Auth

**Files:**
- Create: `src/tymewear_mcp/public.py`
- Modify: `src/tymewear_mcp/server.py`
- Modify: `src/tymewear_mcp/cli.py`
- Test: `tests/test_public.py`

- [x] Add public configuration parsing and static bearer-token verification.
- [x] Build a stateless Streamable HTTP ASGI app with `/mcp` and `/healthz`.
- [x] Add `serve-public` CLI flags for `--host`, `--port`, `--public-url`, `--allowed-host`, and `--allowed-origin`.
- [x] Verify missing public bearer config fails closed.
- [x] Verify unauthenticated MCP requests return HTTP 401.

### Task 2: Request-Scoped Upstream Auth

**Files:**
- Modify: `src/tymewear_mcp/client/http.py`
- Modify: `src/tymewear_mcp/server.py`
- Test: `tests/test_client/test_http.py`
- Test: `tests/test_public.py`

- [x] Add `TymeClient(access_token=...)` support without credential sign-in.
- [x] In public mode, build a transient client from `X-Tymewear-Token` or `X-Tymewear-Authorization`.
- [x] Ensure public mode never calls `CredentialStorage.load()` or `CredentialStorage.save()`.
- [x] Close transient public clients after each tool call.

### Task 3: No Disk Exports In Public Mode

**Files:**
- Modify: `src/tymewear_mcp/server.py`
- Test: `tests/test_public.py`

- [x] Return a structured disabled response for `tw_export_csv`, `tw_export_csv_full`, `tw_export_fit`, and `tw_export_activity_strap_files` in public mode.
- [x] Verify disabled public export tools do not call export implementations or write file paths.
- [x] Hide and block profile/activity mutation tools by default in public mode.
- [x] Add explicit `TYMEWEAR_PUBLIC_ALLOW_MUTATIONS` / `--allow-mutations` opt-in for trusted deployments.

### Task 4: Documentation And Verification

**Files:**
- Modify: `README.md`
- Modify: `tasks/todo.md`

- [x] Document public setup, required headers, no-storage behavior, and deployment hardening.
- [x] Add Docker and Vercel deployment artifacts.
- [x] Add a live endpoint verifier for post-deploy checks.
- [x] Run `./.venv/bin/python -m pytest tests/test_public.py tests/test_client/test_http.py tests/test_server.py -q`.
- [x] Run `./.venv/bin/python -m pytest tests/ -q`.
- [x] Run `./.venv/bin/ruff check app.py src tests scripts`.
- [x] Run `./.venv/bin/mypy src app.py scripts/verify_public_endpoint.py`.
- [x] Add review notes to `tasks/todo.md`.

### Task 5: Public Production Deployment

**Files/State:**
- Deploy from the repository root using Vercel or an equivalent TLS host.
- Set `TYMEWEAR_PUBLIC_BEARER_TOKENS` from a secret manager.
- Set `TYMEWEAR_PUBLIC_URL` when using a stable production alias.
- Verify with `scripts/verify_public_endpoint.py`.

- [ ] Deploy the public server to an Internet-reachable TLS host.
- [ ] Run the post-deploy verifier against the live URL.
- [ ] Record the public MCP URL and verification result in `tasks/todo.md`.
