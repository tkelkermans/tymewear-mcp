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

# Task 5: Public registration and privacy boundary

- [x] Add focused RED tests for the total recursive privacy projector, including
  location scoping, nested identifiers/secrets/paths, unsupported values, and
  compact-analysis availability/provenance preservation.
- [x] Add focused RED tests for strict `GetActivityAnalysisInput` validation.
- [x] Add focused RED tests for exact server registration and dispatch.
- [x] Add focused RED tests for public-only disabled raw/file reads, all-result
  projection, stable exception containment, and unchanged local behavior.
- [x] Update the public endpoint verifier tests and capture one aggregate RED run.
- [x] Implement the minimal centralized privacy projector and public wrapper.
- [x] Implement strict validation, exact analysis registration/dispatch, and
  public-only pre-client disabling/exception containment.
- [x] Update the verifier and README public contracts.
- [x] Run focused GREEN, scoped Ruff and mypy, and a fresh full suite.
- [x] Self-review, request independent review, write `task-5-report.md`, and
  update the progress ledger.
- [x] Create one unsigned Task 5 commit without pushing.

## Task 5 review

- Aggregate RED: 46 failed, 169 passed.
- Review-driven RED groups: 2 failed, 5 failed, and 5 failed; all are GREEN.
- Final focused GREEN: 223 passed.
- Scoped Ruff and mypy: clean.
- Fresh full suite: 508 passed.
- Independent re-review: Ready with no Critical or Important findings.
- No deploy or push performed.
