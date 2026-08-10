# Task 4 report: Compact activity analysis and integration snapshot

## Status

DONE, review findings fixed and awaiting re-review.

## Scope delivered

- Added the unregistered `tw_get_activity_analysis()` callable with the agreed
  `activity_id`, `offset`, `limit`, `channels`, and `include_location` inputs.
- Composed activity detail, epoch-first timestamps, existing insight semantics,
  WZD summary, old/new processed series, profile targets, and bounded in-memory
  FIT fallback. Every upstream read has an isolated stable capability result.
- Canonicalized common TymeWear/Garmin channel aliases and selected each sample
  independently by processed, new processed, then FIT priority. Nulls fall
  through without discarding higher-priority values for other channels.
- Retained source unit, canonical unit, scale, complete-timeline sample count,
  trusted-duration expected count, coverage, tagged availability, and exact
  source/field provenance for every selected or explicitly missing channel.
- Merged the sorted union of observed integer elapsed seconds before paging.
  The returned union is filtered to requested channels, so it never contains
  elapsed-only rows caused by unrequested channels.
- Bounded elapsed seconds against trusted activity duration with a documented
  inclusive two-second tolerance. Negative and after-duration samples are
  discarded and counted. The known `-1` and `75609` malformed values cannot
  amplify the timeline.
- Kept WZD as a separate labeled summary capability. `times_zone` remains
  classified as an elapsed axis, not a raw zone-label series. Summary metrics,
  raw samples, and detected breakpoints remain distinct.
- Reconciled categorized WZD seconds plus reported or derived uncategorized
  seconds to trusted duration with `absolute_delta_lte` and a two-second
  inclusive tolerance. No raw zone-label series is fabricated.
- Added explicit nested safe projections for identity, physiology metrics,
  model bounds, targets, thresholds, breakpoint metrics, raw channels, and
  analytic coordinates. Default output excludes account/user identifiers,
  email, device identifiers, URLs, paths, raw bytes, tokens, and coordinates.
  Explicit location opt-in allows only analytic sample coordinate fields.
- Normalized integration health into current connection, authentication, and
  ingestion states with validated checked/error fields. Sync history, replay,
  last-success history, cursor/watermark, backlog, failed items, retries, and
  next retry are explicitly unavailable or unsupported when not reported.
- Added the observed August 9 Garmin health shape (`is_connected`,
  `is_healthy`, `error`) without inferring authentication. Non-finite numeric
  check timestamps are rejected to keep the result JSON-safe.
- Contained 403, 404, 5xx, arbitrary exception, nested error, and malformed
  integration payloads without exposing raw upstream text. Only the health GET
  is called; no replay or mutation method exists or is invoked.
- Did not edit server/public registration. That remains Task 5.

## TDD evidence

### Initial RED

Command:

`uv run pytest tests/test_tools/test_activity_analysis.py tests/test_tools/test_integrations.py -q`

Result: `15 failed, 8 passed in 0.25s`. Nine failures stopped at the absent
activity-analysis module. Six integration failures demonstrated the old raw
health pass-through, generic source tags, and 5xx exception escape.

### Review-driven RED/GREEN

- A nested dict/list error payload failed with `TypeError: unhashable type:
  'dict'`; malicious checked/error-code data was then contained by validated
  scalar projections.
- The privacy regression exposed an email target and callback URL through
  nested summary fields before numeric-only projection.
- Three semantic regressions failed together before fixes: `times_zone` was
  mislabeled as raw zone labels, requested-channel paging emitted elapsed-only
  rows, and breakpoint projection was absent. The exact three passed after the
  minimal fixes: `3 passed in 0.04s`.
- The exact observed Garmin health shape plus NaN/infinity checked-time cases
  failed `4/4` before field mapping and finite-number validation, then passed
  `4 passed in 0.07s`.

### Final GREEN

`uv run pytest tests/test_tools/test_activity_analysis.py tests/test_tools/test_integrations.py -q`:
`31 passed in 0.12s`.

### Review-fix RED/GREEN

The review-fix tests were written before the production changes. The exact
aggregate RED command was:

`uv run pytest tests/test_tools/test_activity_analysis.py tests/test_tools/test_integrations.py -q`

Result: `25 failed, 31 passed in 0.37s`. The failures covered literal-boolean
location opt-in, pre-I/O channel validation, unit conflicts, malformed and
contradictory capabilities, optional capability semantics, capped coverage,
invalid zone durations, strict JSON numerics, nested source-controlled names,
malformed health payloads, and explicit state conflicts.

