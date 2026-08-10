# Tymewear MCP Athlete Website Read Coverage Design

Date: 2026-04-28

## Purpose

Expand `tymewear-mcp` so Claude can answer the same athlete-facing questions a user can answer by browsing the Tymewear dashboard and app, while keeping this release read-first. The work covers activity data, activity files/status, training plans and workouts, integrations, account/subscription status, and physiology metrics exposed by the athlete-facing website.

This design is based on the current MCP code, existing tests, public Tymewear help pages, and the live dashboard bundle inspected on 2026-04-28.

## Scope

In scope:

- Athlete-facing read, export, and status features.
- Dashboard/app feature areas already exposed by read endpoints.
- Clear unavailable-feature results for permission-gated or missing endpoints.
- Existing write tools remain available, but the new feature work adds no new mutations.

Out of scope:

- Coach/trainer features such as My Athletes, invitations, and athlete management.
- Admin/internal features such as users, bugs/Jira, subscription admin, baseline metrics, and support tooling.
- New delete, edit, upload, move, rerun, redeem-code, connect/disconnect, push, or training-plan mutation tools.
- Browser automation or scraping. The MCP should use HTTP API endpoints only.

## Current State

The MCP currently has 20 tools covering auth status, profile, activities, activity detail/status, pinning, deletion, processed data, thresholds, zones, max-value detections, and exports.

The athlete-facing dashboard exposes additional read surfaces:

- Activity logs, strap files, FIT-style file access, and workout-zone detection.
- Training plan data by current plan, date, week, history, config, preview, and recommendation.
- Integrations list/detail/health.
- Subscription status and available plans.
- Resting max values and other physiology readouts.

Earlier local task notes also showed that processed-data and export-like endpoints can return 404-style responses for this account, and the profile may report `raw_data_access: false`. New tools must treat those as feature availability states when appropriate.

## Architecture

Keep the existing structure:

- `server.py` registers tool metadata and routes tool calls.
- `tools/_validation.py` owns Pydantic input schemas.
- `client/http.py` owns authentication, rate limiting, token refresh, raw responses, and sanitization.
- Feature modules under `src/tymewear_mcp/tools/` contain endpoint-specific behavior.

Add or extend small, focused modules:

- `activity_files.py`: activity logs, strap file metadata/download handling, activity FIT-style file access, and workout-zone detection reads.
- `training_plans.py`: current plan, plan by date/week, plan history, config, preview, and workout recommendation reads.
- `integrations.py`: integrations list, detail, and health/status.
- `account.py`: subscription status and plans.
- `physiology.py`: resting max values and any read-only threshold/zone/max-value gaps that do not fit the existing modules.

Small additions may stay in existing modules when that is clearer, but feature boundaries should remain obvious from filenames and tests.

## Tool Surface

Add these read-only tools:

- `tw_get_activity_logs`
- `tw_get_activity_strap_files`
- `tw_export_activity_strap_files`
- `tw_get_activity_workout_zone_detection`
- `tw_get_resting_max_values`
- `tw_get_training_plan`
- `tw_get_training_plan_by_date`
- `tw_get_training_plan_by_week`
- `tw_get_training_plan_history`
- `tw_get_training_plan_config`
- `tw_get_training_plan_preview`
- `tw_get_workout_recommendation`
- `tw_get_integrations`
- `tw_get_integration`
- `tw_get_integration_health`
- `tw_get_subscription_status`
- `tw_get_subscription_plans`

Improve existing tools without duplicating them:

- `tw_get_activities` should keep the existing `sport` argument for backward compatibility and add `search`, `sports`, `activity_types`, `user_id`, and `pro_team` arguments. Map `sports` to the dashboard `sport` query parameter and `activity_types` to the dashboard `type` query parameter.
- `tw_get_activity` should stay the main activity detail tool and document related tools in its description.
- `tw_get_processed_data` should keep safe `summary`, `window`, and `full` modes.
- `tw_export_fit` should keep the existing POST export path and add a fallback to the dashboard's activity FIT GET endpoint when the POST path is unavailable.
- Export tools should keep writing files through the existing export directory pattern.

