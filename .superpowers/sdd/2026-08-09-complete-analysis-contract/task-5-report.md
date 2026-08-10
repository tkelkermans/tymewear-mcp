# Task 5 report: Public privacy projection and MCP registration

## Status

DONE, verified locally. Independent re-review returned Ready with no Critical
or Important findings. Nothing was deployed or pushed.

## Scope delivered

- Added one total, non-mutating recursive public response projector. It retains
  only standard JSON scalars, lists, and string-keyed dictionaries, rejects
  non-finite or oversized numbers, bounds keys/text and recursion depth, and
  safely terminates cyclic or unsupported values without stringifying them.
- Centralized semantic privacy checks for both dictionary keys and string
  values. The public boundary removes emails, version-agnostic UUID identity
  material, device identifiers/serials, callback/signed/download/generic URIs,
  tokens and access-key-shaped credentials, bare S3 hosts, absolute or
  temporary paths, raw bytes, and source-controlled unsafe names.
- Preserved contracted activity identifiers without reopening identity leaks:
  `activity_id` remains available, while root/list activity `id` and
  `activity_uuid` aliases survive only for known activity-object tools and
  documented result paths. Nested user/account/profile identifiers remain
  removed.
- Added a tool-aware wrapper in `public.py`. Compact analysis keeps labeled
  availability, capabilities, summaries, breakpoints, channel metadata,
  provenance, and paginated samples. Heavy/raw fields are removed outside the
  compact analysis contract, including snake-case and camel-case variants.
- Made location opt-in exact. Only a validated literal `include_location=true`
  on `tw_get_activity_analysis` can retain finite numeric
  `raw_samples.data[*].position_lat`/`position_long` values and allowlisted
  matching channel metadata. Home, generic, malformed, nested metadata values,
  and coordinates from every other tool are removed.
- Added strict `GetActivityAnalysisInput` validation with a closed schema,
  required safe activity ID, strict integer offset/limit, strict boolean
  location opt-in, and nonempty bounded channel lists. Channel item length and
  safe/nonblank pattern constraints are published in JSON Schema as well as
  enforced by the runtime guard.
- Registered and dispatched `tw_get_activity_analysis` with the exact Task 4
  callable name, defaults, and arguments. Local stdio mode keeps its existing
  behavior and all raw/file tools.
- Hidden and pre-client-blocked all four public raw/log/file reads plus the
  existing four disk exports. This remains true when trusted deployments opt
  into mutations. Compact workout-zone detection remains public.
- Routed public successes and stable disabled, unknown, credential,
  validation, handler, close, and projection failures through the privacy
  boundary. Public exceptions return a stable `PUBLIC_TOOL_FAILED` result and
  logs contain only stage and exception type, never upstream text or a
  user-controlled tool name. Local exceptions still propagate.
- Updated the endpoint verifier to require compact analysis/profile tools and
  reject all public-disabled tools. Updated README tool count, privacy,
  location, raw/public limitations, stable errors, and local-versus-public
  heavy-field behavior.

## TDD evidence

### Aggregate RED

Command:

`uv run pytest -q tests/test_tools/test_privacy.py tests/test_tools/test_validation.py tests/test_server.py tests/test_public.py tests/test_public_verifier.py`

Result before production changes: `46 failed, 169 passed in 0.88s`.

The failures covered the absent projector/wrapper, strict input model,
analysis registration/dispatch, raw-read suppression, public exception
containment, and verifier contract.

### Review-driven RED/GREEN

- Semantic key/value mutations for email/credential/UUID keys, embedded POSIX
  and Windows paths, bare S3 hosts, FTP/SSH/data URIs, and AWS access keys:
  `2 failed`, then `2 passed` after centralizing `_unsafe_text`.
- Independent privacy review reproduced activity-ID loss, camel-case raw-field
  bypass, generic/start-position leakage, malformed location shapes, and an
  escaping projection exception: `5 failed`, then `5 passed`.
- Final review reproduced version-7 UUID leakage, coordinate values embedded
  in location metadata, missing published channel item constraints, and
  misleading public heavy-include descriptions: `5 failed`, then `5 passed`.

### Final focused GREEN

The same aggregate focused command completed with `223 passed in 0.53s`.

## Verification

- Scoped Ruff: `All checks passed!`.
- Scoped mypy: `Success: no issues found in 5 source files`.
- Diff whitespace check: clean.
- Fresh full suite: `uv run pytest -q`: `508 passed in 4.55s`.
- Independent read-only re-review: Ready, no Critical or Important findings.
- No deployment, external write, replay, mutation call, or push was performed.

## Strict-JSON and privacy self-review

- Projection never mutates input containers and never uses `default=str` in
  public mode. Cycles, paths, bytes, custom objects, non-string keys, huge
  integers, NaN, and infinities are omitted; the complete result serializes
  with `json.dumps(..., allow_nan=False)`.
- Semantic checks run on keys and values, including nested lists/dictionaries.
  They reject embedded private locators rather than returning partially
  redacted upstream text. UUID recognition is version-agnostic, with explicit
  activity identifier path exceptions only.
- Source-controlled names remain bounded. Availability, capability,
  provenance, units, safe metrics, and activity UUIDs retain their contracted
  shapes. Sensitive nested confidence/zone/provenance keys are projected by the
  same boundary.
- Location is a structural allowlist, not a substring exception. Channel
  entries must be dictionaries containing only documented metadata keys, and
  raw sample coordinates must be finite native integers/floats at the exact
  analysis path.
- Changing literal-boolean validation, widening a location path/shape,
  returning raw/camel-case heavy fields, allowing generic UUIDs/URIs/paths,
  skipping early-result projection, exposing a disabled raw tool, or allowing
  a public exception to escape breaks a focused assertion.
- Public mutation opt-in changes only the existing mutation tool set. It cannot
  re-enable raw reads or exports. Direct hidden calls fail before client or
  credential construction.

## Concerns

- The privacy policy is intentionally conservative. New safe identifier,
  URI-like text, raw field, or location metadata needs an explicit documented
  allowlist entry and focused test.
- Activity `id`/`activity_uuid` aliases are retained only at known activity
  object paths. A future upstream pagination envelope needs an evidenced path
  mapping before its alias will be public.
- `TYMEWEAR_UPSTREAM_TOKEN_REQUIRED` remains the established credential error
  code for compatibility, although public mode uses server-side credentials.
- Deployment verification remains intentionally deferred because Task 5 did
  not authorize deploy or push.
