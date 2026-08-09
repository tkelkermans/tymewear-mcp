# Task 3 report: In-memory FIT fallback

## Status

DONE

## Scope delivered

- Pinned `garmin-fit-sdk==21.212.0` and regenerated `uv.lock`.
- Added `fetch_fit_bytes()` over the existing export POST/dashboard GET fallback
  without filesystem writes.
- Added a narrowly scoped authenticated streaming seam to `TymeClient`, so
  direct FIT responses stop at the transport boundary immediately after the
  configured compressed-response limit is crossed.
- Resolved JSON FIT responses only from the observed exact host
  `tymewear-production-files.s3.amazonaws.com` over HTTPS on port 443, with no
  userinfo or fragment. Redirects remain on that host and stop after one hop.
- Preserved legacy `export_fit()` disk behavior through the shared endpoint
  selection helper. Public analysis uses the bounded in-memory path.
- Added Garmin SDK decoding for plain and gzip FIT payloads, compressed and
  decompressed size guards, safe decoder-warning metadata, and a stable tagged
  capability when decoding fails.
- Normalized record timestamps to UTC RFC3339, derived integer elapsed seconds,
  retained declared developer-field names and units, and exposed channel units,
  scale, coverage, and FIT-field provenance.
- Added post-normalization paging with a maximum page size of 1000. Coordinates
  are absent by default and require explicit `include_location=True`, including
  developer-declared and collision-renamed coordinate fields.
- Exposed canonical units and identity scale only when the developer-declared
  source unit establishes them. Unverified values such as tidal-volume
  `vol/br` retain the source unit and report no canonical unit or scale.
- Distinguished malformed FIT from a structurally valid FIT with zero record
  messages. The latter is available with an empty sample list.

## TDD evidence

### RED 1: in-memory retrieval and signed-response controls

Command:

`uv run pytest tests/test_tools/test_fit_timeseries.py -q`

Result: `13 failed`. Every failure stopped at the intentionally absent
`fetch_fit_bytes()` boundary.

### GREEN 1

The same focused command passed: `13 passed in 0.04s`.

### RED 2: exact observed host contract

Command:

`uv run pytest tests/test_tools/test_fit_timeseries.py::TestFetchFitBytes -q`

Result: `6 failed, 11 passed`. The failures showed that the guessed domains
were accepted and the observed S3 host was rejected.

### RED/GREEN 3: direct transport bound

The direct-stream regression first failed because all three upstream chunks
were consumed instead of stopping after chunk two crossed the limit. After the
streaming seam, the focused regression passed: `1 passed in 0.05s`.

### RED/GREEN 4: decoder and normalized contract

Command:

`uv run pytest tests/test_tools/test_fit_timeseries.py::TestDecodeFitTimeseries -q`

RED: `10 failed`, all at the intentionally absent decoder module.

GREEN: `10 passed in 0.03s` using both decoded-message fixtures and FIT bytes
created by Garmin's SDK encoder.

### RED/GREEN 5: invalid URL port

The added malformed-port case first exposed raw `urlsplit().port` error text,
then passed after mapping it to the stable FIT URL validation error.

### RED/GREEN 6: review contract edges

Three targeted tests failed before implementation:

- developer coordinates leaked by declared/collision-renamed field names;
- tidal-volume `vol/br` incorrectly claimed canonical `L` and scale `1`;
- a valid zero-record FIT was reported unavailable.

The same targeted command passed after the minimal fixes: `3 passed in 0.03s`.
An added camel-case `gpsLatitude` mutation then failed by leaking the developer
coordinate and passed after identifier normalization.

Final Task 3 focused suite: `32 passed in 0.08s`.

## Verification

- Relevant compatibility tests:
  `uv run pytest tests/test_tools/test_fit_timeseries.py tests/test_tools/test_exports.py tests/test_client/test_http.py -q`:
  `54 passed in 0.48s`.
- Scoped Ruff: `All checks passed!`.
- Scoped mypy: `Success: no issues found in 3 source files`.
- Full suite, run once after focused checks:
  `PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider -q`:
  `404 passed in 4.59s`.

## Self-review

- POST 403/404 alone selects the dashboard GET fallback; unexpected POST errors
  still propagate.
- Direct responses and signed downloads both enforce declared and actual byte
  counts while streaming. Gzip expansion reads at most the decompressed limit
  plus one byte.
- Only the evidenced S3 hostname is allowed. HTTP, guessed TymeWear domains,
  lookalike suffixes, embedded credentials, fragments, non-443 and malformed
  ports, cross-host redirects, and second redirects are rejected.
- Signed URLs, FIT bytes, local paths, and raw decoder warning text are never
  returned by the normalized decoder.
- Decoder warnings with usable records produce `partial`; malformed FIT and
  decoder failure without records produce `unavailable/fit_decode_failed`.
  A structurally valid zero-record FIT remains available.
- Inventory counts use the complete decoded timeline, while paging is applied
  afterward. Developer field names and source units come from FIT field
  descriptions.
- Native, developer-declared, and collision-renamed location fields are excluded
  before inventory and paging unless explicitly requested.
- Developer channels receive an identity scale only when their declared source
  unit matches the known canonical unit. Other conversions are explicitly
  unverified.
- Mutation check: changing the host, accepting an unsafe URL/redirect, removing
  either transport or gzip bound, buffering a third direct chunk, dropping a
  developer name/unit, exposing coordinates by default, ignoring warnings, or
  moving pagination before inventory fails a focused assertion.

## Concerns

- The exact signed-download hostname is intentionally fail-closed. A verified
  vendor host change requires an explicit allowlist and test update.
- Lock regeneration also reconciled the already-declared `pyjwt[crypto]`
  metadata and the current `exceptiongroup` marker. No unrelated package
  version changed.
