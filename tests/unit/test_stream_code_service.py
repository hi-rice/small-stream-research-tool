"""실제 연구 식별자를 사용하지 않는 소하천 관리코드 순수 함수 검증."""

from dataclasses import FrozenInstanceError
from datetime import datetime
from itertools import product

import pytest

from small_stream_research_tool.models.excel import ExcelCell
from small_stream_research_tool.models.stream_code import CodeStatus, ComparisonStatus
from small_stream_research_tool.models.stream_code_errors import StreamCodeArgumentError
from small_stream_research_tool.services.stream_code_service import (
    COMPONENT_WIDTHS,
    normalize_component,
    normalize_excel_code_cell,
    validate_source_code,
    validate_stream_code,
)

SYNTHETIC = dict(
    province_code="12", city_county_code="345", town_code="678", stream_serial_no="009"
)


@pytest.mark.parametrize(
    "raw,status,candidate",
    [
        ("009", "VALID", "009"),
        (" 009\t", "VALID", "009"),
        ("0 09", "INVALID_FORMAT", "0 09"),
        ("００９", "INVALID_FORMAT", "００９"),
        ("٠٠٩", "INVALID_FORMAT", "٠٠٩"),
        ("ABC", "INVALID_FORMAT", "ABC"),
        ("+09", "INVALID_FORMAT", "+09"),
        ("-09", "INVALID_FORMAT", "-09"),
        ("9.0", "INVALID_FORMAT", "9.0"),
        ("9e0", "INVALID_FORMAT", "9e0"),
        ("0\x009", "INVALID_FORMAT", "0\x009"),
        (None, "MISSING", None),
        ("", "MISSING", None),
        (" \t\n", "MISSING", None),
        ("09", "INVALID_LENGTH", "09"),
        ("0009", "INVALID_LENGTH", "0009"),
        (True, "INVALID_FORMAT", None),
        (False, "INVALID_FORMAT", None),
        (b"009", "INVALID_FORMAT", None),
        (datetime(2000, 1, 1), "INVALID_FORMAT", None),
        ([], "INVALID_FORMAT", None),
    ],
)
def test_component_strings_and_invalid_types(raw, status, candidate):
    result = normalize_component("stream_serial_no", raw)
    assert result.status == status and result.normalized_value == candidate
    assert result.raw_value is raw
    assert result.expected_width == 3
    assert result.valid == (status == "VALID")


@pytest.mark.parametrize(
    "raw,fmt,status,candidate",
    [
        (123, None, "VALID", "123"),
        (123, "General", "VALID", "123"),
        (9, None, "AMBIGUOUS", "9"),
        (9, "General", "AMBIGUOUS", "9"),
        (9, "000", "VALID", "009"),
        (0, "000", "VALID", "000"),
        (9.0, "000", "VALID", "009"),
        (123.0, None, "VALID", "123"),
        (9.0, None, "AMBIGUOUS", "9"),
        (9.5, "000", "INVALID_FORMAT", None),
        (-9, "000", "INVALID_FORMAT", None),
        (-0.0, "000", "INVALID_FORMAT", None),
        (float("nan"), "000", "INVALID_FORMAT", None),
        (float("inf"), None, "INVALID_FORMAT", None),
        (float("-inf"), None, "INVALID_FORMAT", None),
        (1000, "000", "INVALID_LENGTH", None),
        (1e100, None, "INVALID_LENGTH", None),
        pytest.param(10**5000, None, "INVALID_LENGTH", None, id="oversized-integer"),
        ("09", "000", "INVALID_LENGTH", "09"),
        ("009", "#,##0", "VALID", "009"),
    ],
)
def test_numeric_policy(raw, fmt, status, candidate):
    result = normalize_component("stream_serial_no", raw, number_format=fmt)
    assert result.status == status and result.normalized_value == candidate
    assert result.raw_value is raw and result.number_format == fmt


@pytest.mark.parametrize(
    "fmt", ["000.00", "#,##0", "[Red]000", "00", "0000", "0.00E+00", "000;000", " 000", "", "@"]
)
def test_unsupported_formats_never_restore(fmt):
    for value in (9, 123):
        result = normalize_component("town_code", value, number_format=fmt)
        assert result.status == CodeStatus.AMBIGUOUS
        assert result.normalized_value == str(value)
        assert "ZERO_FORMAT_PADDING" not in result.normalization_steps


def test_normalization_steps_and_raw_preservation():
    text = normalize_component("province_code", " 01 ")
    assert text.normalization_steps == ("TRIM_WHITESPACE",)
    number = normalize_component("town_code", 9.0, number_format="000")
    assert number.normalization_steps == ("INTEGRAL_FLOAT_TO_TEXT", "ZERO_FORMAT_PADDING")
    assert type(number.raw_value) is float
    assert normalize_component("province_code", 12).normalization_steps == ("INTEGER_TO_TEXT",)


@pytest.mark.parametrize(
    "raw,status",
    [
        ("12345678009", "VALID"),
        (" 12345678009 ", "VALID"),
        ("01234567009", "VALID"),
        ("1234567800", "INVALID_LENGTH"),
        ("012345678009", "INVALID_LENGTH"),
        ("12345A78009", "INVALID_FORMAT"),
        ("１２３４５６７８００９", "INVALID_FORMAT"),
        (None, "MISSING"),
        ("", "MISSING"),
        (12345678009, "VALID"),
        (1234567009, "AMBIGUOUS"),
        (12345678009.0, "VALID"),
        ("1.234E10", "INVALID_FORMAT"),
    ],
)
def test_source_independent_validation(raw, status):
    result = validate_source_code(raw)
    assert result.status == status and result.expected_width == 11
    assert result.raw_value is raw


