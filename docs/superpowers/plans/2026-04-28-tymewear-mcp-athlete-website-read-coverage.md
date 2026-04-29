# Tymewear MCP Athlete Website Read Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add read-first MCP coverage for athlete-facing Tymewear dashboard/app features that are not covered by the current 20 tools.

**Architecture:** Keep the existing Python MCP server pattern: Pydantic schemas in `_validation.py`, one focused module per feature area under `tools/`, and server registration/routing in `server.py`. Add a tiny shared availability helper so permission-gated website features return structured results instead of opaque HTTP failures.

**Tech Stack:** Python 3.10+, MCP Python SDK, httpx, Pydantic v2, pytest, pytest-asyncio, ruff, mypy.

---

## File Structure

- Modify: `src/tymewear_mcp/client/http.py`
  - Add `get_raw()` so export-style GET endpoints can reuse authenticated raw-response handling.
- Create: `src/tymewear_mcp/tools/_availability.py`
  - Convert expected `403`/`404` feature failures into consistent availability objects.
- Modify: `src/tymewear_mcp/tools/_validation.py`
  - Add input models for activity filters, date/week training-plan reads, integration ids, and export/status tools.
- Modify: `src/tymewear_mcp/tools/activities.py`
  - Add website-supported read filters to `get_activities()`.
- Create: `src/tymewear_mcp/tools/activity_files.py`
  - Add activity logs, strap-file metadata/export, and workout-zone detection reads.
- Modify: `src/tymewear_mcp/tools/exports.py`
  - Add FIT export fallback through the dashboard GET endpoint.
- Create: `src/tymewear_mcp/tools/training_plans.py`
  - Add current plan, plan by date/week, history, config, preview, and workout recommendation reads.
- Create: `src/tymewear_mcp/tools/integrations.py`
  - Add integrations list, detail, and health reads.
- Create: `src/tymewear_mcp/tools/account.py`
  - Add subscription status and plans reads.
- Create: `src/tymewear_mcp/tools/physiology.py`
  - Add resting max values read.
- Modify: `src/tymewear_mcp/server.py`
  - Register and route all new MCP tools.
- Modify: `README.md`
  - Document the new read-first website coverage and tool list.
- Add tests under `tests/test_client/`, `tests/test_tools/`, and `tests/test_server.py`.

---

### Task 1: Raw GET Support And Availability Helper

**Files:**
- Modify: `src/tymewear_mcp/client/http.py`
- Create: `src/tymewear_mcp/tools/_availability.py`
- Modify: `tests/test_client/test_http.py`
- Create: `tests/test_tools/test_availability.py`

- [ ] **Step 1: Write failing tests for `get_raw()`**

Append to `tests/test_client/test_http.py`:

```python
async def test_get_raw_returns_response(mock_http_client):
    client = TymeClient({"email": "test@example.com", "password": "secret"})
    client._http = mock_http_client
    client._token = "token"
    raw_response = httpx.Response(200, content=b"fit-bytes")
    mock_http_client.get = AsyncMock(return_value=raw_response)

    result = await client.get_raw("/api/activities/abc/fit/")

    assert result is raw_response
    mock_http_client.get.assert_called_once()
```

- [ ] **Step 2: Run the failing raw GET test**

Run:

```bash
pytest tests/test_client/test_http.py::test_get_raw_returns_response -v
```

Expected: FAIL with `AttributeError: 'TymeClient' object has no attribute 'get_raw'`.

- [ ] **Step 3: Implement `get_raw()`**

In `src/tymewear_mcp/client/http.py`, add this method next to `post_raw()`:

```python
    async def get_raw(self, path: str, **kwargs: Any) -> Response:
        return await self._request_raw("get", path, **kwargs)
```

- [ ] **Step 4: Run the raw GET test again**

Run:

```bash
pytest tests/test_client/test_http.py::test_get_raw_returns_response -v
```

Expected: PASS.

- [ ] **Step 5: Write failing tests for availability helpers**

Create `tests/test_tools/test_availability.py`:

```python
from __future__ import annotations

import httpx

from tymewear_mcp.tools._availability import feature_unavailable, unavailable_from_http_error


def test_feature_unavailable_shape():
    result = feature_unavailable("raw_data_access_disabled", 403, "Raw data is disabled")

    assert result == {
        "available": False,
        "reason": "raw_data_access_disabled",
        "status_code": 403,
        "detail": "Raw data is disabled",
    }


def test_unavailable_from_403_response():
    request = httpx.Request("GET", "https://api.tymewear.com/v2/api/activities/abc/strap-files/")
    response = httpx.Response(403, json={"detail": "Forbidden"}, request=request)
    error = httpx.HTTPStatusError("Forbidden", request=request, response=response)

    result = unavailable_from_http_error(error, default_reason="feature_not_available")

    assert result["available"] is False
    assert result["reason"] == "feature_not_available"
    assert result["status_code"] == 403
    assert result["detail"] == "Forbidden"


def test_unavailable_from_404_response():
    request = httpx.Request("GET", "https://api.tymewear.com/v2/api/activities/abc/workout-zone-detection/")
    response = httpx.Response(404, json={"detail": "Not found."}, request=request)
    error = httpx.HTTPStatusError("Not found", request=request, response=response)

    result = unavailable_from_http_error(error, default_reason="not_found")

    assert result["reason"] == "not_found"
    assert result["status_code"] == 404
    assert result["detail"] == "Not found."
```

- [ ] **Step 6: Run the failing availability tests**

Run:

```bash
pytest tests/test_tools/test_availability.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'tymewear_mcp.tools._availability'`.

- [ ] **Step 7: Implement availability helpers**

Create `src/tymewear_mcp/tools/_availability.py`:

