# Tymewear MCP — Trainer-Feedback Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Tymewear MCP surface the threshold/test data a coach actually needs (instead of empty-looking fields buried in multi-MB blobs), and enable power-at-threshold by joining Tymewear's detected breakpoint *times* to an external power stream.

**Architecture:** Tymewear exposes rich per-activity physiology, but spread across (1) a bloated activity-detail blob with unlabeled positional arrays and (2) a separate **labeled** `workout-zone-detection` endpoint (time/cal per zone, threshold VE/HR/power + confidence + a `_quality` block). Per-*second* streams are permission-gated (`raw_data_access:false` → processed-data 404s) and *measured* power lives only in TrainingPeaks/Garmin — but Tymewear's *estimated* power-at-threshold IS present and is what the UI shows. The MCP's job: (a) surface the labeled per-activity insights (thresholds, VE, HR, estimated power, zones, quality) from the working endpoints; (b) stop dumping 3.9–10.8 MB activity / 76–554 KB zone blobs; (c) fail gracefully on gated/broken endpoints (processed-data 404, CSV-export-returns-HTML); (d) provide a power-join tool for the *measured* cross-check (Plan B feeds TP/Garmin power).

> **POST-VERIFICATION ADDENDUM at end of file supersedes Task 5 and adds Tasks A/B — read it.**

**Tech Stack:** Python 3.10+, MCP SDK, httpx, Pydantic v2, pytest + pytest-asyncio (`asyncio_mode = "auto"`). Tests use `unittest.mock.AsyncMock`.

## Global Constraints

- Every tool handler returns a JSON-sanitisable object; the server wraps it via `json.dumps(..., default=str)` in `server.py:554`.
- New read tools must be **public-mode safe** (no disk writes). Any file/FIT-path feature must be added to `_PUBLIC_DISABLED_EXPORT_TOOLS` in `server.py:51`.
- Follow the existing tool-add pattern exactly: input model in `tools/_validation.py` → `Tool(...)` in `server.py:_registered_tools()` → `elif` branch in `server.py:call_tool()` → impl in `tools/*.py` → tests in `tests/test_tools/test_*.py`.
- Use `client.sanitize(...)` on any raw API response before returning.
- Tests mock the client: `mock_client.get = AsyncMock(return_value=...)`, `mock_client.sanitize = lambda d: d`.
- VE targets for bike live in the profile as `bike_ve_target_vt1/bp/vt2/vo2max`; run as `running_ve_target_*`. Verified live values (bike): VT1=58.7, BP=77.6, VT2=114.0, VO2max=158.3.
- Detected breakpoints live as `new_zone_vt1/vt2/vo2max/fatmax` (mm:ss strings, e.g. `"37:27"`). The legacy `vt1/vt2/v02max` string fields are always `""` — do not use them.

---

## File Structure

- `src/tymewear_mcp/tools/_validation.py` — add `ComputePowerAtThresholdInput`, `GetActivityDetailInput`; widen `GetActivitiesInput.sport`.
- `src/tymewear_mcp/tools/thresholds.py` — rewrite `get_ve_targets` to be profile-sourced (drop the broken endpoint call).
- `src/tymewear_mcp/tools/breathing_data.py` — wrap both processed-data calls in graceful 404/403 handling.
- `src/tymewear_mcp/tools/activities.py` — add `_slim_activity` + `include` arg to `get_activity`.
- `src/tymewear_mcp/tools/threshold_analysis.py` — **new file**: `get_thresholds(activity, profile)` and `compute_power_at_threshold(threshold_times, power_samples, window_seconds)`.
- `src/tymewear_mcp/server.py` — register `tw_get_thresholds`, `tw_compute_power_at_threshold`; update `tw_get_ve_targets`, `tw_get_activity` dispatch.
- `tests/test_tools/test_thresholds.py`, `test_breathing_data.py`, `test_activities.py`, `test_validation.py` — extend.
- `tests/test_tools/test_threshold_analysis.py` — **new test file**.

---

## Task 1: Fix `tw_get_ve_targets` (profile-sourced)

**Problem:** `thresholds.py:22` calls `/api/users/{id}/ve-targets/`, which returns an empty body live → `resp.json()` raises `Expecting value: line 1 column 1`. The same data is already in the profile.

