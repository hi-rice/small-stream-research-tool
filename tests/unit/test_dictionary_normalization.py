"""별칭 표기 정규화가 연구 의미/단위를 합치지 않는지 검증한다."""

import pytest

from small_stream_research_tool.models.dictionary_errors import InvalidDictionaryDefinitionError
from small_stream_research_tool.services.dictionary_service import normalize_alias


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  TEST\t Area\n", "test area"),
        ("TEST  AREA", "test area"),
        ("가상", "가상"),
        ("TEST(km²)", "test(km²)"),
    ],
)
def test_normalization(raw, expected):
    assert normalize_alias(raw) == expected
    assert normalize_alias(expected) == expected


@pytest.mark.parametrize(
    "a,b",
    [
        ("test area", "testarea"),
        ("area", "basin area"),
        ("x(km²)", "x(km2)"),
        ("x(m)", "x(mm)"),
        ("x-y", "xy"),
    ],
)
def test_meaningful_distinctions_preserved(a, b):
    assert normalize_alias(a) != normalize_alias(b)


@pytest.mark.parametrize("raw", ["", " \t\n", None, 123, "test\0"])
def test_invalid_alias(raw):
    with pytest.raises(InvalidDictionaryDefinitionError):
        normalize_alias(raw)
