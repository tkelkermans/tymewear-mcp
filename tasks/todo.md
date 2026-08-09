# Task 4: Compact activity analysis and integration snapshot

- [x] Inspect approved design, plan, progress, prior Task 1-3 contracts, and tests.
- [x] Add focused activity-analysis tests and verify the expected RED failure.
- [x] Add integration snapshot tests and verify the expected RED failure.
- [x] Implement per-channel elapsed-second composition with isolated fallbacks.
- [x] Implement honest, read-only Garmin integration snapshot normalization.
- [x] Verify focused tests, scoped Ruff and mypy, and the full test suite.
- [x] Self-review every Task 4 requirement and record results.
- [x] Write `task-4-report.md`, update the SDD ledger, and commit Task 4 files unsigned.

## Review

- Focused Task 4 tests: 31 passed.
- Relevant compatibility tests: 135 passed before the final semantic fixes;
  the subsequent full suite covers the same tests.
- Scoped Ruff: clean.
- Scoped mypy: clean.
- Full suite: 425 passed.
- `tw_get_activity_analysis` remains absent from server/public registration as
  required until Task 5.

## Review fix 2

- [x] Add aggregate RED coverage for strict input validation and pre-I/O failure.
- [x] Add unit sanitization/conflict and finite-scale coverage.
- [x] Add capability contradiction/malformed/empty-series coverage.
- [x] Define required versus optional top-level availability.
- [x] Bound coverage and label accepted duration-tail samples.
- [x] Reject malformed zone durations and raw zone-like processed channels.
- [x] Make every numeric and nested metadata projection JSON-safe.
- [x] Add bounded channel names/count and provenance/zone/confidence keys.
- [x] Distinguish raw-zone-label reasons by WZD capability.
- [x] Report conflicting explicit integration state fields.
- [x] Run focused GREEN, scoped static checks, compatibility and full suite.
- [x] Update report/ledger and create a separate unsigned review-fix commit.

### Review-fix verification

- Aggregate RED: 25 failed, 31 passed.
- Independent-review RED: 4 failed; re-review: Ready with no findings.
- Final focused GREEN: 62 passed.
- Scoped Ruff and mypy: clean.
- Fresh full suite: 456 passed.
- Task 5 server/public registration: untouched.
