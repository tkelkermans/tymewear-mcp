# Public Tymewear MCP Completion Audit

Date: 2026-05-15

## Objective

Create a public version of Tymewear MCP, expose it on the Internet, never store end-customer data, and follow best practices.

## Success Criteria

1. A public MCP server mode exists and can serve MCP over an Internet-compatible transport.
2. The server can be deployed to an Internet-reachable TLS host.
3. Public access is authenticated and not anonymous.
4. End-customer credentials, tokens, exports, and activity data are not stored server-side.
5. Public deployments are hardened with conservative defaults and operational guidance.
6. There is a post-deploy verifier that proves the live URL is reachable, authenticated, and exposing the intended public tool surface.
7. The live public deployment has been created and verified.

## Prompt-To-Artifact Checklist

| Requirement | Evidence | Status |
| --- | --- | --- |
| Public MCP server mode exists | `src/tymewear_mcp/public.py`; `tymewear-mcp serve-public` in `src/tymewear_mcp/cli.py`; public route tests in `tests/test_public.py` | Done |
| Internet-compatible MCP transport | Stateless Streamable HTTP ASGI app on `/mcp`; `/healthz` public status route; `api/index.py` Vercel ASGI entrypoint with import coverage under Vercel-style runtime env and fail-closed coverage when public bearer-token env is absent | Done |
| Deployable artifact for Internet hosting | `Dockerfile`, `.dockerignore`, `api/index.py`, `.python-version`, `uv.lock`, `vercel.json`, `.vercelignore`, `scripts/deploy_public_vercel.sh`; Vercel bundle excludes local `scripts/**` tooling; Docker and Vercel upload ignores exclude local metadata, token/secret files, tests/docs/scripts, generated caches, and exports | Done |
| TLS deployment guidance | `README.md` public deployment section requires edge TLS and canonical HTTPS `TYMEWEAR_PUBLIC_URL` | Done as guidance |
| No anonymous access | Public MCP route requires `Authorization: Bearer <server token>`; unauthenticated `/mcp` tests expect 401; Vercel entrypoint import fails when public bearer-token env is absent | Done |
| Bearer token hardening | `TYMEWEAR_PUBLIC_BEARER_TOKENS`; startup rejects tokens shorter than 32 characters; constant-time comparison via verifier logic; deployment wrapper validates token files before Vercel calls and rejects bearer-token files that are accessible by group or others | Done |
| No end-customer credential storage | Public mode uses request headers `X-Tymewear-Token` or `X-Tymewear-Authorization: Token <token>` to construct transient `TymeClient(access_token=...)`; public tests ensure credential storage load/save is not used, and invalid upstream-token errors do not echo supplied token values for either supported header | Done |
| No customer export files on server | Public mode disables CSV, full CSV, FIT, and strap-file export tools with `PUBLIC_EXPORTS_DISABLED`; tests verify disabled exports | Done |
| Read-only default for public deployments | Mutation tools are hidden and blocked by default with `PUBLIC_MUTATIONS_DISABLED`; explicit opt-in via `TYMEWEAR_PUBLIC_ALLOW_MUTATIONS` or `--allow-mutations` | Done |
| Public malformed tool-call behavior | Public mode converts Pydantic argument validation failures into a structured `INVALID_TOOL_ARGUMENTS` response without traceback or input-field echo; invalid CRLF-bearing and oversized upstream-token errors return fixed messages without token echo for both supported upstream-token header paths | Done |
| Public unknown tool behavior | Public mode returns structured `UNKNOWN_TOOL` responses before client construction or upstream-token extraction, without echoing the unknown tool name | Done |
| Customer data cache and indexing reduction | Public response middleware sets `Cache-Control: no-store`, `Pragma: no-cache`, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-Robots-Tag: noindex, nofollow`, and HSTS for HTTPS public URLs; tests cover health, authenticated, unauthenticated, invalid-host, and localhost no-HSTS responses | Done |
| Request body abuse reduction | Public ASGI middleware caps HTTP request bodies at 1 MiB by default, including chunked/streamed bodies; override is available through `TYMEWEAR_PUBLIC_MAX_BODY_BYTES` or `--max-body-bytes`; tests cover oversized declared and streamed request rejection | Done |
| Host and origin controls | Public config derives allowed hosts/origins from `TYMEWEAR_PUBLIC_URL`; Starlette `TrustedHostMiddleware` protects all routes; MCP transport security remains enabled and tests reject untrusted `Origin` while accepting configured origins; wildcard `*` host/origin configuration is rejected; hosts must be host patterns rather than URLs/paths; origins must be exact http(s) origins without paths, with HTTPS required except localhost | Done |
| Live endpoint verifier | `scripts/verify_public_endpoint.py` checks `/healthz`, unauthenticated `/mcp` rejection, authenticated `initialize`, authenticated `tools/list`, public security/no-cache headers, HSTS for HTTPS URLs, and absence of public-disabled tools; supports `--bearer-token-file`; rejects MCP URLs with params, query strings, or fragments before making requests | Done |
| Public URL route consistency | Public mode and the post-deploy verifier reject public MCP URL params, query strings, and fragments; public mode rejects paths that do not match the mounted MCP route path, and `mcp_path` is validated as a plain URL path | Done |
| Safe deployment runbook | `README.md` documents Vercel project or repo linking, `chmod 600 "$TOKEN_FILE"`, env injection using `--sensitive --yes` from a token file before deployment, the entrypoint fail-closed behavior when public bearer-token env is absent, and optional `PYTHON=/path/to/python` verifier interpreter selection; wrapper uploads the token through stdin with `--sensitive --yes --non-interactive`, disables Vercel update notifications, requires `.vercel/project.json` or `.vercel/repo.json`, extracts Vercel deployment URLs with portable awk string regex patterns, enforces owner-only token-file permissions where file mode can be inspected, and verifies from token file without printing secrets. `tests/test_public_deploy_wrapper.py` covers wrapper preflight behavior, token-file permission rejection, inferred verifier URLs, and explicit `--mcp-url` overrides with fake Vercel/Python calls. `.gitignore` excludes local Vercel metadata, ad hoc token/secret files, and export folders | Done |
| No secret material in repo artifacts | Local leakage audit searched env assignments, bearer/upstream token literals, private-key headers, API key/secret patterns, env/token/secret/credential files, and the generated bearer token value with `rg -f /private/tmp/tymewear_public_bearer_token`; only README placeholders matched, and the generated bearer token was not found. Fresh check with `rg -l --fixed-strings -f /private/tmp/tymewear_public_bearer_token .` returned no matches | Done |
| Live Internet exposure | Production Vercel deployment in `tristan-kelkermans-projects/tymewear-mcp`, configured with sensitive `TYMEWEAR_PUBLIC_BEARER_TOKENS` and `TYMEWEAR_PUBLIC_URL=https://tymewear-mcp.vercel.app/mcp`; live URL is `https://tymewear-mcp.vercel.app/mcp` | Done |
| Live verification evidence | `scripts/deploy_public_vercel.sh --token-file /private/tmp/tymewear_public_bearer_token --env-action update --mcp-url https://tymewear-mcp.vercel.app/mcp` passed health, unauthenticated rejection, authenticated initialize, and authenticated `tools/list` | Done |

