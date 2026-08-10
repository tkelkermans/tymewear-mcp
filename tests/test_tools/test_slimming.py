"""Tests for the shared heavy-field slimming helper."""

from tymewear_mcp.tools._slimming import describe_omitted, slim_dict


class TestDescribeOmitted:
    def test_list_length(self):
        assert describe_omitted([1, 2, 3]) == {"type": "list", "length": 3}

    def test_scalar_no_length(self):
        assert describe_omitted(42) == {"type": "int"}


class TestSlimDict:
    def test_strips_heavy_fields(self):
        data = {"keep": 1, "big": list(range(100))}
        result = slim_dict(data, frozenset({"big"}), [])
        assert "big" not in result
        assert result["keep"] == 1
        assert result["_omitted_fields"]["big"] == {"type": "list", "length": 100}

    def test_include_overrides(self):
        data = {"big": [1, 2]}
        result = slim_dict(data, frozenset({"big"}), ["big"])
        assert result["big"] == [1, 2]
        assert "_omitted_fields" not in result

    def test_no_heavy_fields_no_marker(self):
        data = {"a": 1}
        result = slim_dict(data, frozenset({"big"}), [])
        assert result == {"a": 1}

    def test_non_dict_passthrough(self):
        assert slim_dict([1, 2], frozenset({"big"}), []) == [1, 2]