```python
"""Helpers for read-only features that may be unavailable for an account."""

from __future__ import annotations

from typing import Any

import httpx


def feature_unavailable(reason: str, status_code: int, detail: str) -> dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        "status_code": status_code,
        "detail": detail,
    }


def _response_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text or response.reason_phrase
    if isinstance(data, dict):
        detail = data.get("detail") or data.get("error") or data.get("message")
        if detail is not None:
            return str(detail)
    return response.reason_phrase


def unavailable_from_http_error(
    error: httpx.HTTPStatusError,
    *,
    default_reason: str = "feature_not_available",
) -> dict[str, Any]:
    status_code = error.response.status_code
    return feature_unavailable(
        reason=default_reason,
        status_code=status_code,
        detail=_response_detail(error.response),
    )
```

- [ ] **Step 8: Run helper tests**

Run:

```bash
pytest tests/test_client/test_http.py::test_get_raw_returns_response tests/test_tools/test_availability.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

Run:

```bash
git add src/tymewear_mcp/client/http.py src/tymewear_mcp/tools/_availability.py tests/test_client/test_http.py tests/test_tools/test_availability.py
git commit -m "feat: add raw GET and availability helpers"
```

---

### Task 2: Activity Listing Website Filters

**Files:**
- Modify: `src/tymewear_mcp/tools/_validation.py`
- Modify: `src/tymewear_mcp/tools/activities.py`
- Modify: `tests/test_tools/test_activities.py`

- [ ] **Step 1: Write failing validation and tool tests**

Append to `tests/test_tools/test_activities.py`:

```python
from tymewear_mcp.tools._validation import GetActivitiesInput


class TestActivityFilters:
    def test_validation_accepts_website_filters(self):
        params = GetActivitiesInput.model_validate(
            {
                "sport": 2,
                "sports": ["2"],
                "activity_types": ["0", "6"],
                "search": "tempo",
                "user_id": "99999",
                "pro_team": "visma",
            }
        )

        assert params.sport == 2
        assert params.sports == ["2"]
        assert params.activity_types == ["0", "6"]
        assert params.search == "tempo"
        assert params.user_id == "99999"
        assert params.pro_team == "visma"

    async def test_get_activities_sends_dashboard_filters(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"next": None, "previous": None, "results": []})
        mock_client.sanitize = lambda d: d

        await get_activities(
            mock_client,
            user_id=99999,
            sport=2,
            sports=["1"],
            activity_types=["0", "6"],
            search="tempo",
            limit=25,
            cursor="abc",
            requested_user_id="12345",
            pro_team="visma",
        )

        mock_client.get.assert_called_once_with(
            "/v2/api/activities-cursor/",
            params={
                "user": "12345",
                "limit": 25,
                "sport": ["1"],
                "type": ["0", "6"],
                "search": "tempo",
                "cursor": "abc",
                "pro_team": "visma",
            },
        )

    async def test_legacy_sport_maps_to_sport_filter(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"next": None, "previous": None, "results": []})
        mock_client.sanitize = lambda d: d

        await get_activities(mock_client, user_id=99999, sport=2)

        mock_client.get.assert_called_once_with(
            "/v2/api/activities-cursor/",
            params={"user": 99999, "limit": 50, "sport": ["2"]},
        )
```

- [ ] **Step 2: Run failing activity filter tests**

Run:

```bash
pytest tests/test_tools/test_activities.py::TestActivityFilters -v
```

Expected: FAIL because `GetActivitiesInput` and `get_activities()` do not support the new fields.

- [ ] **Step 3: Extend `GetActivitiesInput`**

In `src/tymewear_mcp/tools/_validation.py`, replace `GetActivitiesInput` with:

```python
class GetActivitiesInput(BaseModel):
    sport: int | None = Field(default=None, description="Legacy sport filter: 1=run, 2=bike")
    sports: list[str] | None = Field(default=None, description="Website sport filters")
    activity_types: list[str] | None = Field(default=None, description="Website activity type filters")
    search: str | None = Field(default=None, description="Search activity names and metadata")
    user_id: str | None = Field(default=None, description="Optional user id override for admin/trainer contexts")
    pro_team: str | None = Field(default=None, description="Optional pro team filter")
    limit: int = Field(default=50, le=1000, gt=0, description="Max results to return")
    cursor: str | None = Field(default=None, description="Pagination cursor from previous response")
```

- [ ] **Step 4: Extend `get_activities()`**

In `src/tymewear_mcp/tools/activities.py`, replace `get_activities()` with:

```python
async def get_activities(
    client: TymeClient,
    user_id: int,
    sport: int | None = None,
    limit: int = 50,
    cursor: str | None = None,
    sports: list[str] | None = None,
    activity_types: list[str] | None = None,
    search: str | None = None,
    requested_user_id: str | None = None,
    pro_team: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"user": requested_user_id or user_id, "limit": limit}
    sport_filters = sports or ([str(sport)] if sport is not None else None)
    if sport_filters:
        params["sport"] = sport_filters
    if activity_types:
        params["type"] = activity_types
    if search:
        params["search"] = search
    if cursor is not None:
        params["cursor"] = cursor
    if pro_team:
        params["pro_team"] = pro_team
    data = await client.get("/v2/api/activities-cursor/", params=params)
    return client.sanitize(data)
```

- [ ] **Step 5: Run activity tests**

Run:

```bash
pytest tests/test_tools/test_activities.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/tymewear_mcp/tools/_validation.py src/tymewear_mcp/tools/activities.py tests/test_tools/test_activities.py
git commit -m "feat: add Tymewear activity listing filters"
```

---

### Task 3: Activity Files, Logs, And Workout-Zone Detection

**Files:**
- Create: `src/tymewear_mcp/tools/activity_files.py`
- Modify: `src/tymewear_mcp/tools/_validation.py`
- Create: `tests/test_tools/test_activity_files.py`

- [ ] **Step 1: Write failing activity file tests**

Create `tests/test_tools/test_activity_files.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from tymewear_mcp.tools.activity_files import (
    export_activity_strap_files,
    get_activity_logs,
    get_activity_strap_files,
    get_activity_workout_zone_detection,
)


