# Tyme Wear MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io/) server that connects Claude to the [Tyme Wear](https://tymewear.com) breathing sensor platform. Analyze your ventilatory data, activities, thresholds, and training zones directly through Claude.

Built on the same architecture as [trainingpeaks-mcp](https://github.com/JamsusMaximus/trainingpeaks-mcp).

## What is Tyme Wear?

Tyme Wear makes the VitalPro chest strap, a wearable breathing sensor that measures ventilatory metrics (breathing rate, tidal volume, minute ventilation) alongside heart rate. It uses ventilatory thresholds (VT1, VT2) to define personalized training zones. Used by Team Visma | Lease a Bike.

## Features

- **37 MCP tools** for profile, activities, breathing data, VE thresholds, activity files/logs/detection, training plans, workout recommendations, integrations, subscription/account, resting/max physiology, and exports
- **Secure credential storage** via system keyring (macOS Keychain / Windows Credential Manager) with AES-256-GCM encrypted file fallback
- **Auto-authentication** with token caching and automatic re-auth on expiry
- **Smart breathing data** with summary, window, and full modes to avoid context overflow
- **Public Streamable HTTP mode** for authenticated Internet deployments without storing end-customer credentials or export files

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

The repo also includes a Vercel ASGI entrypoint (`app.py`) and `vercel.json`. Link the repository to the intended Vercel project first, then configure at least `TYMEWEAR_PUBLIC_BEARER_TOKENS` in that project before deploying it. The entrypoint fails closed if the public bearer token env is absent. `TYMEWEAR_PUBLIC_URL` is recommended for production aliases, but preview deployments can derive it from Vercel's deployment URL.

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

### Post-Deploy Verification

After deployment, verify the public endpoint without printing secrets:

```bash
TYMEWEAR_PUBLIC_URL="https://mcp.example.com/mcp" \
python scripts/verify_public_endpoint.py --bearer-token-file "$TOKEN_FILE"
```

The verifier checks `/healthz`, unauthenticated `/mcp` rejection, authenticated MCP `initialize`, authenticated `tools/list`, and public security/no-cache headers.
It also confirms default public deployments do not advertise disk export or mutation tools.

### Public Client Headers

Every MCP request must include server authentication:

```http
Authorization: Bearer <TYMEWEAR_PUBLIC_BEARER_TOKENS entry>
```

Every tool request that reads Tyme Wear data must also include a request-scoped Tyme Wear upstream token:

```http
X-Tymewear-Token: <Tyme Wear API session token>
```

or:

```http
X-Tymewear-Authorization: Token <Tyme Wear API session token>
```

The Tyme Wear token is kept only in memory for that request. Public mode never reads from or writes to the local keyring, encrypted credential file, or `TYMEWEAR_EMAIL` / `TYMEWEAR_PASSWORD`.

### Public No-Storage Policy

In public mode:

- End-customer email/password credentials are not accepted or stored.
- Tyme Wear upstream tokens are not persisted.
- Activity/profile/training data is relayed in MCP responses and sanitized for secret-like fields.
- Public responses include `Cache-Control: no-store`, `Pragma: no-cache`, `X-Robots-Tag: noindex, nofollow`, HSTS for HTTPS public URLs, and baseline security headers to reduce accidental intermediary caching, indexing, and browser-side leakage of customer data.
- Profile/activity mutation tools are hidden and return `PUBLIC_MUTATIONS_DISABLED` by default. Only enable them with `--allow-mutations` or `TYMEWEAR_PUBLIC_ALLOW_MUTATIONS=true` for trusted deployments.
- CSV, FIT, and strap-file export tools return `PUBLIC_EXPORTS_DISABLED` because the local implementation writes files to disk.

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
| `tw_get_activity` | Full activity detail: duration, thresholds, zones, TSS, firmware, third-party links |
| `tw_get_activity_status` | Algorithm processing status for an activity |
| `tw_pin_activity` | Pin/unpin an activity for threshold detection |
| `tw_get_pinned_activity` | Get currently pinned activity |
| `tw_delete_activity` | Delete an activity (irreversible) |

### Breathing Data

| Tool | Description |
|------|-------------|
| `tw_get_processed_data` | Per-second breathing time-series with 3 modes: **summary** (aggregated stats — default), **window** (raw data for a time range), **full** (all records) |
| `tw_get_new_processed_data` | New-format processed data (if available for the activity) |

### Activity Files & Detection

| Tool | Description |
|------|-------------|
| `tw_get_activity_logs` | Get read-only activity logs/events |
| `tw_get_activity_strap_files` | Get strap-file metadata when available |
| `tw_export_activity_strap_files` | Export raw strap files when available |
| `tw_get_activity_workout_zone_detection` | Get workout-zone detection results |

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
- Public mode requires MCP bearer authentication and request-scoped Tyme Wear upstream tokens, bypasses local credential storage, and disables disk-writing export tools

## Architecture

```
tymewear-mcp/
├── src/tymewear_mcp/
│   ├── cli.py              # CLI entry point
│   ├── server.py           # MCP server + 37 tool registrations
│   ├── public.py           # Public Streamable HTTP server/auth helpers
│   ├── auth/               # Credential storage (keyring → encrypted → env)
│   ├── client/             # Async HTTP client + Pydantic models
│   └── tools/              # Tool implementations
└── tests/                  # 126 tests
```

**Tech stack:** Python 3.10+, [MCP SDK](https://github.com/modelcontextprotocol/python-sdk), httpx, Pydantic, keyring, cryptography

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v          # Run tests
ruff check src tests      # Lint
mypy src/                 # Type check
```

## License

MIT
