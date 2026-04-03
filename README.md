# Tyme Wear MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io/) server that connects Claude to the [Tyme Wear](https://tymewear.com) breathing sensor platform. Analyze your ventilatory data, activities, thresholds, and training zones directly through Claude.

Built on the same architecture as [trainingpeaks-mcp](https://github.com/JamsusMaximus/trainingpeaks-mcp).

## What is Tyme Wear?

Tyme Wear makes the VitalPro chest strap, a wearable breathing sensor that measures ventilatory metrics (breathing rate, tidal volume, minute ventilation) alongside heart rate. It uses ventilatory thresholds (VT1, VT2) to define personalized training zones. Used by Team Visma | Lease a Bike.

## Features

- **20 MCP tools** for profile, activities, breathing data, VE thresholds, zone distributions, max values, and exports
- **Secure credential storage** via system keyring (macOS Keychain / Windows Credential Manager) with AES-256-GCM encrypted file fallback
- **Auto-authentication** with token caching and automatic re-auth on expiry
- **Smart breathing data** with summary, window, and full modes to avoid context overflow

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
| `tw_get_activities` | List activities with cursor pagination, filter by sport type (1=run, 2=bike) |
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

## Security

- Credentials stored in system keyring (preferred) or AES-256-GCM encrypted file with PBKDF2 key derivation (600K iterations, machine-specific salt)
- Tokens and credentials are **never** returned in MCP tool results (sanitized before reaching Claude)
- Environment variable auth available for CI/containers: `TYMEWEAR_EMAIL` + `TYMEWEAR_PASSWORD`
- File permissions set to 600 (owner read/write only) on encrypted credential files

## Architecture

```
tymewear-mcp/
├── src/tymewear_mcp/
│   ├── cli.py              # CLI entry point
│   ├── server.py           # MCP server + 20 tool registrations
│   ├── auth/               # Credential storage (keyring → encrypted → env)
│   ├── client/             # Async HTTP client + Pydantic models
│   └── tools/              # Tool implementations
└── tests/                  # 53 tests
```

**Tech stack:** Python 3.10+, [MCP SDK](https://github.com/modelcontextprotocol/python-sdk), httpx, Pydantic, keyring, cryptography

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v          # Run tests
ruff check src/           # Lint
mypy src/                 # Type check
```

## License

MIT