def _json_response(data: dict) -> httpx.Response:
    import json

    return httpx.Response(200, content=json.dumps(data).encode(), headers={"content-type": "application/json"})


def _binary_response() -> httpx.Response:
    return httpx.Response(
        200,
        content=b"strap-data",
        headers={
            "content-type": "application/zip",
            "content-disposition": 'attachment; filename="strap-files.zip"',
        },
    )


class TestActivityFiles:
    async def test_get_activity_logs(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=[{"event": "created", "token": "secret"}])
        mock_client.sanitize = lambda data: [{"event": item["event"]} for item in data]

        result = await get_activity_logs(mock_client, "abc-123")

        mock_client.get.assert_called_once_with("/v2/api/activities/abc-123/logs/")
        assert result == [{"event": "created"}]

    async def test_get_activity_strap_files_json(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"files": [{"name": "raw.bin"}]})
        mock_client.sanitize = lambda data: data

        result = await get_activity_strap_files(mock_client, "abc-123")

        mock_client.get.assert_called_once_with("/v2/api/activities/abc-123/strap-files/")
        assert result == {"available": True, "files": [{"name": "raw.bin"}]}

    async def test_get_activity_workout_zone_detection(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"thresholds_zone": {"VT1": 62.1}})
        mock_client.sanitize = lambda data: data

        result = await get_activity_workout_zone_detection(mock_client, "abc-123")

        mock_client.get.assert_called_once_with("/v2/api/activities/abc-123/workout-zone-detection/")
        assert result == {"available": True, "thresholds_zone": {"VT1": 62.1}}

    async def test_export_activity_strap_files_saves_binary(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tymewear_mcp.tools.activity_files.EXPORT_DIR", tmp_path)
        mock_client = AsyncMock()
        mock_client.get_raw = AsyncMock(return_value=_binary_response())

        result = await export_activity_strap_files(mock_client, "abc-12345")

        mock_client.get_raw.assert_called_once_with("/v2/api/activities/abc-12345/strap-files/")
        assert result["format"] == "ZIP"
        assert result["file_size_bytes"] == 10
        assert Path(result["file_path"]).exists()

    async def test_export_activity_strap_files_returns_json_metadata(self):
        mock_client = AsyncMock()
        mock_client.get_raw = AsyncMock(return_value=_json_response({"files": []}))

        result = await export_activity_strap_files(mock_client, "abc-123")

        assert result == {"available": True, "files": []}

    async def test_get_activity_strap_files_404_is_availability_result(self):
        request = httpx.Request("GET", "https://api.tymewear.com/v2/api/activities/abc/strap-files/")
        response = httpx.Response(404, json={"detail": "Not found."}, request=request)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError("Not found", request=request, response=response))

        result = await get_activity_strap_files(mock_client, "abc")

        assert result["available"] is False
        assert result["reason"] == "not_found"
        assert result["status_code"] == 404
