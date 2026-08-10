# Public Tymewear MCP Design

## Goal

Expose `tymewear-mcp` over an Internet-reachable MCP transport without storing end-customer credentials, tokens, activity exports, or other customer data on the server.

## Scope

This design adds a public deployment mode next to the existing local stdio mode. Local stdio keeps using keyring/encrypted credential storage for a single desktop user. Public mode is stateless and request-scoped: every tool call must provide a server-issued MCP bearer token plus a separate Tyme Wear upstream token in headers. The server uses the upstream token only in memory for that request and does not write customer data to disk.

## Architecture

- Keep the existing low-level MCP `Server` and tool registration as the shared protocol surface.
- Add a Streamable HTTP ASGI app backed by the official MCP `StreamableHTTPSessionManager` in stateless mode.
- Protect the MCP endpoint with mandatory bearer authentication using server-configured tokens. Tokens must be at least 32 characters, are compared with `hmac.compare_digest`, and are all checked before accepting or rejecting a request. Missing or invalid tokens receive HTTP 401 before MCP dispatch.
- Read the Tyme Wear upstream token from `X-Tymewear-Token` or `X-Tymewear-Authorization: Token <token>` on each public tool request.
- Construct a transient `TymeClient(access_token=...)` per tool call. Public mode never falls back to `CredentialStorage`.
- Disable export tools that currently write files under `~/Downloads/tymewear` when running in public mode.
- Keep public deployments read-only by default by hiding/blocking profile and activity mutation tools unless the operator explicitly opts in.

## Data Handling

Public mode does not persist end-customer data. The server stores only process configuration and transient in-memory request state. Activity data returned by Tyme Wear is relayed in MCP responses and sanitized for secret-like fields using the existing sanitizer. Export tools return a deterministic disabled response in public mode to avoid writing customer CSV/FIT/strap files. Mutation tools are hidden and blocked by default so an Internet-facing deployment starts with a read-only operational posture.
Public responses set `Cache-Control: no-store`, `Pragma: no-cache`, and baseline browser security headers to reduce accidental intermediary caching and browser-side leakage of relayed customer data.
The public app applies Host validation across all routes using the configured allowed hosts; the Streamable HTTP route also keeps MCP SDK transport security checks.

## Security Controls

- No anonymous public MCP access.
- Short public MCP bearer tokens are rejected at startup.
- Inbound MCP authentication and upstream Tyme authentication are separate headers to avoid treating downstream API tokens as MCP authorization tokens.
- Public mode is stateless to reduce session-hijacking risk.
- Host and Origin validation use MCP transport security settings.
- A health endpoint returns only service status.
- Deployment docs require TLS at the edge, private secret injection, no request-body logging, and upstream egress restricted to Tyme Wear API hosts.

## Testing

Tests cover token-only `TymeClient` behavior, public-mode startup validation, request-scoped credential loading, disabled export tools, default read-only mutation blocking, no-store public response headers, middleware authentication failures, and the existing full local-mode suite.