## Endpoint Map

Candidate read endpoints identified from the dashboard bundle:

- `GET /v2/api/activities/{activity_id}/logs/`
- `GET /v2/api/activities/{activity_id}/strap-files/`
- `GET /api/activities/{activity_id}/fit/`
- `GET /v2/api/activities/{activity_id}/workout-zone-detection/`
- `GET /v2/api/resting-max-values/`
- `GET /v2/api/users/{user_id_or_uuid}/training-plan/`
- `GET /v2/api/users/{user_id_or_uuid}/training-plan/?date={date}`
- `GET /v2/api/users/{user_id_or_uuid}/training-plan/?week={week}`
- `GET /v2/api/users/{user_id_or_uuid}/training-plans/history/`
- `GET /v2/api/users/{user_id_or_uuid}/training-plan-config/`
- `GET /v2/api/users/{user_id_or_uuid}/training-plan-preview/`
- `GET /api/users/{user_id_or_uuid}/workout-recommendation/`
- `GET /v2/api/integrations/`
- `GET /v2/api/integrations/{integration_id_or_slug}/`
- `GET /v2/api/integrations/{integration_id_or_slug}/health/`
- `GET /v2/api/subscription/status/`
- `GET /v2/api/subscription/plans/`

Implementation should confirm required identifiers and parameter names against tests and live responses where credentials allow. If an endpoint requires `profile.id`, use the current profile id. If it requires `profile.uuid`, use the current profile uuid.

## Data Flow

Most tools should:

1. Validate inputs with Pydantic.
2. Load the current profile when a user id or uuid is needed.
3. Call one dashboard endpoint through `TymeClient`.
4. Sanitize the returned payload.
5. Return compact JSON through MCP text content.

High-volume data and binary files should avoid returning raw bytes through MCP. Binary downloads should be saved using the existing export-file pattern and return path, filename, content type, and byte count.

`tw_export_activity_strap_files` should call `GET /v2/api/activities/{activity_id}/strap-files/` as a raw response. If Tymewear returns binary content, save it as an export artifact. If it returns JSON metadata, return the sanitized JSON with `available: true`. If it returns `403` or `404`, return an availability object.

## Error Handling

Expected unavailable-feature responses should return a structured object:

```json
{
  "available": false,
  "reason": "raw_data_access_disabled",
  "status_code": 403,
  "detail": "This Tymewear account does not expose raw strap files through the API."
}
```

Use specific reasons where the client can infer them:

- `raw_data_access_disabled`
- `not_found`
- `subscription_required`
- `integration_not_configured`
- `feature_not_available`

Authentication failures should still surface as authentication errors. Unexpected 5xx server errors should not be converted into availability objects because they are operational failures, not missing features.

## Testing

Add focused unit tests for each module:

- Tool functions call the expected method/path/params.
- Binary file tools save content and return metadata.
- `403` and `404` responses become availability objects only for endpoints where absence is expected.
- Sanitization strips sensitive keys from nested payloads.
- Input schemas validate required ids, dates, weeks, and integration identifiers.

Add MCP registration tests:

- Every new tool appears in `list_tools`.
- Every new tool name is routed in `call_tool`.

Verification commands for implementation:

```bash
pytest tests/ -v
ruff check src tests
mypy src
```

## Success Criteria

- Athlete-facing read surfaces from the dashboard are represented by MCP tools or explicitly documented as out of scope.
- Claude can inspect activities, files/status, training plans, integrations, account/subscription status, and physiology readouts without using the website.
- Permission-gated Tymewear features return clear availability objects instead of confusing generic errors.
- Existing tools and tests keep working.
- The implementation passes pytest, ruff, and mypy.