```

- [ ] **Step 2: Run failing activity file tests**

Run:

```bash
pytest tests/test_tools/test_activity_files.py -v
```

Expected: FAIL because `activity_files.py` does not exist.

- [ ] **Step 3: Add raw export helper and activity file module**

Create `src/tymewear_mcp/tools/activity_files.py`:

```python
"""Read-only activity logs, strap files, and workout-zone detection tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.tools._availability import unavailable_from_http_error
from tymewear_mcp.tools.exports import _extract_filename

EXPORT_DIR = Path.home() / "Downloads" / "tymewear"


def _save_binary(resp: httpx.Response, activity_id: str, extension: str) -> dict[str, Any]:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    filename = _extract_filename(resp) or f"activity_{activity_id[:8]}_strap_files.{extension}"
    filepath = EXPORT_DIR / filename
    filepath.write_bytes(resp.content)
    return {
        "file_path": str(filepath),
        "file_size_bytes": len(resp.content),
        "format": extension.upper(),
        "content_type": resp.headers.get("content-type", ""),
    }


async def get_activity_logs(client: TymeClient, activity_id: str) -> Any:
    data = await client.get(f"/v2/api/activities/{activity_id}/logs/")
    return client.sanitize(data)


async def get_activity_strap_files(client: TymeClient, activity_id: str) -> dict[str, Any]:
    try:
        data = await client.get(f"/v2/api/activities/{activity_id}/strap-files/")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {403, 404}:
            reason = "raw_data_access_disabled" if exc.response.status_code == 403 else "not_found"
            return unavailable_from_http_error(exc, default_reason=reason)
        raise
    sanitized = client.sanitize(data)
    return {"available": True, **sanitized} if isinstance(sanitized, dict) else {"available": True, "data": sanitized}


async def export_activity_strap_files(client: TymeClient, activity_id: str) -> dict[str, Any]:
    try:
        resp = await client.get_raw(f"/v2/api/activities/{activity_id}/strap-files/")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {403, 404}:
            reason = "raw_data_access_disabled" if exc.response.status_code == 403 else "not_found"
            return unavailable_from_http_error(exc, default_reason=reason)
        raise
    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        data = TymeClient.sanitize(resp.json())
        return {"available": True, **data} if isinstance(data, dict) else {"available": True, "data": data}
    extension = "zip" if "zip" in content_type else "bin"
    return _save_binary(resp, activity_id, extension)


async def get_activity_workout_zone_detection(client: TymeClient, activity_id: str) -> dict[str, Any]:
    try:
        data = await client.get(f"/v2/api/activities/{activity_id}/workout-zone-detection/")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {403, 404}:
            return unavailable_from_http_error(exc, default_reason="feature_not_available")
        raise
    sanitized = client.sanitize(data)
    return {"available": True, **sanitized} if isinstance(sanitized, dict) else {"available": True, "data": sanitized}
```

- [ ] **Step 4: Run activity file tests**

Run:

```bash
pytest tests/test_tools/test_activity_files.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/tymewear_mcp/tools/activity_files.py tests/test_tools/test_activity_files.py
git commit -m "feat: add activity file read tools"
```

---

### Task 4: FIT Export Fallback

**Files:**
- Modify: `src/tymewear_mcp/tools/exports.py`
- Modify: `tests/test_tools/test_exports.py`

- [ ] **Step 1: Write failing FIT fallback test**

Append inside `TestExportFit` in `tests/test_tools/test_exports.py`:

```python
    async def test_export_fit_falls_back_to_dashboard_get(self, tmp_path, monkeypatch):
        import httpx

        monkeypatch.setattr("tymewear_mcp.tools.exports.EXPORT_DIR", tmp_path)
        request = httpx.Request("POST", "https://api.tymewear.com/v2/api/activities/export-fit/")
        response = httpx.Response(404, json={"detail": "Not found."}, request=request)
        mock_client = AsyncMock()
        mock_client.post_raw = AsyncMock(side_effect=httpx.HTTPStatusError("Not found", request=request, response=response))
        mock_client.get_raw = AsyncMock(return_value=_make_fit_response())

        result = await export_fit(mock_client, "abc-12345")

        mock_client.post_raw.assert_called_once_with("/v2/api/activities/export-fit/", json={"activity_id": "abc-12345"})
        mock_client.get_raw.assert_called_once_with("/api/activities/abc-12345/fit/")
        assert result["format"] == "FIT"
        assert Path(result["file_path"]).exists()
```

- [ ] **Step 2: Run failing FIT fallback test**

Run:

```bash
pytest tests/test_tools/test_exports.py::TestExportFit::test_export_fit_falls_back_to_dashboard_get -v
```

Expected: FAIL because `export_fit()` does not call `get_raw()`.

- [ ] **Step 3: Implement FIT fallback**

In `src/tymewear_mcp/tools/exports.py`, add `import httpx` near the top and replace `export_fit()` with:

```python
async def export_fit(client: TymeClient, activity_id: str) -> dict[str, Any]:
    try:
        resp = await client.post_raw("/v2/api/activities/export-fit/", json={"activity_id": activity_id})
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in {403, 404}:
            raise
        resp = await client.get_raw(f"/api/activities/{activity_id}/fit/")
    return _save_export(resp, activity_id, "fit")
```

- [ ] **Step 4: Run export tests**

Run:

```bash
pytest tests/test_tools/test_exports.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/tymewear_mcp/tools/exports.py tests/test_tools/test_exports.py
git commit -m "feat: add FIT export fallback"
```

---

### Task 5: Training Plan And Workout Recommendation Reads

**Files:**
- Create: `src/tymewear_mcp/tools/training_plans.py`
- Modify: `src/tymewear_mcp/tools/_validation.py`
- Create: `tests/test_tools/test_training_plans.py`

- [ ] **Step 1: Write failing training plan tests**

Create `tests/test_tools/test_training_plans.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx

from tymewear_mcp.tools._validation import TrainingPlanByDateInput, TrainingPlanByWeekInput
from tymewear_mcp.tools.training_plans import (
    get_training_plan,
    get_training_plan_by_date,
    get_training_plan_by_week,
    get_training_plan_config,
    get_training_plan_history,
    get_training_plan_preview,
    get_workout_recommendation,
)


class TestTrainingPlanValidation:
    def test_date_input_accepts_iso_date(self):
        params = TrainingPlanByDateInput.model_validate({"date": "2026-04-28"})
        assert params.date == "2026-04-28"

    def test_week_input_accepts_string(self):
        params = TrainingPlanByWeekInput.model_validate({"week": "2026-W18"})
        assert params.week == "2026-W18"


class TestTrainingPlanTools:
    async def test_get_training_plan(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"weeks": []})
        mock_client.sanitize = lambda data: data

        result = await get_training_plan(mock_client, "user-uuid")

        mock_client.get.assert_called_once_with("/v2/api/users/user-uuid/training-plan/")
        assert result == {"available": True, "weeks": []}

    async def test_get_training_plan_by_date(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"date": "2026-04-28"})
        mock_client.sanitize = lambda data: data

        await get_training_plan_by_date(mock_client, "user-uuid", "2026-04-28")

        mock_client.get.assert_called_once_with(
            "/v2/api/users/user-uuid/training-plan/",
            params={"date": "2026-04-28"},
        )

    async def test_get_training_plan_by_week(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"week": "2026-W18"})
        mock_client.sanitize = lambda data: data

        await get_training_plan_by_week(mock_client, "user-uuid", "2026-W18")

        mock_client.get.assert_called_once_with(
            "/v2/api/users/user-uuid/training-plan/",
            params={"week": "2026-W18"},
        )

    async def test_get_training_plan_history(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=[])
        mock_client.sanitize = lambda data: data

        await get_training_plan_history(mock_client, "user-uuid")

        mock_client.get.assert_called_once_with("/v2/api/users/user-uuid/training-plans/history/")

    async def test_get_training_plan_config(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"hours": 8})
        mock_client.sanitize = lambda data: data

        await get_training_plan_config(mock_client, "user-uuid")

        mock_client.get.assert_called_once_with("/v2/api/users/user-uuid/training-plan-config/")

    async def test_get_training_plan_preview(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"preview": []})
        mock_client.sanitize = lambda data: data

        await get_training_plan_preview(mock_client, "user-uuid")

        mock_client.get.assert_called_once_with("/v2/api/users/user-uuid/training-plan-preview/")

    async def test_get_workout_recommendation_uses_user_id(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={"recommendation": "endurance"})
        mock_client.sanitize = lambda data: data

        await get_workout_recommendation(mock_client, 99999)

        mock_client.get.assert_called_once_with("/api/users/99999/workout-recommendation/")

    async def test_404_returns_availability_result(self):
        request = httpx.Request("GET", "https://api.tymewear.com/v2/api/users/user-uuid/training-plan/")
        response = httpx.Response(404, json={"detail": "No plan"}, request=request)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError("No plan", request=request, response=response))

        result = await get_training_plan(mock_client, "user-uuid")

        assert result["available"] is False
        assert result["reason"] == "not_found"
```

- [ ] **Step 2: Run failing training plan tests**

Run:

```bash
pytest tests/test_tools/test_training_plans.py -v
```

Expected: FAIL because `training_plans.py` and new validation models do not exist.

- [ ] **Step 3: Add validation models**

Append to `src/tymewear_mcp/tools/_validation.py`:

```python
class TrainingPlanByDateInput(BaseModel):
    date: str = Field(description="ISO date in YYYY-MM-DD format", pattern=r"^\d{4}-\d{2}-\d{2}$")


class TrainingPlanByWeekInput(BaseModel):
    week: str = Field(description="Training plan week identifier, for example 2026-W18")
```

- [ ] **Step 4: Implement training plan module**

Create `src/tymewear_mcp/tools/training_plans.py`:

```python
"""Read-only training plan and workout recommendation tools."""

from __future__ import annotations

from typing import Any

import httpx

from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.tools._availability import unavailable_from_http_error


def _available(data: Any) -> dict[str, Any]:
    return {"available": True, **data} if isinstance(data, dict) else {"available": True, "data": data}


async def _get_available(client: TymeClient, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        data = await client.get(path, params=params) if params is not None else await client.get(path)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {403, 404}:
            reason = "subscription_required" if exc.response.status_code == 403 else "not_found"
            return unavailable_from_http_error(exc, default_reason=reason)
        raise
    return _available(client.sanitize(data))


async def get_training_plan(client: TymeClient, user_uuid: str) -> dict[str, Any]:
    return await _get_available(client, f"/v2/api/users/{user_uuid}/training-plan/")


async def get_training_plan_by_date(client: TymeClient, user_uuid: str, date: str) -> dict[str, Any]:
    return await _get_available(client, f"/v2/api/users/{user_uuid}/training-plan/", params={"date": date})


async def get_training_plan_by_week(client: TymeClient, user_uuid: str, week: str) -> dict[str, Any]:
    return await _get_available(client, f"/v2/api/users/{user_uuid}/training-plan/", params={"week": week})


async def get_training_plan_history(client: TymeClient, user_uuid: str) -> dict[str, Any]:
    return await _get_available(client, f"/v2/api/users/{user_uuid}/training-plans/history/")


async def get_training_plan_config(client: TymeClient, user_uuid: str) -> dict[str, Any]:
    return await _get_available(client, f"/v2/api/users/{user_uuid}/training-plan-config/")


async def get_training_plan_preview(client: TymeClient, user_uuid: str) -> dict[str, Any]:
    return await _get_available(client, f"/v2/api/users/{user_uuid}/training-plan-preview/")


async def get_workout_recommendation(client: TymeClient, user_id: int) -> dict[str, Any]:
    return await _get_available(client, f"/api/users/{user_id}/workout-recommendation/")
```

- [ ] **Step 5: Run training plan tests**

Run:

```bash
pytest tests/test_tools/test_training_plans.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/tymewear_mcp/tools/_validation.py src/tymewear_mcp/tools/training_plans.py tests/test_tools/test_training_plans.py
git commit -m "feat: add training plan read tools"
```

---

### Task 6: Integrations, Account, And Physiology Reads

**Files:**
- Create: `src/tymewear_mcp/tools/integrations.py`
- Create: `src/tymewear_mcp/tools/account.py`
- Create: `src/tymewear_mcp/tools/physiology.py`
- Modify: `src/tymewear_mcp/tools/_validation.py`
- Create: `tests/test_tools/test_integrations.py`
- Create: `tests/test_tools/test_account.py`
- Create: `tests/test_tools/test_physiology.py`

- [ ] **Step 1: Write failing integration/account/physiology tests**

Create `tests/test_tools/test_integrations.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx

from tymewear_mcp.tools._validation import IntegrationInput
from tymewear_mcp.tools.integrations import get_integration, get_integration_health, get_integrations


def test_integration_input_accepts_slug():
    params = IntegrationInput.model_validate({"integration_id": "garmin"})
    assert params.integration_id == "garmin"


async def test_get_integrations():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=[{"slug": "garmin", "token": "secret"}])
    mock_client.sanitize = lambda data: [{"slug": item["slug"]} for item in data]

    result = await get_integrations(mock_client)

    mock_client.get.assert_called_once_with("/v2/api/integrations/")
    assert result == {"available": True, "data": [{"slug": "garmin"}]}


async def test_get_integration_detail():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value={"slug": "garmin"})
    mock_client.sanitize = lambda data: data

    await get_integration(mock_client, "garmin")

    mock_client.get.assert_called_once_with("/v2/api/integrations/garmin/")


async def test_get_integration_health_404():
    request = httpx.Request("GET", "https://api.tymewear.com/v2/api/integrations/garmin/health/")
    response = httpx.Response(404, json={"detail": "Not configured"}, request=request)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError("Not configured", request=request, response=response))

    result = await get_integration_health(mock_client, "garmin")

    assert result["available"] is False
    assert result["reason"] == "integration_not_configured"
```

Create `tests/test_tools/test_account.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock

from tymewear_mcp.tools.account import get_subscription_plans, get_subscription_status


async def test_get_subscription_status():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value={"status": "active"})
    mock_client.sanitize = lambda data: data

    result = await get_subscription_status(mock_client)

    mock_client.get.assert_called_once_with("/v2/api/subscription/status/")
    assert result == {"available": True, "status": "active"}


async def test_get_subscription_plans():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=[{"name": "Pro"}])
    mock_client.sanitize = lambda data: data

    result = await get_subscription_plans(mock_client)

    mock_client.get.assert_called_once_with("/v2/api/subscription/plans/")
    assert result == {"available": True, "data": [{"name": "Pro"}]}
```

Create `tests/test_tools/test_physiology.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock

from tymewear_mcp.tools.physiology import get_resting_max_values


async def test_get_resting_max_values():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value={"max_hr": 190, "secret": "x"})
    mock_client.sanitize = lambda data: {"max_hr": data["max_hr"]}

    result = await get_resting_max_values(mock_client)

    mock_client.get.assert_called_once_with("/v2/api/resting-max-values/")
    assert result == {"available": True, "max_hr": 190}
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
pytest tests/test_tools/test_integrations.py tests/test_tools/test_account.py tests/test_tools/test_physiology.py -v
```

Expected: FAIL because modules and `IntegrationInput` do not exist.

- [ ] **Step 3: Add `IntegrationInput`**

Append to `src/tymewear_mcp/tools/_validation.py`:

```python
class IntegrationInput(BaseModel):
    integration_id: str = Field(description="Integration id or slug, for example garmin or intervals-icu")
```

- [ ] **Step 4: Implement integrations module**

Create `src/tymewear_mcp/tools/integrations.py`:

```python
"""Read-only Tymewear integration tools."""

from __future__ import annotations

from typing import Any

import httpx

from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.tools._availability import unavailable_from_http_error


def _available(data: Any) -> dict[str, Any]:
    return {"available": True, **data} if isinstance(data, dict) else {"available": True, "data": data}


async def _get_available(client: TymeClient, path: str, *, not_found_reason: str) -> dict[str, Any]:
    try:
        data = await client.get(path)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {403, 404}:
            return unavailable_from_http_error(exc, default_reason=not_found_reason)
        raise
    return _available(client.sanitize(data))


async def get_integrations(client: TymeClient) -> dict[str, Any]:
    data = await client.get("/v2/api/integrations/")
    return _available(client.sanitize(data))


async def get_integration(client: TymeClient, integration_id: str) -> dict[str, Any]:
    return await _get_available(client, f"/v2/api/integrations/{integration_id}/", not_found_reason="not_found")


async def get_integration_health(client: TymeClient, integration_id: str) -> dict[str, Any]:
    return await _get_available(
        client,
        f"/v2/api/integrations/{integration_id}/health/",
        not_found_reason="integration_not_configured",
    )
```

- [ ] **Step 5: Implement account module**

Create `src/tymewear_mcp/tools/account.py`:

```python
"""Read-only account and subscription tools."""

from __future__ import annotations

from typing import Any

from tymewear_mcp.client.http import TymeClient


def _available(data: Any) -> dict[str, Any]:
    return {"available": True, **data} if isinstance(data, dict) else {"available": True, "data": data}


async def get_subscription_status(client: TymeClient) -> dict[str, Any]:
    data = await client.get("/v2/api/subscription/status/")
    return _available(client.sanitize(data))


async def get_subscription_plans(client: TymeClient) -> dict[str, Any]:
    data = await client.get("/v2/api/subscription/plans/")
    return _available(client.sanitize(data))
```

- [ ] **Step 6: Implement physiology module**

Create `src/tymewear_mcp/tools/physiology.py`:

```python
"""Read-only physiology metric tools."""

from __future__ import annotations

from typing import Any

import httpx

from tymewear_mcp.client.http import TymeClient
from tymewear_mcp.tools._availability import unavailable_from_http_error


def _available(data: Any) -> dict[str, Any]:
    return {"available": True, **data} if isinstance(data, dict) else {"available": True, "data": data}


async def get_resting_max_values(client: TymeClient) -> dict[str, Any]:
    try:
        data = await client.get("/v2/api/resting-max-values/")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {403, 404}:
            return unavailable_from_http_error(exc, default_reason="feature_not_available")
        raise
    return _available(client.sanitize(data))
```

- [ ] **Step 7: Run new module tests**

Run:

```bash
pytest tests/test_tools/test_integrations.py tests/test_tools/test_account.py tests/test_tools/test_physiology.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```bash
git add src/tymewear_mcp/tools/_validation.py src/tymewear_mcp/tools/integrations.py src/tymewear_mcp/tools/account.py src/tymewear_mcp/tools/physiology.py tests/test_tools/test_integrations.py tests/test_tools/test_account.py tests/test_tools/test_physiology.py
git commit -m "feat: add account integration physiology reads"
```

---

### Task 7: Server Registration And Routing

**Files:**
- Modify: `src/tymewear_mcp/server.py`
- Create: `tests/test_server.py`

- [ ] **Step 1: Write failing server registration/routing tests**

Create `tests/test_server.py`:

```python
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from tymewear_mcp import server as server_mod


NEW_TOOLS = {
    "tw_get_activity_logs",
    "tw_get_activity_strap_files",
    "tw_export_activity_strap_files",
    "tw_get_activity_workout_zone_detection",
    "tw_get_resting_max_values",
    "tw_get_training_plan",
    "tw_get_training_plan_by_date",
    "tw_get_training_plan_by_week",
    "tw_get_training_plan_history",
    "tw_get_training_plan_config",
    "tw_get_training_plan_preview",
    "tw_get_workout_recommendation",
    "tw_get_integrations",
    "tw_get_integration",
    "tw_get_integration_health",
    "tw_get_subscription_status",
    "tw_get_subscription_plans",
}


async def test_list_tools_includes_athlete_website_tools():
    tools = await server_mod.list_tools()
    names = {tool.name for tool in tools}

    assert NEW_TOOLS.issubset(names)


async def test_call_tool_routes_activity_logs(monkeypatch):
    client = object()
    monkeypatch.setattr(server_mod, "_get_client", lambda: client)
    monkeypatch.setattr(
        server_mod.activity_files_mod,
        "get_activity_logs",
        AsyncMock(return_value={"events": []}),
    )

    result = await server_mod.call_tool("tw_get_activity_logs", {"activity_id": "abc-123"})

    server_mod.activity_files_mod.get_activity_logs.assert_awaited_once_with(client, "abc-123")
    assert json.loads(result[0].text) == {"events": []}


async def test_call_tool_routes_training_plan_by_date(monkeypatch):
    client = object()
    monkeypatch.setattr(server_mod, "_get_client", lambda: client)
    monkeypatch.setattr(server_mod.profile_mod, "get_profile", AsyncMock(return_value={"id": 99999, "uuid": "user-uuid"}))
    monkeypatch.setattr(
        server_mod.training_plans_mod,
        "get_training_plan_by_date",
        AsyncMock(return_value={"available": True}),
    )

    result = await server_mod.call_tool("tw_get_training_plan_by_date", {"date": "2026-04-28"})

    server_mod.training_plans_mod.get_training_plan_by_date.assert_awaited_once_with(client, "user-uuid", "2026-04-28")
    assert json.loads(result[0].text) == {"available": True}


async def test_call_tool_routes_integration_health(monkeypatch):
    client = object()
    monkeypatch.setattr(server_mod, "_get_client", lambda: client)
    monkeypatch.setattr(
        server_mod.integrations_mod,
        "get_integration_health",
        AsyncMock(return_value={"available": True}),
    )

    result = await server_mod.call_tool("tw_get_integration_health", {"integration_id": "garmin"})

    server_mod.integrations_mod.get_integration_health.assert_awaited_once_with(client, "garmin")
    assert json.loads(result[0].text) == {"available": True}
```

- [ ] **Step 2: Run failing server tests**

Run:

```bash
pytest tests/test_server.py -v
```

Expected: FAIL because the new tools are not registered and new module imports are missing.

- [ ] **Step 3: Add server imports**

In `src/tymewear_mcp/server.py`, add these imports near the existing tool imports:

```python
from tymewear_mcp.tools import account as account_mod
from tymewear_mcp.tools import activity_files as activity_files_mod
from tymewear_mcp.tools import integrations as integrations_mod
from tymewear_mcp.tools import physiology as physiology_mod
from tymewear_mcp.tools import training_plans as training_plans_mod
```

And add these validation imports:

```python
    IntegrationInput,
    TrainingPlanByDateInput,
    TrainingPlanByWeekInput,
```

- [ ] **Step 4: Add tool metadata**

In `list_tools()`, insert these `Tool(...)` entries before export tools:

```python
        Tool(
            name="tw_get_activity_logs",
            description="Get read-only logs/events for a Tymewear activity.",
            inputSchema=GetActivityInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_activity_strap_files",
            description="Get strap-file metadata for a Tymewear activity when available.",
            inputSchema=GetActivityInput.model_json_schema(),
        ),
        Tool(
            name="tw_export_activity_strap_files",
            description="Export raw strap files for a Tymewear activity when the account has access.",
            inputSchema=ExportInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_activity_workout_zone_detection",
            description="Get workout-zone detection results for a Tymewear activity when available.",
            inputSchema=GetActivityInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_resting_max_values",
            description="Get read-only resting/max physiology values from Tymewear.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_get_training_plan",
            description="Get the current Tymewear training plan for the authenticated athlete.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_get_training_plan_by_date",
            description="Get Tymewear training-plan data for a specific ISO date.",
            inputSchema=TrainingPlanByDateInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_training_plan_by_week",
            description="Get Tymewear training-plan data for a specific week identifier.",
            inputSchema=TrainingPlanByWeekInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_training_plan_history",
            description="Get Tymewear training-plan history for the authenticated athlete.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_get_training_plan_config",
            description="Get Tymewear training-plan configuration for the authenticated athlete.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_get_training_plan_preview",
            description="Get Tymewear training-plan preview for the authenticated athlete.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_get_workout_recommendation",
            description="Get Tymewear workout recommendation for the authenticated athlete.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_get_integrations",
            description="List athlete-facing Tymewear integrations.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_get_integration",
            description="Get details for a Tymewear integration by id or slug.",
            inputSchema=IntegrationInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_integration_health",
            description="Get connection health/status for a Tymewear integration by id or slug.",
            inputSchema=IntegrationInput.model_json_schema(),
        ),
        Tool(
            name="tw_get_subscription_status",
            description="Get Tymewear subscription status for the authenticated athlete.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="tw_get_subscription_plans",
            description="Get available Tymewear subscription plans.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
```

- [ ] **Step 5: Update `tw_get_activities` routing**

Replace the existing `tw_get_activities` branch in `call_tool()` with:

```python
    elif name == "tw_get_activities":
        params = GetActivitiesInput.model_validate(arguments)
        profile = await profile_mod.get_profile(client)
        result = await activities_mod.get_activities(
            client,
            user_id=profile["id"],
            sport=params.sport,
            limit=params.limit,
            cursor=params.cursor,
            sports=params.sports,
            activity_types=params.activity_types,
            search=params.search,
            requested_user_id=params.user_id,
            pro_team=params.pro_team,
        )
```

- [ ] **Step 6: Add call routing branches**

Insert these branches in `call_tool()` before the export branches:

```python
    elif name == "tw_get_activity_logs":
        params = GetActivityInput.model_validate(arguments)
        result = await activity_files_mod.get_activity_logs(client, params.activity_id)

    elif name == "tw_get_activity_strap_files":
        params = GetActivityInput.model_validate(arguments)
        result = await activity_files_mod.get_activity_strap_files(client, params.activity_id)

    elif name == "tw_export_activity_strap_files":
        params = ExportInput.model_validate(arguments)
        result = await activity_files_mod.export_activity_strap_files(client, params.activity_id)

    elif name == "tw_get_activity_workout_zone_detection":
        params = GetActivityInput.model_validate(arguments)
        result = await activity_files_mod.get_activity_workout_zone_detection(client, params.activity_id)

    elif name == "tw_get_resting_max_values":
        result = await physiology_mod.get_resting_max_values(client)

    elif name == "tw_get_training_plan":
        profile = await profile_mod.get_profile(client)
        result = await training_plans_mod.get_training_plan(client, profile["uuid"])

    elif name == "tw_get_training_plan_by_date":
        params = TrainingPlanByDateInput.model_validate(arguments)
        profile = await profile_mod.get_profile(client)
        result = await training_plans_mod.get_training_plan_by_date(client, profile["uuid"], params.date)

    elif name == "tw_get_training_plan_by_week":
        params = TrainingPlanByWeekInput.model_validate(arguments)
        profile = await profile_mod.get_profile(client)
        result = await training_plans_mod.get_training_plan_by_week(client, profile["uuid"], params.week)

    elif name == "tw_get_training_plan_history":
        profile = await profile_mod.get_profile(client)
        result = await training_plans_mod.get_training_plan_history(client, profile["uuid"])

    elif name == "tw_get_training_plan_config":
        profile = await profile_mod.get_profile(client)
        result = await training_plans_mod.get_training_plan_config(client, profile["uuid"])

    elif name == "tw_get_training_plan_preview":
        profile = await profile_mod.get_profile(client)
        result = await training_plans_mod.get_training_plan_preview(client, profile["uuid"])

    elif name == "tw_get_workout_recommendation":
        profile = await profile_mod.get_profile(client)
        result = await training_plans_mod.get_workout_recommendation(client, profile["id"])

    elif name == "tw_get_integrations":
        result = await integrations_mod.get_integrations(client)

    elif name == "tw_get_integration":
        params = IntegrationInput.model_validate(arguments)
        result = await integrations_mod.get_integration(client, params.integration_id)

    elif name == "tw_get_integration_health":
        params = IntegrationInput.model_validate(arguments)
        result = await integrations_mod.get_integration_health(client, params.integration_id)

    elif name == "tw_get_subscription_status":
        result = await account_mod.get_subscription_status(client)

    elif name == "tw_get_subscription_plans":
        result = await account_mod.get_subscription_plans(client)
```

- [ ] **Step 7: Run server tests**

Run:

```bash
pytest tests/test_server.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```bash
git add src/tymewear_mcp/server.py tests/test_server.py
git commit -m "feat: register athlete website read tools"
```

---

### Task 8: README And Full Verification

**Files:**
- Modify: `README.md`
- Modify: `tasks/todo.md` in the workspace root if task tracking is still being used outside the `tymewear-mcp` repo.

- [ ] **Step 1: Update README feature count and sections**

In `README.md`, update the feature count from `20 MCP tools` to the new total after Task 7. Add the new tools to these sections:

```markdown
### Activity Files & Detection

| Tool | Description |
|------|-------------|
| `tw_get_activity_logs` | Get read-only activity logs/events |
| `tw_get_activity_strap_files` | Get strap-file metadata when available |
| `tw_export_activity_strap_files` | Export raw strap files when available |
| `tw_get_activity_workout_zone_detection` | Get workout-zone detection results |

### Training Plans & Workouts

| Tool | Description |
|------|-------------|
| `tw_get_training_plan` | Get current training plan |
| `tw_get_training_plan_by_date` | Get training-plan data for a date |
| `tw_get_training_plan_by_week` | Get training-plan data for a week |
| `tw_get_training_plan_history` | Get training-plan history |
| `tw_get_training_plan_config` | Get training-plan configuration |
| `tw_get_training_plan_preview` | Get training-plan preview |
| `tw_get_workout_recommendation` | Get workout recommendation |

### Integrations & Account

| Tool | Description |
|------|-------------|
| `tw_get_integrations` | List integrations |
| `tw_get_integration` | Get integration details |
| `tw_get_integration_health` | Get integration health/status |
| `tw_get_subscription_status` | Get subscription status |
| `tw_get_subscription_plans` | Get available subscription plans |
| `tw_get_resting_max_values` | Get resting/max physiology values |
```

- [ ] **Step 2: Run focused tool tests**

Run:

```bash
pytest tests/test_tools -v
```

Expected: PASS.

- [ ] **Step 3: Run full test suite**

Run:

```bash
pytest tests/ -v
```

Expected: PASS.

- [ ] **Step 4: Run ruff**

Run:

```bash
ruff check src tests
```

Expected: PASS with no lint errors.

- [ ] **Step 5: Run mypy**

Run:

```bash
mypy src
```

Expected: PASS. If mypy reports `AsyncMock` or untyped test issues, do not silence source errors; only adjust test annotations or existing mypy config if the failure is test-only.

- [ ] **Step 6: Update task review notes**

If `/Users/tristan/Developer/cycling/tasks/todo.md` is still the active task tracker, add a review entry like:

```markdown
- Implemented athlete-facing Tymewear website read coverage: activity files/logs/detection, training plans, integrations, account/subscription, and resting max values.
- Added structured availability responses for expected 403/404 feature gaps.
- Verified with `pytest tests/ -v`, `ruff check src tests`, and `mypy src`.
```

- [ ] **Step 7: Commit documentation and final verification notes**

Run:

```bash
git add README.md
git commit -m "docs: document athlete website read tools"
```

---

## Self-Review Checklist

- Spec coverage:
  - Activity files/logs/detection: Task 3 and Task 7.
  - Activity listing filters: Task 2 and Task 7.
  - FIT fallback: Task 4.
  - Training plans/workout recommendation: Task 5 and Task 7.
  - Integrations: Task 6 and Task 7.
  - Account/subscription: Task 6 and Task 7.
  - Resting max values: Task 6 and Task 7.
  - Availability objects: Task 1, Task 3, Task 5, Task 6.
  - README and verification: Task 8.
- Open-ended step scan: every step has concrete files, code, commands, and expected results.
- Type consistency:
  - Server routes use `TrainingPlanByDateInput.date`, `TrainingPlanByWeekInput.week`, and `IntegrationInput.integration_id`.
  - Activity filter tool args use `sports`, `activity_types`, `user_id`, and `pro_team`, with `requested_user_id` used only inside the Python function.
  - Raw binary GET endpoints use `TymeClient.get_raw()`.