**Files:**
- Modify: `src/tymewear_mcp/tools/thresholds.py:21-23`
- Modify: `src/tymewear_mcp/server.py:443-445`
- Test: `tests/test_tools/test_thresholds.py:7-16`

**Interfaces:**
- Produces: `get_ve_targets(profile: dict) -> dict` returning `{"bike": {"vt1","bp","vt2","vo2max"}, "running": {...}}` (no client call).

- [ ] **Step 1 — failing test** (replace `TestGetVeTargets` in `test_thresholds.py`):

```python
from tymewear_mcp.tools.thresholds import get_ve_targets

class TestGetVeTargets:
    def test_targets_from_profile(self):
        profile = {
            "bike_ve_target_vt1": 58.7, "bike_ve_target_bp": 77.6,
            "bike_ve_target_vt2": 114.0, "bike_ve_target_vo2max": 158.3,
            "running_ve_target_vt1": 0.0, "running_ve_target_bp": 0.0,
            "running_ve_target_vt2": 0.0, "running_ve_target_vo2max": 0.0,
        }
        result = get_ve_targets(profile)
        assert result["bike"] == {"vt1": 58.7, "bp": 77.6, "vt2": 114.0, "vo2max": 158.3}
        assert result["running"]["vt1"] == 0.0
```

- [ ] **Step 2 — run, expect FAIL** (`get_ve_targets` still async/takes client): `pytest tests/test_tools/test_thresholds.py::TestGetVeTargets -v`

- [ ] **Step 3 — implement** (replace `thresholds.py:21-23`):

```python
def get_ve_targets(profile: dict[str, Any]) -> dict[str, Any]:
    """Assemble VE threshold targets from the profile (the /ve-targets/ endpoint returns an empty body)."""
    def _sport(prefix: str) -> dict[str, Any]:
        return {k: profile.get(f"{prefix}_ve_target_{k}") for k in ("vt1", "bp", "vt2", "vo2max")}
    return {"bike": _sport("bike"), "running": _sport("running")}
```

- [ ] **Step 4 — update dispatch** (`server.py:443-445`):

```python
        elif name == "tw_get_ve_targets":
            profile = await profile_mod.get_profile(client)
            result = thresholds_mod.get_ve_targets(profile)
```

- [ ] **Step 5 — run, expect PASS**; then `git add -A && git commit -m "fix: source VE targets from profile (ve-targets endpoint returns empty body)"`

---

## Task 2: Fix `sport` filter validation

**Problem:** `tw_get_activities(sport=2)` fails `'2' is not valid under any of the given schemas` — the MCP wire layer presents the value as string `"2"` and the generated `integer|null` schema rejects it. Pydantic-level `model_validate({"sport": 2})` already passes, so widen the type to accept the string wire form and coerce.

**Files:**
- Modify: `src/tymewear_mcp/tools/_validation.py:37-45`
- Test: `tests/test_tools/test_validation.py`

**Interfaces:**
- Produces: `GetActivitiesInput.sport: int | None` (coerced) — downstream `get_activities` unchanged (it already does `str(sport)`).

- [ ] **Step 1 — failing test** (add to `test_validation.py`):

```python
from tymewear_mcp.tools._validation import GetActivitiesInput

class TestSportCoercion:
    def test_string_sport_coerced_to_int(self):
        assert GetActivitiesInput.model_validate({"sport": "2"}).sport == 2
    def test_int_sport_still_works(self):
        assert GetActivitiesInput.model_validate({"sport": 2}).sport == 2
    def test_none_sport(self):
        assert GetActivitiesInput.model_validate({}).sport is None
```

- [ ] **Step 2 — run, expect FAIL** on `test_string_sport_coerced_to_int`.

- [ ] **Step 3 — implement** (in `_validation.py`, change the field + add validator inside `GetActivitiesInput`):

```python
    sport: int | str | None = Field(default=None, description="Legacy sport filter: 1=run, 2=bike")

    @field_validator("sport")
    @classmethod
    def _coerce_sport(cls, value: int | str | None) -> int | None:
        if value is None:
            return None
        if isinstance(value, str):
            if not value.isdigit():
                raise ValueError("sport must be 1 (run) or 2 (bike)")
            return int(value)
        return value
```

- [ ] **Step 4 — run, expect PASS** (whole file: `pytest tests/test_tools/test_validation.py tests/test_tools/test_activities.py -v`).