## Verification Evidence

Fresh local implementation evidence:

- Focused public/server tests passed with 48 tests.
- Full local suite passed with 291 tests.
- `ruff check app.py src tests scripts` passed.
- `mypy src app.py scripts/verify_public_endpoint.py` passed.
- `git diff --check` passed.
- `tymewear-mcp serve-public --help` passed and exposes public deployment flags.
- Vercel stripped-import smoke loaded `app.app` as a Starlette app.
- Local runtime smoke returned `/healthz` 200 and unauthenticated `/mcp` 401.

Recent deployment-tooling evidence:

- Live production deployment passed on Vercel: project `tristan-kelkermans-projects/tymewear-mcp`, deployment `dpl_DRrwbrPhK1VQNRBssV5P8mHH8KXw`, production alias `https://tymewear-mcp.vercel.app`, public MCP URL `https://tymewear-mcp.vercel.app/mcp`.
- Live verifier output against the production alias:
  - `ok healthz https://tymewear-mcp.vercel.app/healthz`
  - `ok unauthenticated /mcp rejected with 401`
  - `ok authenticated /mcp initialize`
  - `ok authenticated /mcp tools/list`
- Vercel packaging fix verified: `api/index.py` is the Python ASGI entrypoint; `vercel.json` keeps only rewrites because the linked Vercel project is a Python framework project whose `@vercel/python` builder detects the entrypoint itself. Local `NO_UPDATE_NOTIFIER=1 vercel build --prod --yes --debug` completed successfully after this change.
- Final post-deploy local verification passed with `./.venv/bin/python -m pytest tests/ -q` (`293 passed`), `./.venv/bin/ruff check api src tests scripts`, `./.venv/bin/mypy src api scripts/verify_public_endpoint.py`, `git diff --check`, no fixed-string generated bearer-token repo matches, and no generated Python artifacts under `api`, `src`, `tests`, or `scripts`. Local `.vercel/.env.production.local`, `.vercel/output`, and `.vercel/python` artifacts created during deployment debugging were removed; `.vercel/project.json` remains as ignored link metadata.

