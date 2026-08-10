# TymeWear Complete Analysis Contract Implementation Plan

> Execute with TDD. Every behavior begins with a failing focused test.

**Goal:** Produce a privacy-safe, timestamp-correct and capability-aware hosted
activity analysis, including in-memory Garmin FIT fallback.

**Architecture:** Add pure helpers for availability, timestamps, FIT decoding and
public projection. Compose existing detail, processed, WZD and export endpoints
in one additive analysis tool. Preserve existing tools with corrected semantics.

**Dependency:** `garmin-fit-sdk==21.212.0`.

## Task 1: Stable availability and processed-data semantics

**Files:** `src/tymewear_mcp/tools/_availability.py`,
`src/tymewear_mcp/tools/breathing_data.py`,
`src/tymewear_mcp/tools/_validation.py`,
`tests/test_tools/test_availability.py`,
`tests/test_tools/test_breathing_data.py`.

1. Add failing tests for tagged success/failure, dict-wrapped series, time-based
   window filtering, bounds validation and safe error reasons.
2. Implement the stable envelope while retaining `available` for compatibility.
3. Normalize common upstream wrappers and channel inventory with units/coverage.
4. Run focused tests and commit.

## Task 2: Timestamp and insight semantics

**Files:** new `src/tymewear_mcp/tools/timestamps.py`,
`src/tymewear_mcp/tools/threshold_analysis.py`,
`tests/test_tools/test_timestamps.py`,
`tests/test_tools/test_threshold_analysis.py`.

1. Add failing August 9 timestamp conflict and valid/malformed edge tests.
2. Implement epoch-first UTC/local reconciliation and consistency metadata.
3. Add units/provenance, `model_input_bounds`, raw completeness status and
   explicit breakpoint availability to insights.
4. Run focused tests and commit.

## Task 3: In-memory FIT fallback

**Files:** `pyproject.toml`, `uv.lock`, `src/tymewear_mcp/tools/exports.py`, new
`src/tymewear_mcp/tools/fit_timeseries.py`, new
`tests/test_tools/test_fit_timeseries.py`.

1. Add failing decoded-message and SDK-encoded FIT tests.
2. Factor `fetch_fit_bytes()` from export POST/dashboard GET without writing.
   Resolve JSON signed-URL responses only through strict HTTPS host allowlisting,
   embedded-credential rejection, one allowlisted redirect and response limits.
3. Implement gzip/size guards, developer-field naming, timestamps, paging,
   units, provenance and default coordinate filtering.
4. Test 403/404, malformed FIT, gzip, decoder warnings and size limits.
5. Run focused tests and commit.

## Task 4: Compact activity analysis and integration snapshot

**Files:** new `src/tymewear_mcp/tools/activity_analysis.py`,
`src/tymewear_mcp/tools/integrations.py`, new
`tests/test_tools/test_activity_analysis.py`,
`tests/test_tools/test_integrations.py`.

1. Add failing source-selection tests for mixed per-channel processed/FIT,
   FIT-only and summary-only cases, plus August 9 zone reconciliation.
2. Merge by integer elapsed second, choose each channel independently, page the
   merged timeline, and return every missing capability with a reason.
3. Normalize Garmin health into current connection/auth/ingestion snapshot and
   explicitly mark history/replay/backlog/cursor unsupported.
4. Assert no unsupported mutation method is called.
5. Run focused tests and commit.

## Task 5: Public privacy projection and MCP registration

**Files:** new `src/tymewear_mcp/tools/_privacy.py`,
`src/tymewear_mcp/server.py`, `src/tymewear_mcp/public.py`,
`tests/test_tools/test_privacy.py`, `tests/test_public.py`, `README.md`.

1. Add failing nested PII, signed URL, S3, temporary path, callback and location
   redaction tests plus tool-list/dispatch tests.
2. Apply projection to public tool results and keep raw/log/export tools disabled.
3. Register `tw_get_activity_analysis` and document contracts and limitations.
4. Run focused public/server tests and commit.

## Task 6: Verification and live acceptance

1. Run `uv run ruff check src tests`.
2. Run `uv run mypy src`.
3. Run `PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider`.
4. Run local FIT acceptance without printing personal location.
5. Deploy the exact intended revision to a Vercel preview and run hosted
   acceptance there.
6. Promote the verified revision to production, then repeat health, auth
   rejection, tool listing and the August 9 analysis-envelope smoke test.