- [ ] **Step 5 — commit**: `git commit -am "fix: accept string sport filter from MCP wire layer"`

---

## Task 3: Graceful handling for processed-data 404/403

**Problem:** `breathing_data.py:34,45` call the endpoints with no error handling. Live, both return 404 (the data is `raw_data_access`-gated). A raw `HTTPStatusError` is unhelpful. Mirror the `activity_files.py:38-47` pattern.

**Files:**
- Modify: `src/tymewear_mcp/tools/breathing_data.py`
- Test: `tests/test_tools/test_breathing_data.py`

**Interfaces:**
- Produces: on 404/403 both functions return `{"available": False, "reason": "processed_data_not_available"|"new_processed_data_not_available", "status_code": int, "detail": str}` (via `unavailable_from_http_error`).

- [ ] **Step 1 — failing test** (add to `test_breathing_data.py`):

```python
import httpx
from tymewear_mcp.tools._availability import unavailable_from_http_error  # noqa: F401

def _http_error(status: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://api.tymewear.com/x")
    resp = httpx.Response(status, json={"detail": "Not found."}, request=req)
    return httpx.HTTPStatusError("err", request=req, response=resp)

class TestProcessedDataUnavailable:
    async def test_processed_data_404_graceful(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=_http_error(404))
        mock_client.sanitize = lambda d: d
        result = await get_processed_data(mock_client, "abc-123", mode="summary")
        assert result["available"] is False
        assert result["reason"] == "processed_data_not_available"
        assert result["status_code"] == 404

    async def test_new_processed_data_404_graceful(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=_http_error(404))
        mock_client.sanitize = lambda d: d
        result = await get_new_processed_data(mock_client, "abc-123")
        assert result["available"] is False
        assert result["reason"] == "new_processed_data_not_available"
```

- [ ] **Step 2 — run, expect FAIL** (raises instead of returning).

- [ ] **Step 3 — implement** (wrap both calls in `breathing_data.py`):

```python
import httpx
from tymewear_mcp.tools._availability import unavailable_from_http_error

async def get_processed_data(client, activity_id, mode="summary", window_start=None, window_end=None):
    try:
        data = await client.get(f"/v2/api/activities/{activity_id}/processed-data/")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {403, 404}:
            return unavailable_from_http_error(exc, default_reason="processed_data_not_available")
        raise
    records = data if isinstance(data, list) else []
    # ... unchanged summary/window/full logic ...

async def get_new_processed_data(client, activity_id):
    try:
        data = await client.get(f"/v2/api/activities/{activity_id}/new-processed-data/")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {403, 404}:
            return unavailable_from_http_error(exc, default_reason="new_processed_data_not_available")
        raise
    return client.sanitize(data) if isinstance(data, dict) else data
```

- [ ] **Step 4 — run, expect PASS** (`pytest tests/test_tools/test_breathing_data.py -v`).

- [ ] **Step 5 — commit**: `git commit -am "fix: graceful 404/403 on processed-data endpoints"`

---

## Task 4: Slim down `tw_get_activity`

**Problem:** `get_activity` returns the raw activity (3.9–10.8 MB). One field `x` is 5 MB; `onesignal_results` is 458 KB of notification noise; `predict_*_v3` arrays are ~3.2k points each. Strip heavy fields by default; allow opt-in via `include`.

**Files:**
- Modify: `src/tymewear_mcp/tools/activities.py:38-40`
- Modify: `src/tymewear_mcp/tools/_validation.py` (new `GetActivityDetailInput`)
- Modify: `src/tymewear_mcp/server.py` (import + register + dispatch)
- Test: `tests/test_tools/test_activities.py`

**Interfaces:**
- Produces: `get_activity(client, activity_id, include: list[str] | None = None) -> dict`. Dropped keys are summarised under `_omitted_fields: {key: {"type","length"}}`. Keys in `include` are retained.
- `GetActivityDetailInput(ActivityIdMixin)`: `activity_id: str`, `include: list[str] | None = None`.

- [ ] **Step 1 — failing test** (add to `test_activities.py`):

