import pytest
from pydantic import ValidationError

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
