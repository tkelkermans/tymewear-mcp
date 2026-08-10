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

# Published PR CI repair

- [x] Refresh PR #1 and reproduce the GitHub Actions failure.
- [x] Confirm that unlocked pip selected incompatible `mcp==2.0.0` while the
  verified lock retained MCP 1.x.
- [x] Add RED coverage for the MCP major-version boundary and locked CI gates.
- [x] Cap the runtime dependency at MCP 1.x and regenerate `uv.lock`.
- [x] Replace unlocked pip CI setup with immutable `setup-uv` and `uv --locked`.
- [x] Run final focused, Ruff, Mypy, lock, workflow, and full-suite verification.
- [x] Commit and push the repair, then verify PR #1 checks.

## CI repair review

- RED: 2 failed for the intended dependency and workflow-contract gaps.
- Focused GREEN: 2 passed.
- Exact locked sync: passed.
- Final focused: 2 passed.
- Ruff: clean.
- Mypy: clean across 36 source files.
- Lock check and workflow YAML parse: clean.
- Fresh full suite: 510 passed.
- Repair commit: `233ee58`.
- GitHub Actions replacement run `31362161930`: test passed in 18 seconds;
  deployment correctly skipped for the pull-request event.

# Native Vercel Git deployment

- [x] Confirm that the token requirement came from the inherited CLI deploy job,
  not the complete-analysis implementation.
- [x] Add RED coverage proving CI contains no deploy job, `VERCEL_TOKEN`, or
  `vercel deploy` command.
- [x] Keep locked Ruff, Mypy, and Pytest gates in GitHub Actions.
- [x] Remove the token-authenticated production job and document native Vercel
  Git deployment as the default.
- [x] Connect the existing Vercel project to the GitHub repository.
- [x] Run final local verification.
- [x] Commit and push the native deployment workflow, then verify GitHub CI.
- [x] Diagnose the first native preview's `/healthz` and `/mcp` 404 responses.
- [x] Move to the root Python ASGI entrypoint, remove obsolete rewrites, and
  verify the replacement native preview end to end.

## Native deployment review

- Vercel project link: GitHub `tkelkermans/tymewear-mcp`, production branch
  `main`.
- Preview uses a dedicated sensitive bearer rather than the Production bearer.
- RED: 1 failed, 2 passed; focused GREEN: 3 passed.
- Final Ruff and Mypy: clean.
- Lock and workflow YAML checks: clean.
- Fresh full suite: 511 passed.
- First native preview: build Ready, but both public routes returned 404.
- Root cause: current Vercel Python rewrites pass the rewritten `/api/index`
  path into the ASGI app; the public app intentionally serves `/healthz`,
  `/mcp`, and `/.well-known/*` instead.
- Routing-fix RED: 3 failed; focused GREEN: 3 passed.
- Final Ruff and Mypy: clean; lock check: clean; full suite: 511 passed.
- GitHub Actions run `31365215277`: passed.
- Native preview `dpl_8MzBmHUFNU4Tabj7Azmkrd5h8YyE`: Ready for commit
  `13025a3422b47b49eb4226d921857898b939ed68`.
- Authenticated Vercel preview checks: `/healthz` returned `{"status":"ok"}`;
  unauthenticated `/mcp` reached the app and returned `401` with the expected
  Bearer challenge.