During the final adversarial review, two focused tests then failed for an empty
channel list and pre-projection numeric overflow (`2 failed, 3 passed`). A
separate access-key-shaped error-code probe failed once before the error-code
allowlist was applied.

An independent read-only review then found four important edge cases. Focused
tests reproduced all four (`4 failed in 0.11s`): Task 3 canonical FIT unit
spelling, malformed successful series bodies, tail-only coverage inflation,
and out-of-bound derived zone totals. The four passed after the fixes
(`4 passed in 0.04s`), and the re-review returned no Critical or Important
findings with a Ready verdict. The final aggregate focused result is
`62 passed in 0.16s`.

## Verification

- Relevant compatibility tests before the final semantic fixes:
  `135 passed in 0.80s`. The later full suite includes those same tests.
- Scoped Ruff: `All checks passed!`.
- Review-fix scoped Ruff: `All checks passed!`.
- Review-fix scoped mypy: `Success: no issues found in 3 source files`.
- Fresh full suite after all fixes:
  `PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider -q`:
  `456 passed in 4.78s`.

## Self-review

- Source failure isolation is per endpoint and per channel. Processed VE can
  coexist with new-processed/FIT HR, power, or cadence, including per-second
  null fallback.
- Collision behavior is deterministic: first non-null value by upstream record
  order, then sorted field name, within a source and integer second.
- Pagination is after the full validated observed-union merge. Channel coverage
  uses the complete selected series and trusted activity duration, not the page.
- Missing requested channels are explicit and do not infer sensor absence from
  unrelated arrays. WZD summary availability is independent of processed 404s.
- Timestamp reconciliation preserves the August 9 epoch-derived UTC/local
  values and reports the two-hour source-label conflict.
- Zone tolerance is explicitly inclusive. `times_zone` is never treated as zone
  labels, and no label series is synthesized from aggregate durations.
- Output is built from allowlisted/validated projections rather than returning
  raw activity, profile, WZD, FIT, processed, or integration payloads.
- A shared finite-number and safe-name/unit/text boundary now backs samples,
  identity, insight inputs, source metadata, timestamps, integration checks,
  provenance fields, zone keys, and confidence keys. Strict JSON serialization
  is asserted after extreme integers and NaN/infinity inputs.
- Unit metadata must prove a canonical identity conversion. Unsafe or
  unverified units and non-finite scales reject only affected samples and leave
  a stable partial `unit_conflict` or `unsafe_unit_metadata` capability.
- Safe source-unit spelling remains provenance when the upstream FIT decoder
  has already proved the canonical unit and identity scale.
- Nested availability and legacy booleans are normalized once for both tagged
  capability state and payload usability. Empty or contradictory envelopes are
  malformed, while a valid available empty series remains available.
- `raw_zone_labels` is explicitly optional for top-level availability. Invalid
  aggregate zone durations remain partial or not computed, and processed
  zone-like fields never become a fabricated raw label channel.
- Coverage and missing-count calculations use only the trusted duration range;
  accepted tolerance-tail samples remain separately counted and cannot fill an
  earlier gap. Derived zone arithmetic is rechecked against the shared numeric
  bound before it is returned.
- Integration state is current-only. It does not infer authentication from a
  generic healthy status or invent prior successful recovery, replay, cursors,
  backlog, failures, retry counts, or next-retry timing.
- Conflicting explicit health fields are reported as `conflicting`; empty or
  non-dict health payloads are malformed. Checked values are finite or valid
  aware timestamps, and only allowlisted semantic error codes are returned.
- Mutation check: changing source priority, disabling null fallback, paging a
  source before merge, retaining outliers, treating `times_zone` as labels,
  returning unrequested empty rows, leaking nested strings, or calling a
  mutation method breaks a focused assertion.

## Concerns

- FIT files above 1000 records are decoded again for each additional page to
  preserve Task 3's public maximum-page contract without changing Task 3 files.
  This is bounded by FIT size limits but costs extra CPU for long activities.
- Channel aliases and integration state mappings are deliberately conservative.
  New upstream names or units require an evidenced mapping and focused test.
- Undeclared custom channel units are rejected until a canonical identity or
  finite evidenced conversion is added. This deliberately favors an explicit
  partial result over silently combining incompatible measurements.
- Raw zone-label data remains `not_computed` because no explicitly labeled
  upstream series has been proven. WZD aggregate zones remain available.
