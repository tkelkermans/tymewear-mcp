#!/usr/bin/env bash
# Deploy the public Tymewear MCP server to Vercel without printing bearer secrets.

set -euo pipefail

export NO_UPDATE_NOTIFIER=1

TOKEN_FILE=""
ENV_ACTION="add"
MCP_URL=""
SKIP_VERIFY="false"

usage() {
  cat <<'USAGE'
Usage:
  scripts/deploy_public_vercel.sh --token-file PATH [options]

Options:
  --token-file PATH     File containing the public MCP bearer token.
  --env-action ACTION   Vercel env command to use: add or update. Default: add.
  --mcp-url URL         Override verifier URL. Defaults to the deployed URL plus /mcp.
  --skip-verify         Deploy only; do not run the post-deploy verifier.
  -h, --help            Show this help.

The token is passed to Vercel through stdin and never echoed.
Set PYTHON=/path/to/python to choose the verifier interpreter.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --token-file)
      if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
        echo "--token-file requires a path" >&2
        exit 2
      fi
      TOKEN_FILE="${2:-}"
      shift 2
      ;;
    --env-action)
      if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
        echo "--env-action requires add or update" >&2
        exit 2
      fi
      ENV_ACTION="${2:-}"
      shift 2
      ;;
    --mcp-url)
      if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
        echo "--mcp-url requires a URL" >&2
        exit 2
      fi
      MCP_URL="${2:-}"
      shift 2
      ;;
    --skip-verify)
      SKIP_VERIFY="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -z "$TOKEN_FILE" ]; then
  echo "missing --token-file" >&2
  usage >&2
  exit 2
fi

if [ "$ENV_ACTION" != "add" ] && [ "$ENV_ACTION" != "update" ]; then
  echo "--env-action must be add or update" >&2
  exit 2
fi

if [ ! -f "$TOKEN_FILE" ]; then
  echo "token file does not exist: $TOKEN_FILE" >&2
  exit 2
fi

if [ ! -s "$TOKEN_FILE" ]; then
  echo "token file is empty: $TOKEN_FILE" >&2
  exit 2
fi

TOKEN_MODE="$(stat -c '%a' "$TOKEN_FILE" 2>/dev/null || stat -f '%Lp' "$TOKEN_FILE" 2>/dev/null || true)"
if printf '%s' "$TOKEN_MODE" | grep -qE '^[0-7]+$'; then
  TOKEN_MODE_DEC=$((8#$TOKEN_MODE))
  if [ $((TOKEN_MODE_DEC & 077)) -ne 0 ]; then
    echo "token file must not be accessible by group or others: $TOKEN_FILE" >&2
    exit 2
  fi
fi

BEARER_TOKEN=""
IFS= read -r BEARER_TOKEN < "$TOKEN_FILE" || true
IFS=',' read -r -a BEARER_TOKENS <<< "$BEARER_TOKEN"
VALID_TOKEN_COUNT=0
for TOKEN in "${BEARER_TOKENS[@]}"; do
  TOKEN="${TOKEN#"${TOKEN%%[![:space:]]*}"}"
  TOKEN="${TOKEN%"${TOKEN##*[![:space:]]}"}"
  if [ -z "$TOKEN" ]; then
    continue
  fi
  VALID_TOKEN_COUNT=$((VALID_TOKEN_COUNT + 1))
  if [ "${#TOKEN}" -lt 32 ]; then
    echo "all bearer tokens must be at least 32 characters" >&2
    exit 2
  fi
done
if [ "$VALID_TOKEN_COUNT" -eq 0 ]; then
  echo "token file did not contain a bearer token" >&2
  exit 2
fi

if ! command -v vercel >/dev/null 2>&1; then
  echo "vercel CLI is not installed or not on PATH" >&2
  exit 2
fi

PYTHON_BIN="${PYTHON:-}"
if [ -n "$PYTHON_BIN" ]; then
  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "configured PYTHON is not executable: $PYTHON_BIN" >&2
    exit 2
  fi
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "python or python3 is not installed or not on PATH" >&2
  exit 2
fi

if [ ! -f ".vercel/project.json" ] && [ ! -f ".vercel/repo.json" ]; then
  echo "Vercel project is not linked. Run 'vercel link' or 'vercel link --repo' in this repository before deploying." >&2
  exit 2
fi

echo "Uploading TYMEWEAR_PUBLIC_BEARER_TOKENS as a sensitive Vercel production env var..."
vercel env "$ENV_ACTION" TYMEWEAR_PUBLIC_BEARER_TOKENS production --sensitive --yes --non-interactive < "$TOKEN_FILE"

echo "Deploying public Tymewear MCP to Vercel production..."
set +e
DEPLOY_OUTPUT="$(vercel deploy --prod --yes --non-interactive 2>&1)"
DEPLOY_STATUS=$?
set -e
printf '%s\n' "$DEPLOY_OUTPUT"
if [ "$DEPLOY_STATUS" -ne 0 ]; then
  exit "$DEPLOY_STATUS"
fi

DEPLOY_URL="$(printf '%s\n' "$DEPLOY_OUTPUT" | awk '/Production:/ {for (i = 1; i <= NF; i++) if ($i ~ "^https://") print $i}' | tail -n 1)"
if [ -z "$DEPLOY_URL" ]; then
  DEPLOY_URL="$(printf '%s\n' "$DEPLOY_OUTPUT" | awk '{for (i = 1; i <= NF; i++) if ($i ~ "^https://[^[:space:]/]+\\.vercel\\.app") print $i}' | tail -n 1)"
fi

if [ "$SKIP_VERIFY" = "true" ]; then
  exit 0
fi

if [ -z "$MCP_URL" ]; then
  if [ -z "$DEPLOY_URL" ]; then
    echo "could not infer deployed URL; rerun verifier with --mcp-url" >&2
    exit 1
  fi
  MCP_URL="${DEPLOY_URL%/}/mcp"
fi

echo "Verifying public MCP endpoint at $MCP_URL..."
"$PYTHON_BIN" scripts/verify_public_endpoint.py --url "$MCP_URL" --bearer-token-file "$TOKEN_FILE"