```python
class TestSlimActivity:
    async def test_heavy_fields_omitted_by_default(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={**SAMPLE_ACTIVITY, "x": [0]*100, "predict_ve_v3": [1.0]*3231, "new_zone_vt1": "37:27"})
        mock_client.sanitize = lambda d: d
        result = await get_activity(mock_client, "abc-123")
        assert "x" not in result and "predict_ve_v3" not in result
        assert result["_omitted_fields"]["x"]["length"] == 100
        assert result["new_zone_vt1"] == "37:27"   # small useful fields kept

    async def test_include_restores_field(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value={**SAMPLE_ACTIVITY, "x": [0]*100})
        mock_client.sanitize = lambda d: d
        result = await get_activity(mock_client, "abc-123", include=["x"])
        assert result["x"] == [0]*100
```

- [ ] **Step 2 — run, expect FAIL** (`get_activity` has no `include` arg / does not slim).

- [ ] **Step 3 — implement** (`activities.py`):

```python
_HEAVY_ACTIVITY_FIELDS = frozenset({
    "x", "onesignal_results",
    "predict_ve", "predict_time", "predict_ve_zone1", "predict_ve_zone2", "predict_ve_zone3",
    "predict_ve_v3", "predict_time_v3",
    "predict_ve_zone2_v3", "predict_ve_zone3_v3", "predict_ve_zone4_v3", "predict_ve_zone5_v3",
    "regression_analysis_x", "assoc_results", "plf_x_results",
    "zones_predict_plot", "zones_predict_v3_plot",
    "ext_hr", "ext_bike_power", "ext_cadence", "ext_speed",
})

def _describe_omitted(value: Any) -> dict[str, Any]:
    info: dict[str, Any] = {"type": type(value).__name__}
    if isinstance(value, (list, str, dict)):
        info["length"] = len(value)
    return info

def _slim_activity(activity: dict[str, Any], include: list[str]) -> dict[str, Any]:
    keep = set(include)
    out: dict[str, Any] = {}
    omitted: dict[str, Any] = {}
    for key, value in activity.items():
        if key in _HEAVY_ACTIVITY_FIELDS and key not in keep:
            omitted[key] = _describe_omitted(value)
        else:
            out[key] = value
    if omitted:
        out["_omitted_fields"] = omitted
    return out

async def get_activity(client, activity_id, include=None):
    data = await client.get(f"/v2/api/activities/{activity_id}/")
    sanitized = client.sanitize(data)
    if not isinstance(sanitized, dict):
        return cast(dict[str, Any], sanitized)
    return _slim_activity(sanitized, include or [])
```

- [ ] **Step 4 — wire validation + server.** Add to `_validation.py`:

```python
class GetActivityDetailInput(ActivityIdMixin):
    activity_id: str = Field(description="Activity UUID")
    include: list[str] | None = Field(default=None, description="Heavy fields to include verbatim, e.g. ['ext_bike_power','predict_ve_v3']")
```

In `server.py`: import `GetActivityDetailInput`; change `tw_get_activity` registration to `inputSchema=GetActivityDetailInput.model_json_schema()`; update dispatch:

```python
        elif name == "tw_get_activity":
            params = GetActivityDetailInput.model_validate(arguments)
            result = await activities_mod.get_activity(client, params.activity_id, include=params.include)
```

Update the `tw_get_activity` description to mention slimming + `include`.

- [ ] **Step 5 — run, expect PASS** (`pytest tests/test_tools/test_activities.py tests/test_server.py -v`); commit `feat: slim tw_get_activity heavy fields with opt-in include`.

---

## Task 5: New `tw_get_thresholds` tool

**Goal:** One compact call returns the detected breakpoints + targets + truncated-test flag a coach needs — the headline fix for "threshold fields come back empty."

**Files:**
- Create: `src/tymewear_mcp/tools/threshold_analysis.py`
- Modify: `src/tymewear_mcp/server.py` (import + register + dispatch)
- Test: `tests/test_tools/test_threshold_analysis.py` (new)

**Interfaces:**
- Produces: `get_thresholds(activity: dict, profile: dict) -> dict` (pure function; handler fetches activity+profile).
- Consumes: `_mmss_to_seconds` (also used by Task 6).

- [ ] **Step 1 — failing test** (`test_threshold_analysis.py`):

