import pytest
from pydantic import ValidationError

from tymewear_mcp.tools import _validation as validation_mod
from tymewear_mcp.tools._validation import (
    ExportInput,
    GetActivitiesInput,
    GetActivityInput,
    GetProcessedDataInput,
    TagNewZoneInput,
    TagThresholdInput,
)

ACTIVITY_ID_MODELS = [
    (GetActivityInput, {}),
    (GetProcessedDataInput, {}),
    (TagThresholdInput, {"threshold_type": "vt1"}),
    (TagNewZoneInput, {"zone_type": "vt1"}),
    (ExportInput, {}),
]


@pytest.mark.parametrize(("model", "extra"), ACTIVITY_ID_MODELS)
@pytest.mark.parametrize("activity_id", ["abc-12345", "550e8400-e29b-41d4-a716-446655440000"])
def test_activity_id_models_accept_safe_path_segments(model, extra, activity_id):
    result = model(activity_id=activity_id, **extra)

    assert result.activity_id == activity_id


@pytest.mark.parametrize(("model", "extra"), ACTIVITY_ID_MODELS)
@pytest.mark.parametrize(
    "activity_id",
    [
        "",
        "   ",
        " abc-12345",
        "abc-12345 ",
        "abc/def",
        r"abc\def",
        "abc?def",
        "abc#def",
        ".",
        "..",
        "abc%2Fdef",
        "abc%252Fdef",
        r"abc%5Cdef",
        r"abc%255Cdef",
        "abc%3Fdef",
        "abc%23def",
        "%2e",
        "%2e%2e",
        "%252e%252e",
    ],
)
def test_activity_id_models_reject_unsafe_path_segments(model, extra, activity_id):
    with pytest.raises(ValidationError):
        model(activity_id=activity_id, **extra)


class TestSportCoercion:
    def test_string_sport_coerced_to_int(self):
        assert GetActivitiesInput.model_validate({"sport": "2"}).sport == 2

    def test_int_sport_still_works(self):
        assert GetActivitiesInput.model_validate({"sport": 2}).sport == 2

    def test_none_sport(self):
        assert GetActivitiesInput.model_validate({}).sport is None

    def test_invalid_sport_rejected(self):
        with pytest.raises(ValidationError):
            GetActivitiesInput.model_validate({"sport": "bike"})

    def test_sport_schema_allows_string_wire_value(self):
        # The MCP SDK validates raw wire args against this published schema BEFORE
        # pydantic coercion. A string "2" arriving over the wire must be permitted,
        # otherwise tw_get_activities(sport=2) fails with "'2' is not valid".
        sport_schema = GetActivitiesInput.model_json_schema()["properties"]["sport"]
        variants = sport_schema.get("anyOf", [sport_schema])
        assert any(v.get("type") == "string" for v in variants)


def _analysis_input_model():
    model = getattr(validation_mod, "GetActivityAnalysisInput", None)
    assert model is not None, "Task 5 requires strict GetActivityAnalysisInput validation"
    return model


def test_activity_analysis_input_schema_is_closed_and_matches_public_contract():
    model = _analysis_input_model()

    schema = model.model_json_schema()

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["activity_id"]
    assert schema["properties"]["activity_id"]["type"] == "string"
    assert schema["properties"]["offset"]["default"] == 0
    assert schema["properties"]["offset"]["minimum"] == 0
    assert schema["properties"]["limit"]["default"] == 500
    assert schema["properties"]["limit"]["minimum"] == 1
    assert schema["properties"]["limit"]["maximum"] == 1000
    channel_variants = schema["properties"]["channels"]["anyOf"]
    channel_array = next(variant for variant in channel_variants if variant.get("type") == "array")
    assert channel_array["minItems"] == 1
    assert channel_array["maxItems"] == 32
    assert channel_array["items"]["maxLength"] == 64
    assert channel_array["items"]["pattern"] == r"^[A-Za-z][A-Za-z0-9_. -]*$"
    assert schema["properties"]["include_location"] == {
        "default": False,
        "title": "Include Location",
        "type": "boolean",
    }


def test_activity_analysis_input_accepts_exact_valid_contract():
    model = _analysis_input_model()

    parsed = model.model_validate(
        {
            "activity_id": "550e8400-e29b-41d4-a716-446655440000",
            "offset": 4,
            "limit": 250,
            "channels": ["heart_rate", "position_lat"],
            "include_location": True,
        }
    )

    assert parsed.model_dump() == {
        "activity_id": "550e8400-e29b-41d4-a716-446655440000",
        "offset": 4,
        "limit": 250,
        "channels": ["heart_rate", "position_lat"],
        "include_location": True,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"activity_id": "activity-123", "unexpected": "field"},
        {"activity_id": "activity-123", "offset": "0"},
        {"activity_id": "activity-123", "offset": True},
        {"activity_id": "activity-123", "offset": -1},
        {"activity_id": "activity-123", "limit": "500"},
        {"activity_id": "activity-123", "limit": True},
        {"activity_id": "activity-123", "limit": 0},
        {"activity_id": "activity-123", "limit": 1001},
        {"activity_id": "activity-123", "include_location": "false"},
        {"activity_id": "activity-123", "include_location": 1},
        {"activity_id": "activity-123", "include_location": []},
        {"activity_id": "activity-123", "include_location": None},
    ],
)
def test_activity_analysis_input_rejects_missing_extra_or_coercive_values(payload):
    model = _analysis_input_model()

    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize(
    "channels",
    [
        [],
        ["heart_rate", 1],
        [""],
        ["!!!"],
        ["token_value"],
        ["x" * 65],
        [f"channel_{index}" for index in range(33)],
    ],
)
def test_activity_analysis_input_rejects_unsafe_or_unbounded_channels(channels):
    model = _analysis_input_model()

    with pytest.raises(ValidationError):
        model.model_validate({"activity_id": "activity-123", "channels": channels})
