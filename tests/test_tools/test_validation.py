import pytest
from pydantic import ValidationError

from tymewear_mcp.tools._validation import (
    ExportInput,
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