```python
from tymewear_mcp.tools.threshold_analysis import get_thresholds, _mmss_to_seconds

PROFILE = {"bike_ve_target_vt1": 58.7, "bike_ve_target_bp": 77.6, "bike_ve_target_vt2": 114.0,
           "bike_ve_target_vo2max": 158.3, "running_ve_target_vt1": 0.0, "running_ve_target_bp": 0.0,
           "running_ve_target_vt2": 0.0, "running_ve_target_vo2max": 0.0}

def test_mmss():
    assert _mmss_to_seconds("37:27") == 2247
    assert _mmss_to_seconds("") is None
    assert _mmss_to_seconds("1:02:03") == 3723

def test_complete_test_thresholds():
    activity = {"id": "e4", "name": "Ramp", "sport": "2", "sport_display": "Bike",
                "data_type": "tyme-wear", "duration": "53:48", "time_stamp": "2026-06-17T15:47:12Z",
                "unix_timestamp": 1781704032, "new_zone_fitness_level": "Elite",
                "new_zone_vt1": "37:27", "new_zone_vt2": "44:34", "new_zone_vo2max": "52:23",
                "new_zone_fatmax": "30:41", "predict_ve_v3": [1.0, 2.0]}
    r = get_thresholds(activity, PROFILE)
    assert r["detected_thresholds"]["vt1"]["time_seconds"] == 2247
    assert r["ve_targets"]["vt2"] == 114.0
    assert r["truncated_test"] is False
    assert r["started_at"] == "2026-06-17T15:47:12Z"

def test_truncated_test_flagged():
    activity = {"id": "x", "sport": "2", "new_zone_vt1": "20:00", "new_zone_vt2": "28:00",
                "new_zone_vo2max": "", "predict_ve_v3": [1.0]}
    assert get_thresholds(activity, PROFILE)["truncated_test"] is True
```

- [ ] **Step 2 — run, expect FAIL** (module missing).

- [ ] **Step 3 — implement** `threshold_analysis.py`:

```python
from __future__ import annotations
from typing import Any

def _mmss_to_seconds(value: str | None) -> int | None:
    if not value or not isinstance(value, str):
        return None
    parts = value.split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    seconds = 0
    for n in nums:
        seconds = seconds * 60 + n
    return seconds

def _ve_targets(profile: dict[str, Any], sport: str | None) -> dict[str, Any]:
    prefix = "running" if str(sport) == "1" else "bike"
    return {k: profile.get(f"{prefix}_ve_target_{k}") for k in ("vt1", "bp", "vt2", "vo2max")}

def get_thresholds(activity: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    detected: dict[str, Any] = {}
    for key, field in (("vt1", "new_zone_vt1"), ("vt2", "new_zone_vt2"),
                       ("vo2max", "new_zone_vo2max"), ("fatmax", "new_zone_fatmax")):
        secs = _mmss_to_seconds(activity.get(field))
        detected[key] = {"time": activity.get(field), "time_seconds": secs} if secs is not None else None
    is_test = bool(activity.get("predict_ve_v3"))
    truncated = is_test and (detected["vt1"] or detected["vt2"]) is not None and detected["vo2max"] is None
    return {
        "activity_id": activity.get("id"),
        "name": activity.get("name"),
        "sport": activity.get("sport_display"),
        "data_type": activity.get("data_type"),
        "duration": activity.get("duration"),
        "started_at": activity.get("time_stamp"),
        "unix_timestamp": activity.get("unix_timestamp"),
        "fitness_level": activity.get("new_zone_fitness_level"),
        "detected_thresholds": detected,
        "ve_targets": _ve_targets(profile, activity.get("sport")),
        "zone_time_kcal": activity.get("new_zone_thresholds_kcal_hrs"),
        "ve_curve_available": is_test,
        "truncated_test": truncated,
        "raw_threshold_metrics": activity.get("zones_predict_v3_thres_metrics"),
        "note": "Tymewear has no power. To get power-at-threshold, look up power at each time_seconds offset (start + offset) in the matching TrainingPeaks/Garmin ride, or use tw_compute_power_at_threshold.",
    }
```

- [ ] **Step 4 — register in `server.py`.** Import `threshold_analysis as threshold_analysis_mod`; add `Tool(name="tw_get_thresholds", description="Compact threshold/test report: detected VT1/VT2/VO2max/FatMax breakpoint times, VE targets, fitness level, zone time/kcal, and a truncated-test flag. Reads the detected breakpoints Tymewear already computed (new_zone_*).", inputSchema=GetActivityInput.model_json_schema())`; dispatch:

```python
        elif name == "tw_get_thresholds":
            params = GetActivityInput.model_validate(arguments)
            activity = await activities_mod.get_activity(client, params.activity_id, include=["predict_ve_v3"])
            profile = await profile_mod.get_profile(client)
            result = threshold_analysis_mod.get_thresholds(activity, profile)
```

