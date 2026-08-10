# claude.ai-Connectable OAuth for the Public Tyme Wear MCP — Design

## Context & goal

The public MCP (`https://tymewear-mcp.vercel.app/mcp`) authenticates with a static gateway bearer token **plus** a per-request `X-Tymewear-Token`. claude.ai's remote-connector flow authenticates **only via OAuth 2.1** (it self-registers with Dynamic Client Registration, then runs a hosted login). With no OAuth authorization server present, claude.ai's registration fails — the "Couldn't register with Tymewear MCP's sign-in service" error.

**Goal:** make the public MCP connectable from claude.ai's one-click connector, so the trainer (and Tristan) can add it and sign in, with the server transparently serving Tristan's Tyme Wear data.

## Decisions (approved)

1. **Single-tenant.** The server uses one stored Tyme Wear credential (Tristan's) for all upstream calls. OAuth only controls *who may connect*; everyone allowed sees Tristan's data.
2. **Managed OAuth provider.** Use a provider with first-class MCP/DCR support — **WorkOS AuthKit** (recommended; free tier) or **Stytch**. The server is a standard OIDC *protected resource*, not an auth server.
3. **Email allowlist + hosted login.** The provider hosts login (Google / email magic link); the server admits only emails in an allowlist (Tristan + trainer).

## Non-goals

- No per-user Tyme Wear accounts / account linking (single-tenant only).
- The server does **not** implement OAuth endpoints (authorize/token/register) — the provider does. No serverless OAuth state store needed.
- No change to local stdio mode.

## Architecture

Three pieces:

1. **Provider (WorkOS) = authorization server.** Hosts login, issues JWT access tokens, exposes `/.well-known/oauth-authorization-server` and a DCR `/register` endpoint that claude.ai uses. Configured by Tristan.
2. **MCP server = OAuth protected resource** (the scaffolding already exists in `public.py` behind `issuer_url`):
   - Setting `TYMEWEAR_PUBLIC_ISSUER_URL` → provider issuer turns on `create_protected_resource_routes(...)` → serves `/.well-known/oauth-protected-resource`, and `RequireAuthMiddleware` makes the `/mcp` 401 carry `WWW-Authenticate: Bearer resource_metadata="…"` pointing claude.ai at the provider.
   - Token check is done by a new **OIDC verifier** (replaces/augments `StaticBearerTokenVerifier`): validate JWT signature via the provider JWKS, check `iss`/`aud`/`exp`, extract the `email` claim, require it in the allowlist.
3. **Single-tenant upstream.** In public mode, `_get_client()` stops calling `extract_upstream_token(request)` and instead builds `TymeClient` from a server-side stored Tyme Wear credential (Vercel env). No `X-Tymewear-Token` needed.

### Dual-mode verifier (keeps Claude Code working)

`BearerAuthBackend` takes one verifier. Use a **CompositeVerifier**: first try the static bearer compare (so header-based clients like Claude Code keep working with `Authorization: Bearer <gateway-token>`); if no match, validate as a provider OIDC JWT + allowlist. This preserves both access paths.

## Components (files)

- `src/tymewear_mcp/auth/oidc.py` — **new.** `OIDCTokenVerifier`: OIDC discovery (`issuer/.well-known/openid-configuration` → `jwks_uri`), JWKS fetch + cache, JWT validation (signature, `iss`, `aud`, `exp`), allowlist check on the `email` claim. Returns `AccessToken` or `None`.
- `src/tymewear_mcp/public.py` — add `CompositeVerifier` (static + OIDC); wire it into `BearerAuthBackend`; extend `PublicServerConfig` with `issuer_url` (already present), `oidc_audience`, `allowed_emails`. Keep protected-resource routes (already gated on `issuer_url`).
- `src/tymewear_mcp/server.py` — `_get_client()` public branch builds the client from stored credentials (see below) instead of the request header. `extract_upstream_token` retained only if multi-tenant is ever revisited (otherwise unused in single-tenant).
- `src/tymewear_mcp/auth/storage.py` — reused. On Vercel it falls back to `TYMEWEAR_EMAIL`/`TYMEWEAR_PASSWORD` env. Public mode will load via `CredentialStorage().load()`.
- Tests: `tests/test_auth/test_oidc.py` (valid / expired / wrong-audience / wrong-issuer / not-allowlisted / good token), `tests/test_public.py` (composite verifier paths), `tests/test_server.py` (public `_get_client` uses stored creds).
- `pyproject.toml` — add `pyjwt[crypto]` (RS256/ES256 verification; `cryptography` already present).
- `README.md` — provider setup + env reference.

## Data flow

1. Trainer adds the connector in claude.ai → claude.ai GETs `/mcp` → `401` with `resource_metadata`.
2. claude.ai reads `/.well-known/oauth-protected-resource` (server) → finds the provider issuer → reads the provider's `/.well-known/oauth-authorization-server` → **DCR** registers a client at the provider.
3. Trainer is redirected to the provider's hosted login → signs in (Google / email magic link).
4. Provider issues a JWT access token (audience = the MCP resource) to claude.ai.
5. claude.ai calls `/mcp` with `Authorization: Bearer <jwt>` → server's OIDC verifier validates signature/claims + allowlist email.
6. Tool call → `_get_client()` builds `TymeClient` from the stored Tyme Wear credential → calls the Tyme Wear API as Tristan → returns data.

## Token verification & security

- Validate: signature (JWKS, RS256/ES256), `iss` == configured issuer, `aud` == configured resource/audience, `exp`/`nbf`, and `email` ∈ `TYMEWEAR_ALLOWED_EMAILS` (case-insensitive). Reject otherwise (→ 401/403).
- Secrets in Vercel **sensitive** env: the Tyme Wear credential and any provider secret. The static gateway bearer remains for header clients.
- Stored Tyme Wear credential: prefer `TYMEWEAR_EMAIL`/`TYMEWEAR_PASSWORD` (lets `TymeClient` auto-reauth on 401) over a bare token (which can't refresh). Documented as sensitive.
- Allowlist is the access gate; removing an email revokes access on the next token validation.

## Configuration (env vars)

| Var | Purpose |
|-----|---------|
| `TYMEWEAR_PUBLIC_ISSUER_URL` | Provider issuer (turns on OAuth protected-resource mode) |
| `TYMEWEAR_OIDC_AUDIENCE` | Expected `aud` (the MCP resource URL / configured audience) |
| `TYMEWEAR_ALLOWED_EMAILS` | Comma-separated allowlist (Tristan + trainer) |
| `TYMEWEAR_EMAIL` / `TYMEWEAR_PASSWORD` | Server-side Tyme Wear credential (sensitive) |
| `TYMEWEAR_PUBLIC_BEARER_TOKENS` | (existing) static bearer for header clients |
| `TYMEWEAR_PUBLIC_URL` | (existing) resource URL |

## Dependencies

- Add `pyjwt[crypto]`. `httpx` (discovery/JWKS) and `cryptography` already present.

## Testing

- Unit: `OIDCTokenVerifier` against a locally-signed JWT (generate an RSA keypair in the test, stub JWKS) — valid passes; expired/wrong-aud/wrong-iss/not-allowlisted/bad-signature return `None`.
- Composite verifier: static-token path and OIDC path both resolve; junk rejected.
- Server: public `_get_client()` builds a client from stored creds and never reads `X-Tymewear-Token`.
- Manual/E2E (with the live provider): add the connector in claude.ai, complete login, list tools, call `tw_get_activity_insights`.

## Effort & division of labor

- **Tristan:** create the WorkOS (or Stytch) app, enable Google/email login, provide issuer + audience; allowlist + Tyme Wear creds set as Vercel env (Claude can set non-secret ones).
- **Claude:** `oidc.py` + verifier + credential swap + config + tests + dep + README; Vercel env wiring; redeploy.
- **Together:** the live claude.ai ↔ provider ↔ server OAuth test (can't be fully exercised without the provider account).

## Risks & open items

- Exact `aud`/resource-indicator handling must match what the provider issues and what claude.ai requests (RFC 8707). Verify against the provider's MCP docs during implementation.
- DCR vs CIMD: claude.ai prefers DCR; the provider must expose a registration endpoint (WorkOS/Stytch do). If DCR is unavailable, fall back to a pre-registered client (`--client-id`).
- JWKS rotation: cache with refresh-on-unknown-kid.