def test_full_code_format_and_order():
    source = validate_source_code(1234567009, number_format="00000000000")
    assert source.normalized_value == "01234567009" and source.valid
    result = validate_stream_code(**SYNTHETIC)
    assert result.generated_code == "12345678009" and result.generated_valid
    assert result.source.status == CodeStatus.MISSING
    assert result.comparison_status == ComparisonStatus.NOT_COMPARABLE
    assert "SOURCE_MISSING_GENERATED_AVAILABLE" in [i.code for i in result.issues]


@pytest.mark.parametrize(
    "source,comparison",
    [("12345678009", "MATCH"), ("12345678008", "MISMATCH"), ("ABC", "NOT_COMPARABLE")],
)
def test_comparison_does_not_overwrite(source, comparison):
    before = SYNTHETIC.copy()
    result = validate_stream_code(source_code=source, **before)
    assert result.comparison_status == comparison
    assert result.source_code == source
    assert result.generated_code == "12345678009"
    assert before == SYNTHETIC
    assert ("SOURCE_COMPONENT_MISMATCH" in [i.code for i in result.issues]) == (
        comparison == "MISMATCH"
    )
    assert result == validate_stream_code(source_code=source, **before)
    with pytest.raises(FrozenInstanceError):
        result.generated_code = source


@pytest.mark.parametrize("name", list(COMPONENT_WIDTHS))
@pytest.mark.parametrize("bad", [None, "X", "", "1", 1])
def test_each_component_blocks_generation_without_invalidating_source(name, bad):
    values = {**SYNTHETIC, name: bad}
    result = validate_stream_code(source_code="12345678009", **values)
    assert result.source_valid and result.generated_code is None
    assert not result.generated_valid
    assert result.comparison_status == ComparisonStatus.NOT_COMPARABLE
    assert next(p for p in result.components if p.name == name).raw_value is bad


def test_all_missing():
    result = validate_stream_code()
    assert not result.source_valid and not result.generated_valid
    assert len(result.issues) == 5


def test_formats_are_applied_per_field():
    result = validate_stream_code(
        source_code="12345678009",
        **{**SYNTHETIC, "stream_serial_no": 9},
        number_formats={"stream_serial_no": "000"},
    )
    assert result.comparison_status == ComparisonStatus.MATCH
    assert result.components[-1].raw_value == 9
    assert result.components[-1].number_format == "000"


@pytest.mark.parametrize(
    "value,fmt,status,candidate",
    [
        (9, "000", "VALID", "009"),
        ("009", "General", "VALID", "009"),
        (9, "000.00", "AMBIGUOUS", "9"),
    ],
)
def test_excel_helper(value, fmt, status, candidate):
    cell = ExcelCell(2, 4, "D", value, "n" if type(value) is int else "s", False, fmt)
    result = normalize_excel_code_cell("stream_serial_no", cell)
    assert result.status == status and result.normalized_value == candidate
    assert cell.value == value and cell.number_format == fmt and cell.coordinate == "D2"


@pytest.mark.parametrize("formula,value_type", [(True, "n"), (False, "f"), (False, "e")])
def test_excel_formula_or_error_is_not_code(formula, value_type):
    cell = ExcelCell(2, 1, "A", "12345678009", value_type, formula, "General")
    result = normalize_excel_code_cell("stream_code", cell)
    assert result.status == CodeStatus.INVALID_FORMAT
    assert result.normalized_value is None and result.raw_value == cell.value


@pytest.mark.parametrize(
    "name,width",
    [
        ("unknown", 3),
        (None, 3),
        ([], 3),
        ("province_code", 3),
        ("town_code", 0),
        ("town_code", True),
        ("town_code", 3.0),
    ],
)
def test_api_name_and_width_errors(name, width):
    with pytest.raises(StreamCodeArgumentError):
        normalize_component(name, "123", expected_width=width)


@pytest.mark.parametrize("formats", [[], "000", {"unknown": "000"}, {"town_code": 3}])
def test_api_format_errors(formats):
    with pytest.raises(StreamCodeArgumentError):
        validate_stream_code(**SYNTHETIC, number_formats=formats)


def test_api_cell_error():
    with pytest.raises(StreamCodeArgumentError):
        normalize_excel_code_cell("town_code", "009")


def test_synthetic_boundary_invariants():
    for name, width in COMPONENT_WIDTHS.items():
        for value in (0, 1, 9, 10**width - 1):
            result = normalize_component(name, value, number_format="0" * width)
            assert result.valid and len(result.normalized_value) == width
            assert result.normalized_value.isascii() and result.normalized_value.isdecimal()
    for pieces in product(("00", "01", "99"), ("000", "009", "999"), repeat=1):
        result = validate_stream_code(
            province_code=pieces[0],
            city_county_code=pieces[1],
            town_code="000",
            stream_serial_no="009",
        )
        assert type(result.generated_code) is str and len(result.generated_code) == 11
        assert result.generated_code.isascii() and result.generated_code.isdecimal()
        assert result.generated_code == pieces[0] + pieces[1] + "000009"


def test_no_io_or_terminology_confusion(monkeypatch):
    import builtins
    import socket
    import sqlite3

    def forbidden(*args, **kwargs):
        pytest.fail("관리코드 검증에는 파일/DB/네트워크 I/O가 없어야 한다.")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    result = validate_stream_code(source_code="12345678008", **SYNTHETIC)
    assert result.comparison_status == ComparisonStatus.MISMATCH
    assert all("법정동" not in issue.message for issue in result.issues)