(Note: pass `include=["predict_ve_v3"]` so `ve_curve_available`/`truncated_test` see the curve even though Task 4 omits it by default.)

- [ ] **Step 5 — run, expect PASS**; commit `feat: add tw_get_thresholds compact threshold report`.

---

## Task 6: New `tw_compute_power_at_threshold` tool

**Goal:** Pure-Python join — given threshold time offsets (fetched from the activity) and a caller-supplied power series, return mean watts in a window around each breakpoint. This is what the coach workflow (Plan B) calls with TrainingPeaks/Garmin power.

**Files:**
- Modify: `src/tymewear_mcp/tools/threshold_analysis.py` (add `compute_power_at_threshold`)
- Modify: `src/tymewear_mcp/tools/_validation.py` (`ComputePowerAtThresholdInput`)
- Modify: `src/tymewear_mcp/server.py`
- Test: `tests/test_tools/test_threshold_analysis.py`

**Interfaces:**
- Produces: `compute_power_at_threshold(threshold_times: dict[str, int | None], power_samples: list[list[float]], window_seconds: int = 15) -> dict` → `{name: {"power_watts": float|None, "samples": int, "at_seconds": int}}`.
- `ComputePowerAtThresholdInput(ActivityIdMixin)`: `activity_id`, `power_samples: list[list[float]]` (each `[t_seconds, watts]`), `window_seconds: int = 15`.

- [ ] **Step 1 — failing test**:

```python
from tymewear_mcp.tools.threshold_analysis import compute_power_at_threshold

def test_power_at_threshold_windowed_mean():
    samples = [[float(t), 100.0 + t] for t in range(0, 120)]   # watts ramps with time
    times = {"vt1": 60, "vt2": None}
    r = compute_power_at_threshold(times, samples, window_seconds=5)
    assert r["vt1"]["samples"] == 11           # 55..65 inclusive
    assert r["vt1"]["power_watts"] == 160.0     # mean of 155..165
    assert r["vt2"] is None

def test_power_no_samples_in_window():
    r = compute_power_at_threshold({"vt1": 5000}, [[0.0, 200.0]], window_seconds=15)
    assert r["vt1"]["power_watts"] is None and r["vt1"]["samples"] == 0
```

- [ ] **Step 2 — run, expect FAIL**.

- [ ] **Step 3 — implement** (append to `threshold_analysis.py`):

```python
def compute_power_at_threshold(threshold_times, power_samples, window_seconds=15):
    series = [(float(t), float(w)) for t, w in power_samples if w is not None]
    out: dict[str, Any] = {}
    for name, secs in threshold_times.items():
        if secs is None:
            out[name] = None
            continue
        window = [w for (t, w) in series if abs(t - secs) <= window_seconds]
        out[name] = {
            "power_watts": round(sum(window) / len(window), 1) if window else None,
            "samples": len(window),
            "at_seconds": secs,
        }
    return out
```

- [ ] **Step 4 — validation + server.** Add `ComputePowerAtThresholdInput` to `_validation.py`:

```python
class ComputePowerAtThresholdInput(ActivityIdMixin):
    activity_id: str = Field(description="Tyme Wear activity UUID to read threshold times from")
    power_samples: list[list[float]] = Field(description="Power series as [[t_seconds, watts], ...] from the matching TrainingPeaks/Garmin ride")
    window_seconds: int = Field(default=15, ge=0, le=120, description="Averaging half-window around each breakpoint")
```

In `server.py` register `tw_compute_power_at_threshold` (description: "Join Tyme Wear's detected threshold times to an external power series and return mean watts at VT1/VT2/VO2max/FatMax. Supply power_samples from TrainingPeaks/Garmin — Tyme Wear has no power."), dispatch:

```python
        elif name == "tw_compute_power_at_threshold":
            params = ComputePowerAtThresholdInput.model_validate(arguments)
            activity = await activities_mod.get_activity(client, params.activity_id, include=["predict_ve_v3"])
            profile = await profile_mod.get_profile(client)
            report = threshold_analysis_mod.get_thresholds(activity, profile)
            times = {k: (v["time_seconds"] if v else None) for k, v in report["detected_thresholds"].items()}
            result = {
                "activity_id": params.activity_id,
                "power_at_threshold": threshold_analysis_mod.compute_power_at_threshold(
                    times, params.power_samples, params.window_seconds),
                "ve_targets": report["ve_targets"],
                "truncated_test": report["truncated_test"],
            }
```

