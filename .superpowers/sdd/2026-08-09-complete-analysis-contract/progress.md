# SDD ledger — plan: docs/superpowers/plans/2026-08-09-complete-analysis-contract.md

- Baseline: `f2a309d`; 340 tests pass.
- Design review: per-channel source fallback, signed-URL controls, and
  preview-before-production order incorporated before implementation.
- Task 1 review round 1 at `e6457ce`: needs channel `source_unit`, scale,
  explicit sample/expected counts and coverage naming. Fix base: `e6457ce`.
- Task 1 review round 2 at `f39b9f0`: approved. Complete with commits
  `e6457ce` and `f39b9f0`; focused tests, full suite, Ruff and mypy passed.
- Task 2 review round 1 at `5286426`: needs explicit activity-type-based
  breakpoint semantics and removal of the unverified blanket measured-power
  claim. Fix base: `5286426`.
- Task 2 review round 2 at `bc254a2`: approved. Complete with commits
  `5286426` and `bc254a2`; focused tests, full suite, Ruff and mypy passed.
- Task 3 review round 1 at `85e32c7`: needs a fix because exceptions from
  `Decoder.read()` escape the tagged capability boundary and can expose raw
  SDK error text, paths, or signed-URL material. Fix base: `85e32c7`.
- Task 3 review round 2 at `0ece9de`: approved. Complete with commits
  `85e32c7` and `0ece9de`; focused tests, compatibility tests, full suite,
  Ruff, mypy, lock check, constructor/stream leak probes, and legacy-export
  checks passed.
- Task 4 implementation complete: unregistered compact activity analysis,
  per-channel processed/new/FIT fallback, bounded observed-second merge,
  separate WZD summary and breakpoint semantics, privacy-safe projections,
  and honest integration snapshots. Focused tests, scoped Ruff/mypy and the
  full 425-test suite passed. Awaiting review.
- Task 4 review round 1 at `c132a7d`: needs stricter pre-I/O inputs,
  canonical-unit conflict handling, centralized capability and JSON-safe value
  normalization, optional capability semantics, bounded zone/provenance keys,
  and malformed/conflicting integration-state handling. Fix base: `c132a7d`.
- Task 4 review round 2 fixes complete: exact aggregate RED was 25 failed and
  31 passed. Independent review found four additional important edge cases;
  their focused RED was 4 failed and final re-review reported no unresolved
  Critical or Important findings. Final focused tests are 62 passed, scoped
  Ruff/mypy are clean, and the fresh full suite is 456 passed. Server/public
  registration remains untouched for Task 5. Awaiting parent re-review.