- Final evidence refresh passed with `./.venv/bin/python -m pytest tests/ -q` (`291 passed`), `./.venv/bin/ruff check app.py src tests scripts`, `./.venv/bin/mypy src app.py scripts/verify_public_endpoint.py`, and `git diff --check`. Generated Python caches were removed and verified absent, the generated bearer-token fixed-string search found no repo matches, and `.vercel/project.json` / `.vercel/repo.json` are still absent.
- Vercel packaging readiness scan inspected `.vercelignore`, `vercel.json`, top-level files, and `src/` contents to confirm runtime files remain packageable while tests/docs/scripts/caches/secrets/export artifacts are ignored or excluded. A generated root `__pycache__` from entrypoint import checks was removed, then `find . -type d -name __pycache__` returned no directories, `git diff --check` passed, and the generated bearer-token fixed-string search found no repo matches.
- Vercel entrypoint runbook alignment passed with entrypoint/deploy-wrapper tests (`9 passed`), README/test pattern inspection, no fixed-string generated bearer-token repo matches, `git diff --check`, and no generated Python artifacts after cleanup. README now states that `TYMEWEAR_PUBLIC_BEARER_TOKENS` must be configured before deployment and that `app.py` fails closed if the env is absent.
- Vercel entrypoint fail-closed coverage passed with focused public/deploy/client tests (`62 passed`), full suite (`291 passed`), Ruff, mypy, `git diff --check`, no fixed-string generated bearer-token repo matches, and no generated Python artifacts after cleanup. The entrypoint test proves `app.py` fails import under Vercel-style runtime env when public bearer-token env is absent.
- Vercel entrypoint automation passed with focused public/deploy/client tests (`61 passed`), full suite (`290 passed`), Ruff, mypy, `git diff --check`, no fixed-string generated bearer-token repo matches, and no generated Python artifacts after cleanup. `tests/test_vercel_entrypoint.py` imports `app.py` with Vercel-style runtime env and asserts it exposes a Starlette ASGI app.
- Post-deploy verifier URL hardening passed with verifier tests (`11 passed`), focused public/client/deploy/verifier tests (`60 passed`), full suite (`289 passed`), Ruff, mypy, `git diff --check`, no fixed-string generated bearer-token repo matches, and no generated Python artifacts after cleanup. The verifier now rejects MCP URLs with params, query strings, or fragments before making requests.
- Public upstream-token error hardening passed with focused public/client/deploy/verifier tests (`57 passed`), full suite (`286 passed`), Ruff, mypy, `git diff --check`, no fixed-string generated bearer-token repo matches, and no generated Python artifacts after cleanup. The new tests cover invalid CRLF-bearing and oversized `X-Tymewear-Token` and `X-Tymewear-Authorization: Token ...` values returning fixed `TYMEWEAR_UPSTREAM_TOKEN_REQUIRED` errors without echoing token markers or loading credential storage.
- Vercel CLI help verification with `NO_UPDATE_NOTIFIER=1` confirmed update-notifier suppression avoids sandboxed cache-write errors, and `vercel env add --help` / `vercel env update --help` confirm stdin, `--sensitive`, and `--yes` support. Wrapper and README now use `--yes` for env add/update.
- Token-file permission runbook alignment verified with `git diff --check`, README/script pattern inspection for `chmod 600`, owner-only token-file wording, and `--sensitive --yes`, the expected no-link wrapper preflight failure against the real owner-only token file, and no fixed-string generated bearer-token repo matches.
- Fresh token-file permission hardening passed with `./.venv/bin/python -m pytest tests/test_public_deploy_wrapper.py -q` (`7 passed`), including `0644` token-file rejection before Vercel calls. The real generated bearer-token file is `-rw-------`, and the wrapper proceeds to the expected no-link preflight failure with it.
- Current full-suite verification passed with `./.venv/bin/python -m pytest tests/ -q` (`282 passed`), `./.venv/bin/ruff check app.py src tests scripts`, `./.venv/bin/mypy src app.py scripts/verify_public_endpoint.py`, `git diff --check`, no fixed-string generated bearer-token repo matches, generated bearer-token file mode `-rw-------`, and no generated Python artifacts after cleanup.
- Fresh deploy-wrapper URL verification passed with `./.venv/bin/python -m pytest tests/test_public_deploy_wrapper.py -q` (`6 passed`), including inferred Vercel deployment URL verification and explicit `--mcp-url` override verification. This caught and fixed an awk portability bug in the URL extraction path.
- Fresh focused public audit passed with `./.venv/bin/python -m pytest tests/test_public.py tests/test_public_verifier.py tests/test_public_deploy_wrapper.py tests/test_client/test_http.py -q` (`52 passed`), `./.venv/bin/ruff check app.py src tests scripts`, `./.venv/bin/mypy src app.py scripts/verify_public_endpoint.py`, `git diff --check`, the expected no-link wrapper preflight failure, no fixed-string generated bearer-token repo matches, and no generated Python artifacts after cleanup.
- `bash -n scripts/deploy_public_vercel.sh` passed.
- `./scripts/deploy_public_vercel.sh --help` passed.
- `scripts/deploy_public_vercel.sh --token-file /private/tmp/tymewear_public_bearer_token` validated local prerequisites and stopped before Vercel calls with the expected no-link message: `Vercel project is not linked. Run 'vercel link' or 'vercel link --repo' in this repository before deploying.`
- `tests/test_public_deploy_wrapper.py` passed with 4 tests covering missing token-file args, short bearer tokens, no-link failure before Vercel calls, and `.vercel/repo.json` link acceptance with a fake Vercel binary.
- `tests/test_public_verifier.py` passed with 8 tests.
- `./.venv/bin/python -m pytest tests/test_public_deploy_wrapper.py tests/test_public_verifier.py -q` passed with 12 tests.
- `ruff check app.py src tests scripts` passed.
- `mypy scripts/verify_public_endpoint.py` passed.
- `git diff --check` passed.
- Fresh `ruff check app.py src tests scripts` passed.
- `git check-ignore .vercel/project.json .env .env.production local.token local.secret exports/activity.csv __pycache__/app.cpython-312.pyc` confirmed local Vercel metadata, env files, ad hoc token/secret files, export artifacts, and generated caches are ignored.
- `.dockerignore` and `.vercelignore` were aligned to exclude `.vercel`, `*.enc`, `*.token`, `*.secret`, tests/docs/scripts, generated caches, logs, dist/build artifacts, and exports where applicable; `rg` inspection confirmed the expected patterns.
- Local leakage audit found only README placeholder token examples and no generated bearer token matches in repo files; a fresh fixed-string token search returned no repo matches.
- Generated `__pycache__`/`.pyc` files under `src`, `tests`, and `scripts` were removed, and a fresh `find` returned no generated Python artifacts.

## Current Completion Decision

The active goal is complete.

The user explicitly approved the third-party production deployment and sensitive bearer-token upload after the storage risk was stated. The public server is deployed to the TLS URL `https://tymewear-mcp.vercel.app/mcp`, the stable production alias passes the live verifier, and the final URL plus verifier result are recorded in `tasks/todo.md`.
