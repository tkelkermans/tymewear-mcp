# Tyme Wear MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io/) server that connects Claude to the [Tyme Wear](https://tymewear.com) breathing sensor platform. Analyze your ventilatory data, activities, thresholds, and training zones directly through Claude.

Built on the same architecture as [trainingpeaks-mcp](https://github.com/JamsusMaximus/trainingpeaks-mcp).

## What is Tyme Wear?

Tyme Wear makes the VitalPro chest strap, a wearable breathing sensor that measures ventilatory metrics (breathing rate, tidal volume, minute ventilation) alongside heart rate. It uses ventilatory thresholds (VT1, VT2) to define personalized training zones. Used by Team Visma | Lease a Bike.

## Features

- **40 MCP tools** for profile, activities, breathing data, VE thresholds, compact per-activity analysis, activity files/detection, training plans, workout recommendations, integrations, subscription/account, resting/max physiology, and exports
- **Secure credential storage** via system keyring (macOS Keychain / Windows Credential Manager) with AES-256-GCM encrypted file fallback
- **Auto-authentication** with token caching and automatic re-auth on expiry
- **Smart breathing data** with summary, window, and full modes to avoid context overflow
- **Per-activity insights** (`tw_get_activity_insights`): detected VT1/VT2/VO2max with measured power-at-threshold, confidence scores, a truncated-test flag, and per-zone time/calories — in one call, no FIT parsing
- **Compact activity analysis** (`tw_get_activity_analysis`): reconciled timestamps, labeled summary and capability states, per-channel processed/new-processed/FIT fallback, deterministic elapsed-second merging, and pagination
- **Slim activity payloads**: `tw_get_activity` and `tw_get_activity_workout_zone_detection` drop multi-MB per-second arrays by default (opt back in with `include=[...]`)
- **Public Streamable HTTP mode** with static-bearer or OAuth auth (one-click claude.ai connector), single-tenant to the operator's Tyme Wear account

## Quick Start

### 1. Install

```bash
git clone https://github.com/tkelkermans/tymewear-mcp.git
cd tymewear-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Authenticate

```bash
tymewear-mcp auth
```

Enter your Tyme Wear email and password. Credentials are stored securely in your system keyring with an encrypted file fallback.

### 3. Configure Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "tymewear": {
      "command": "/path/to/tymewear-mcp/.venv/bin/tymewear-mcp",
      "args": ["serve"]
    }
  }
}
```

Or run `tymewear-mcp config` to generate the snippet with the correct path.

### 4. Restart Claude Desktop

The Tyme Wear tools will appear in Claude's tool list.

## CLI Commands

| Command | Description |
|---------|-------------|
| `tymewear-mcp auth` | Store Tyme Wear credentials (interactive or `--email`/`--password`) |
| `tymewear-mcp auth-status` | Check if stored credentials are valid |
| `tymewear-mcp auth-clear` | Remove stored credentials |
| `tymewear-mcp config` | Output Claude Desktop config snippet |
| `tymewear-mcp serve` | Start the MCP server (stdio transport) |
| `tymewear-mcp serve-public` | Start the public Streamable HTTP server |

## Public Internet Deployment

`serve-public` exposes a Streamable HTTP MCP endpoint for hosted deployments. It is authenticated and stateless; it is not an anonymous public API.

### Public Server

Set the public URL and one or more MCP bearer tokens through environment variables. Each bearer token must be at least 32 characters; use a generated random secret.

```bash
export TYMEWEAR_PUBLIC_URL="https://mcp.example.com/mcp"
export TYMEWEAR_PUBLIC_BEARER_TOKENS="replace-with-a-long-random-secret-of-32-plus-chars"

tymewear-mcp serve-public \
  --host 0.0.0.0 \
  --port 8000 \
  --public-url "$TYMEWEAR_PUBLIC_URL"
```

The MCP endpoint is `/mcp` by default. `/healthz` returns only `{"status":"ok"}` and does not expose customer data.

### Container

The included Dockerfile runs the public server as a non-root user. Inject secrets at runtime:

```bash
docker build -t tymewear-mcp-public .

docker run --rm -p 8000:8000 \
  -e TYMEWEAR_PUBLIC_URL="https://mcp.example.com/mcp" \
  -e TYMEWEAR_PUBLIC_BEARER_TOKENS="replace-with-a-long-random-secret-of-32-plus-chars" \
  tymewear-mcp-public
```

### Vercel

The repo also includes a Vercel ASGI entrypoint (`api/index.py`) and `vercel.json`. Link the repository to the intended Vercel project first, then configure at least `TYMEWEAR_PUBLIC_BEARER_TOKENS` in that project before deploying it. The entrypoint fails closed if the public bearer token env is absent. `TYMEWEAR_PUBLIC_URL` is recommended for production aliases, but preview deployments can derive it from Vercel's deployment URL.

```bash
TOKEN_FILE=/path/to/generated-public-bearer-token
chmod 600 "$TOKEN_FILE"
vercel link  # or: vercel link --repo for repo-level project linking
vercel env add TYMEWEAR_PUBLIC_BEARER_TOKENS production --sensitive --yes < "$TOKEN_FILE"
vercel deploy --prod
```

Keep the token file readable only by its owner; the deployment wrapper rejects token files that are accessible by group or others. Use `vercel env update TYMEWEAR_PUBLIC_BEARER_TOKENS production --sensitive --yes < "$TOKEN_FILE"` when rotating an existing token. Do not pass bearer tokens through `vercel deploy --env`, shell `echo`, or other command arguments that can end up in shell history or process listings.

The same path is wrapped by `scripts/deploy_public_vercel.sh`, which requires an existing Vercel project link, uploads the token from a file, deploys production, and runs `scripts/verify_public_endpoint.py` against the deployed MCP URL:

```bash
scripts/deploy_public_vercel.sh --token-file "$TOKEN_FILE"
```

Set `PYTHON=/path/to/python` when the verifier should run with a specific interpreter, such as the repo virtual environment.

### Automated deploy (CI/CD)

`.github/workflows/deploy.yml` runs the test suite (ruff + mypy + pytest) on every push and pull request, and — when a push to `main` passes — deploys the public MCP to Vercel production automatically, so a hosted instance stays current without running the script by hand.

To enable it, add one repository secret under **Settings → Secrets and variables → Actions**:

- **`VERCEL_TOKEN`** — a Vercel access token (Vercel → Account Settings → Tokens).

The org/project IDs are baked into the workflow (they are not secret and grant nothing without the token). The runtime `TYMEWEAR_PUBLIC_BEARER_TOKENS` env var persists in the Vercel project across deploys; rotate it with `scripts/deploy_public_vercel.sh`, not CI.

### claude.ai connector (OAuth)

The static bearer token works for header-capable clients (Claude Code: `claude mcp add --transport http <url> --header "Authorization: Bearer <token>"`). claude.ai's connector instead authenticates via OAuth, so to add the MCP there the server runs as an OAuth *protected resource*: it validates JWT access tokens from a managed provider (e.g. WorkOS AuthKit or Stytch) and enforces an email allowlist. It stays single-tenant — every authorized user reads the operator's data via server-side credentials.

Set these (sensitive) Vercel env vars to enable it:

| Var | Purpose |
|-----|---------|
| `TYMEWEAR_PUBLIC_ISSUER_URL` | Provider issuer URL (enables OAuth protected-resource mode) |
| `TYMEWEAR_OIDC_AUDIENCE` | Optional expected token `aud`; if unset, `aud` is not enforced (issuer signature + email allowlist still apply) |
| `TYMEWEAR_OIDC_JWKS_URL` | Optional explicit JWKS URL (else discovered from the issuer) |
| `TYMEWEAR_OIDC_SCOPES` | Optional scopes to advertise to the client (default `openid profile email`) |
| `TYMEWEAR_ALLOWED_EMAILS` | Comma-separated allowlist of emails permitted to connect |
| `TYMEWEAR_EMAIL` / `TYMEWEAR_PASSWORD` | The operator's Tyme Wear credentials used for all upstream calls |

Provider setup (WorkOS AuthKit example): create an app, enable Google/email login, enable Dynamic Client Registration so claude.ai can self-register, and copy the issuer URL into `TYMEWEAR_PUBLIC_ISSUER_URL`. Then add the connector in claude.ai → it discovers the provider via the server's `/.well-known/oauth-protected-resource`, registers, and runs the hosted login; only allow-listed emails are admitted.

The static `TYMEWEAR_PUBLIC_BEARER_TOKENS` path keeps working alongside OAuth (dual-mode). Without `TYMEWEAR_PUBLIC_ISSUER_URL`, OAuth is off and only the bearer path is active.

### Post-Deploy Verification

After deployment, verify the public endpoint without printing secrets:

```bash
TYMEWEAR_PUBLIC_URL="https://mcp.example.com/mcp" \
python scripts/verify_public_endpoint.py --bearer-token-file "$TOKEN_FILE"
```

The verifier checks `/healthz`, unauthenticated `/mcp` rejection, authenticated MCP `initialize`, authenticated `tools/list`, required compact-analysis/profile tools, and public security/no-cache headers.
It also confirms public deployments do not advertise raw activity reads or disk exports, and that default deployments do not advertise mutation tools.

### Public Client Authentication

Public mode is **single-tenant**: it authenticates upstream to Tyme Wear with the operator's own credentials from `TYMEWEAR_EMAIL` / `TYMEWEAR_PASSWORD` (server-side env), so every authorized caller reads the operator's data. Clients only need to prove they are allowed to connect — there is no per-request Tyme Wear token.

Header-capable clients (e.g. Claude Code) send the static gateway bearer token:

```http
Authorization: Bearer <TYMEWEAR_PUBLIC_BEARER_TOKENS entry>
```

When OAuth is enabled (`TYMEWEAR_PUBLIC_ISSUER_URL` set), clients such as the claude.ai connector instead send a provider-issued JWT obtained through the hosted login; the server validates it (signature via JWKS, issuer, optional audience) and admits only allow-listed emails. Both paths work at once (dual-mode).

> Earlier revisions required a per-request `X-Tymewear-Token`. Single-tenant mode removed it — credentials are now server-side.

### Public Data Policy

In public mode:

- Access is gated by the static bearer token and/or the OAuth email allowlist; only allow-listed identities connect.
- The operator's Tyme Wear credentials live only in server-side env (keep them in a secret manager). They are read straight from the environment — public mode does **not** touch the local keyring or encrypted credential file (those write under `$HOME`, which is read-only on serverless).
- Every tool result and stable public error passes through one non-mutating recursive privacy projection before JSON serialization. It removes non-JSON values, non-finite numbers, emails, user/account/profile UUIDs, device identifiers/serials, tokens, signed/callback/download URLs, S3 or temporary paths, heavy raw fields, and coordinates outside the explicit analysis location contract.
- `tw_get_activity_analysis` is the public compact raw-sample interface. It keeps labeled availability, capability, channel, provenance, summary, and paginated sample data. `include_location` must be the literal boolean `true`; only `raw_samples.data[*].position_lat`/`position_long` and their matching channel metadata may then survive. Home, generic, and unrelated coordinates are always removed.
- Public responses include `Cache-Control: no-store`, `Pragma: no-cache`, `X-Robots-Tag: noindex, nofollow`, HSTS for HTTPS public URLs, and baseline security headers to reduce accidental intermediary caching, indexing, and browser-side leakage of customer data.
- Profile/activity mutation tools are hidden and return `PUBLIC_MUTATIONS_DISABLED` by default. Only enable them with `--allow-mutations` or `TYMEWEAR_PUBLIC_ALLOW_MUTATIONS=true` for trusted deployments.
- CSV, FIT, and strap-file export tools return `PUBLIC_EXPORTS_DISABLED` because the local implementation writes files to disk.
- `tw_get_processed_data`, `tw_get_new_processed_data`, `tw_get_activity_logs`, and `tw_get_activity_strap_files` are hidden and return `PUBLIC_RAW_DATA_DISABLED`, even when mutations are enabled. Local stdio mode retains these tools. Compact workout-zone detection remains public.

Public tool errors are stable and do not echo upstream exception text:

| Code | Meaning |
|------|---------|
| `INVALID_TOOL_ARGUMENTS` | The request does not match the published strict tool schema |
| `UNKNOWN_TOOL` | The requested tool is not registered |
| `TYMEWEAR_UPSTREAM_TOKEN_REQUIRED` | Server-side Tyme Wear credentials are unavailable |
| `PUBLIC_TOOL_FAILED` | A public client, handler, close, or projection operation failed |
| `PUBLIC_RAW_DATA_DISABLED` | A raw/log/file-read tool is unavailable in public mode |
| `PUBLIC_EXPORTS_DISABLED` | A disk-writing export is unavailable in public mode |
| `PUBLIC_MUTATIONS_DISABLED` | A mutation is unavailable without explicit trusted-deployment opt-in |

### Production Hardening

- Terminate TLS at the edge and set `TYMEWEAR_PUBLIC_URL` to the canonical HTTPS MCP URL.
- Keep `TYMEWEAR_PUBLIC_URL` path aligned with the mounted MCP path (`/mcp` by default). Public mode rejects URL query strings, fragments, and route/path mismatches at startup.
- Inject `TYMEWEAR_PUBLIC_BEARER_TOKENS` from a secret manager, not shell history or source control. Tokens shorter than 32 characters are rejected at startup.
- Keep public deployments read-only unless you have a specific trusted-client requirement for profile/activity mutations.
- Prefer an OAuth or identity-aware proxy in front of `serve-public` for untrusted clients; rotate static bearer tokens regularly.
- When using an OAuth-capable proxy or authorization server, set `TYMEWEAR_PUBLIC_ISSUER_URL` or `--issuer-url` so MCP clients can discover protected-resource metadata.
- Public HTTP request bodies are capped at 1 MiB by default, including chunked/streamed bodies. Override with `TYMEWEAR_PUBLIC_MAX_BODY_BYTES` or `--max-body-bytes` only if a trusted deployment needs larger JSON-RPC requests.
- Keep authorization header, request body, and response body logging disabled at the reverse proxy and application platform.
- Restrict outbound network egress to Tyme Wear API hosts where your platform supports it.
- Set explicit `--allowed-host` and `--allowed-origin` values when the public URL host is not the only valid host/origin. Public mode rejects untrusted `Host` headers across all routes, refuses wildcard `*` host/origin configuration, requires allowed origins to be exact http(s) origins without paths, and requires non-localhost origins to use HTTPS.

## Available Tools

### Auth & Profile

| Tool | Description |
|------|-------------|
| `tw_auth_status` | Check authentication status and token validity |
| `tw_get_profile` | Get athlete profile: weight, height, VE targets (VT1, BP, VT2, VO2max) per sport, subscription status, external accounts |
| `tw_update_profile` | Update profile fields (weight, height, units) |

### Activities

| Tool | Description |
|------|-------------|
| `tw_get_activities` | List activities with cursor pagination and website filters for sports, activity types, search, user ID, and pro team |
| `tw_get_activity` | Full activity detail: duration, thresholds, zones, TSS, firmware, third-party links. Heavy arrays are summarised by default. Local stdio callers may use `include=[...]`; public mode still returns projected compact data |
| `tw_get_activity_analysis` | Compact read-only analysis with reconciled timestamps, summary, breakpoints, explicit capabilities, per-channel source/unit/coverage/provenance, and samples merged before pagination. `include_location=true` opts into analytic sample coordinates only |
| `tw_get_activity_insights` | Compact per-activity report: VT1/VT2/Endurance VE+HR+confidence, **measured power-at-threshold**, detected breakpoint times, per-zone time/calories, quality flags, a truncated-test flag, and VE targets — works for tests and rides |
| `tw_get_activity_status` | Algorithm processing status for an activity |
| `tw_pin_activity` | Pin/unpin an activity for threshold detection |
| `tw_get_pinned_activity` | Get currently pinned activity |
| `tw_delete_activity` | Delete an activity (irreversible) |

### Breathing Data

| Tool | Description |
|------|-------------|
| `tw_get_processed_data` | Local-only per-second breathing time-series with summary, window, and full modes; public mode uses `tw_get_activity_analysis` instead |
| `tw_get_new_processed_data` | Local-only new-format processed data when available; public mode uses `tw_get_activity_analysis` instead |

### Activity Files & Detection

| Tool | Description |
|------|-------------|
| `tw_get_activity_logs` | Get local-only read-only activity logs/events |
| `tw_get_activity_strap_files` | Get local-only strap-file metadata when available |
| `tw_export_activity_strap_files` | Export raw strap files when available |
| `tw_get_activity_workout_zone_detection` | Workout-zone detection (per-zone time/calories, VT1/VT2 VE+HR+confidence, estimated power). Point clouds are summarised by default. Local stdio callers may use `include=[...]`; public mode still returns projected compact data |

### Training Plans & Workouts

| Tool | Description |
|------|-------------|
| `tw_get_training_plan` | Get current training plan |
| `tw_get_training_plan_by_date` | Get training-plan data for a date |
| `tw_get_training_plan_by_week` | Get training-plan data for a week |
| `tw_get_training_plan_history` | Get training-plan history |
| `tw_get_training_plan_config` | Get training-plan configuration |
| `tw_get_training_plan_preview` | Get training-plan preview |
| `tw_get_workout_recommendation` | Get workout recommendation |

### Integrations & Account

| Tool | Description |
|------|-------------|
| `tw_get_integrations` | List integrations |
| `tw_get_integration` | Get integration details |
| `tw_get_integration_health` | Get integration health/status |
| `tw_get_subscription_status` | Get subscription status |
| `tw_get_subscription_plans` | Get available subscription plans |
| `tw_get_resting_max_values` | Get resting/max physiology values |

### Thresholds & Zones

| Tool | Description |
|------|-------------|
| `tw_get_ve_targets` | Current VE targets (VT1, BP, VT2, VO2max) per sport |
| `tw_compute_power_at_threshold` | Join an external power series (`[[t_seconds, watts], ...]`) to detected breakpoint times → mean watts at VT1/VT2/VO2max/FatMax. A cross-check/backfill for the power Tyme Wear already records |
| `tw_get_zone_distribution` | Zone time distribution across activities |
| `tw_tag_threshold` | Tag a ventilatory threshold (vt1, vt2, bp, vo2max) from a specific activity |
| `tw_tag_new_zone` | Tag a new-model zone value (fatmax, vt1, vt2, vo2max) from a specific activity |

### Max Values

| Tool | Description |
|------|-------------|
| `tw_get_max_value_detections` | List pending max value detection notifications |
| `tw_respond_max_value` | Accept or dismiss a detected max value |

### Exports

| Tool | Description |
|------|-------------|
| `tw_export_csv` | Export activity as CSV |
| `tw_export_csv_full` | Export full CSV with all data channels |
| `tw_export_fit` | Export activity as FIT file |

## Example Prompts

Once configured, you can ask Claude things like:

- *"Show me my last 10 bike activities"*
- *"Analyze the breathing data from my ride yesterday — what were my average VE and time in each zone?"*
- *"What are my current VT1 and VT2 thresholds for cycling?"*
- *"Pull the insights for my last threshold test — what's my power at VT2 and did it reach VO2max?"*
- *"Export my last activity as a FIT file"*
- *"Compare my VE targets between running and cycling"*
- *"Show my current training plan and workout recommendation"*
- *"Check whether my latest ride has strap files, logs, or workout-zone detection results"*
- *"List my connected integrations and subscription status"*

## Security

- Credentials stored in system keyring (preferred) or AES-256-GCM encrypted file with PBKDF2 key derivation (600K iterations, machine-specific salt)
- Tokens and credentials are **never** returned in MCP tool results (sanitized before reaching Claude)
- Environment variable auth available for CI/containers: `TYMEWEAR_EMAIL` + `TYMEWEAR_PASSWORD`
- File permissions set to 600 (owner read/write only) on encrypted credential files
- Public mode requires bearer or OAuth authentication and is single-tenant: upstream Tyme Wear auth uses server-side `TYMEWEAR_EMAIL`/`TYMEWEAR_PASSWORD` env (never the local keyring or encrypted file, which are read-only on serverless), every result is privacy-projected, and raw/file/export tools are disabled

## Architecture

```
tymewear-mcp/
├── src/tymewear_mcp/
│   ├── cli.py              # CLI entry point
│   ├── server.py           # MCP server + 40 tool registrations
│   ├── public.py           # Public Streamable HTTP server + bearer/OAuth auth
│   ├── auth/               # Credential storage (keyring → encrypted → env) + OIDC verifier (oidc.py)
│   ├── client/             # Async HTTP client + Pydantic models
│   └── tools/              # Tool implementations (incl. threshold_analysis.py, _slimming.py)
└── tests/                  # 340 tests
```

**Tech stack:** Python 3.10+, [MCP SDK](https://github.com/modelcontextprotocol/python-sdk), httpx, Pydantic, keyring, cryptography, PyJWT

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v          # Run tests
ruff check src tests      # Lint
mypy src/                 # Type check
```

## License

MIT