- [ ] **Step 5 — run full suite, expect PASS**; commit `feat: add tw_compute_power_at_threshold (VE-breakpoint × external power join)`.

---

## Task 7 (additive, optional): FIT-path power source

Only if a local-mode convenience is wanted. Add `power_samples_from_fit(path) -> list[list[float]]` in a new `tools/fit_power.py` guarded by `try: import fitparse`. Add `fitparse` to an optional extra in `pyproject.toml` (`[project.optional-dependencies] fit = ["fitparse>=1.2"]`). Add a `tw_power_at_threshold_from_fit` tool and **add it to `_PUBLIC_DISABLED_EXPORT_TOOLS`** (reads a local file). Defer until Tasks 1–6 land and are verified.

---

## Verification (end-to-end)

- [ ] `pytest -q` — full suite green.
- [ ] `ruff`/type-check if configured (`ruff check .` / `mypy` per repo config).
- [ ] Live MCP smoke against activity `e4ce60cb-1574-4db1-961e-0d033e32e57f` (a real ramp test):
  - `tw_get_ve_targets` → returns `{bike:{vt1:58.7,...}}` (no crash).
  - `tw_get_activities` with `sport=2` → returns results (no validation error).
  - `tw_get_activity` → now a few KB with `_omitted_fields` listing `x`, `predict_*_v3`, etc.
  - `tw_get_processed_data` → `{available:false, reason:"processed_data_not_available"}` (graceful, not an exception).
  - `tw_get_thresholds` → `detected_thresholds.vt1.time_seconds == 2247`, `ve_targets.vt2 == 114.0`, `truncated_test:false`.
  - `tw_compute_power_at_threshold` with a synthetic `power_samples=[[t, 200+t] for t in range(0,3300,1)]` → returns watts at each breakpoint time.
- [ ] Confirm public-mode tool list still excludes exports and includes the two new read tools.

---

## Follow-up Plan B — cycling-coach power-join workflow (separate plan)

After Tasks 1–6 land: explore the `cycling-coach` skill, then write a workflow that, for a Tymewear test, calls `tw_get_thresholds`, pulls the matching TrainingPeaks (`tp_*`) or Garmin (`garmin_*`) ride's power stream, converts it to `[[t,watts]]`, calls `tw_compute_power_at_threshold`, and reports power@VT1/VT2/VO2max. Requires exploring the coach skill's structure and the TP/Garmin power-stream shape — not yet read, so deferred to its own plan.

## Follow-up Plan C — deploy automation (separate plan)

After Tasks 1–6 land: inspect the existing Vercel setup (`public.py`, `serve-public`, any `vercel.json`/`vercel.ts`, the GitHub→Vercel link in commits `eb1ad5a`/`7aaa705`) and wire automatic deploy-on-merge so the trainer's instance picks up changes. Requires reading the deploy config — deferred to its own plan.

---

# POST-VERIFICATION ADDENDUM (live data, 2026-06-26)

Live checks against a ramp test (`e4ce60cb`) and a long endurance ride (`a343b98b`) changed the design. **Tymewear DOES expose power-at-threshold** (estimated from ventilation/METs — `ext_bike_power` is empty but the UI value lives in the metric arrays and the workout-zone-detection endpoint). The headline is now a per-activity *insights* tool, not a test-only threshold tool.

## Verified per-activity data map

| Data | Source | Status |
|------|--------|--------|
| Zone time/cal/%, threshold VE+HR+confidence, `_quality`, estimated power (`steady_state_intensity`) | `tw_get_activity_workout_zone_detection` | ✅ works for **tests AND rides**, **labeled** — but 76–554 KB (needs slimming) |
| Breakpoint times (`new_zone_vt1/vt2/vo2max`), displayed power profile (250/290/350 W via `new_zone_*_metrics[12]/[24..26]`), fitness level, kcal/hr per zone | `tw_get_activity` detail | ✅ **tests only** (empty for rides); positional/unlabeled; blob is 3.9–10.8 MB |
| VE targets (VT1 58.7 / BP 77.6 / VT2 114 / VO2max 158.3) | profile | ✅ reliable |
| Per-**second** VE/power/HR stream | processed-data / strap-files | ⛔ gated (`raw_data_access:false` → 404/403). Only Tymewear can unlock |
| Per-second labeled CSV | `tw_export_csv_full` | 🐞 **broken** — saves a 404 HTML page as `.csv` |

## REVISED Task 5 — `tw_get_activity_insights` (supersedes `tw_get_thresholds`)

One tool, works for any activity. **Files:** add `extract_activity_insights(wzd, activity, profile)` to `tools/threshold_analysis.py`; register `tw_get_activity_insights` in `server.py`; tests in `test_threshold_analysis.py`.

**Handler** fetches three sources and merges:
```python
        elif name == "tw_get_activity_insights":
            params = GetActivityInput.model_validate(arguments)
            wzd = await activity_files_mod.get_activity_workout_zone_detection(client, params.activity_id)
            activity = await activities_mod.get_activity(client, params.activity_id, include=["predict_ve_v3"])
            profile = await profile_mod.get_profile(client)
            result = threshold_analysis_mod.extract_activity_insights(wzd, activity, profile)
```

**`extract_activity_insights(wzd, activity, profile)`** returns a compact labeled dict:
- `zones`: from `wzd["zone_summary_table"]` (time/cal/% per zone — already labeled, pass through).
- `thresholds`: from `wzd["thresholds_zone"]` — for each of VT1/VT2/Endurance present (skip `None` and `_quality`): `{ve, hr, confidence}`; merge estimated `power` from `wzd["steady_state_intensity"][name]["power"]`.
- `quality`: from `wzd["thresholds_zone"]["_quality"]` → `{fit_r2, per_threshold_confidence, reason}`.
- `min_max`: `wzd["min_max_used"]`.
- `detected_breakpoints` (tests only): `new_zone_vt1/vt2/vo2max/fatmax` → `_mmss_to_seconds`; `displayed_power` from `new_zone_*_metrics` index 12 & 24 (label both `instant_w`/`zone_avg_w`); `fitness_level`; `zone_time_kcal` from `new_zone_thresholds_kcal_hrs`.
- `ve_targets`: `_ve_targets(profile, activity.get("sport"))`.
- `truncated_test`: `bool(activity.get("predict_ve_v3"))` and VT2 detected but VO2max breakpoint empty.
- `note`: where measured power comes from (Plan B cross-check).

Decode-verification (lock in tests): VT1 VE≈60.7, VT2 VE≈113.3 (≈ profile 58.7/114) ; zone_summary Total kcal 643.9 == activity `summary[19]` 644. The earlier `tw_get_thresholds` (original Task 5) collapses into this tool — do not ship both.

## NEW Task A — fix `tw_export_csv_full` / `tw_export_csv` returning HTML

`exports.py` writes the response body to disk without checking it is CSV. When the endpoint 404s it saves `<!DOCTYPE html>...404`. Detect non-CSV (content-type not `text/csv` **or** body starts with `<!DOCTYPE`/`<html`) and return `{"available": False, "reason": "export_unavailable", "status_code": ...}` instead of saving garbage. Test with a mocked HTML response.

## NEW Task B — slim `tw_get_activity_workout_zone_detection`

It returns 76–554 KB because of per-second arrays. Strip `times_zone`, `ve_list_zone`, `prob_list_zone`, and the `transition_points_zone[*].{HR,VE,HR_filt,VE_filt,...}` point-clouds by default (summarise as `_omitted_fields`), keeping `zone_summary_table`, `thresholds_zone`, `min_max_used`, `steady_state_intensity`, `model_version`, `available`. Reuse the `_describe_omitted` helper from Task 4. Add an `include` opt-in. Note: `tw_get_activity_insights` consumes the **full** wzd internally (it only needs the small labeled tables, so it is unaffected).

## Revised task order (high-certainty fixes first)

1. Task 1 (ve_targets) · Task 2 (sport) · Task 3 (processed-data graceful) · Task A (CSV-export graceful) — quick, unambiguous, immediately useful.
2. Task 4 (slim activity) · Task B (slim wzd) — kill the blobs.
3. Revised Task 5 (`tw_get_activity_insights`) — the headline.
4. Task 6 (`tw_compute_power_at_threshold`) + Plan B (coach workflow) — measured cross-check.
5. Plan C (deploy automation).
