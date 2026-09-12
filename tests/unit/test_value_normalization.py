"""모든 값은 synthetic이다. DB 없이 변환의 경계와 모델 불변조건을 검사한다."""

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone

import pytest

from small_stream_research_tool.models.excel import ExcelCell, ExcelFormula
from small_stream_research_tool.models.import_preparation import (
    ImportFieldPolicy,
    PreparedCharacteristicValue,
    PreparedStreamData,
)
from small_stream_research_tool.models.import_preparation_errors import (
    InvalidPreparationArgumentError,
    ValueNormalizationError,
)
from small_stream_research_tool.services.value_normalization_service import (
    normalize_cell,
    original_value_text,
)


def cell(value, **changes):
    return replace(ExcelCell(8, 3, "C", value, "s", False, "General"), **changes)


@pytest.mark.parametrize("data_type", ["REAL", "INTEGER", "TEXT", "DATE", "DATETIME"])
@pytest.mark.parametrize("value", [None, "", " \t\n "])
def test_missing(data_type, value):
    assert normalize_cell(cell(value), data_type) is None


@pytest.mark.parametrize(
    "data_type,value,expected",
    [
        ("REAL", 4, 4.0),
        ("REAL", 4.24, 4.24),
        ("REAL", "4.24", 4.24),
        ("REAL", " 4.24 ", 4.24),
        ("REAL", "4", 4.0),
        ("REAL", "1.2e2", 120.0),
        ("REAL", "0", 0.0),
        ("REAL", "-2.5", -2.5),
        ("INTEGER", 3, 3),
        ("INTEGER", 3.0, 3),
        ("INTEGER", "3", 3),
        ("INTEGER", " 3 ", 3),
        ("INTEGER", "-3", -3),
        ("INTEGER", 0, 0),
        ("INTEGER", 2**63 - 1, 2**63 - 1),
        ("INTEGER", -(2**63), -(2**63)),
        ("TEXT", "abc", "abc"),
        ("TEXT", "  Synthetic  A  ", "Synthetic  A"),
        ("TEXT", "-", "-"),
        ("TEXT", "001", "001"),
        ("DATE", date(2026, 9, 12), "2026-09-12"),
        ("DATE", "2026-09-12", "2026-09-12"),
        ("DATE", "2024-02-29", "2024-02-29"),
        ("DATETIME", datetime(2026, 9, 12, 15, 30), "2026-09-12T15:30:00"),
        ("DATETIME", "2026-09-12 15:30:00", "2026-09-12T15:30:00"),
        ("DATETIME", "2026-09-12T15:30:00.123456", "2026-09-12T15:30:00.123456"),
        ("DATETIME", "2026-09-12T15:30:00+09:00", "2026-09-12T15:30:00+09:00"),
        ("DATETIME", "2026-09-12T15:30:00Z", "2026-09-12T15:30:00+00:00"),
        (
            "DATETIME",
            datetime(2026, 9, 12, 15, 30, tzinfo=timezone(timedelta(hours=-4))),
            "2026-09-12T15:30:00-04:00",
        ),
    ],
)
def test_success(data_type, value, expected):
    source = cell(value)
    result = normalize_cell(source, data_type)
    assert result == expected and type(result) is type(expected)
    assert source.value == value
    assert original_value_text(source) == (
        value.isoformat() if isinstance(value, date) else str(value)
    )


@pytest.mark.parametrize(
    "data_type,value",
    [
        *(
            ("REAL", value)
            for value in [
                True,
                False,
                float("nan"),
                float("inf"),
                float("-inf"),
                "NaN",
                "Inf",
                "4.24 km",
                "약 4.2",
                "4,24",
                "1_000",
                "４",
                "1e999",
                "1e-999",
            ]
        ),
        *(
            ("INTEGER", value)
            for value in [
                True,
                False,
                3.2,
                "3.2",
                "3.0",
                "3개",
                float("nan"),
                float("inf"),
                "3e0",
                2**63,
                -(2**63) - 1,
                "９",
            ]
        ),
        *(("TEXT", value) for value in [3, 3.0, True, date(2026, 9, 12), datetime(2026, 9, 12)]),
        *(
            ("DATE", value)
            for value in [
                datetime(2026, 9, 12),
                "09/12/2026",
                "2026.09.12",
                "9월 12일",
                "2026-02-29",
                "20260912",
                40000,
            ]
        ),
        *(
            ("DATETIME", value)
            for value in [
                date(2026, 9, 12),
                "2026-09-12",
                "09/12/2026 15:30",
                "2026-09-12T25:00:00",
                "2026-09-12T15:30:00.1234567",
                "2026-09-12T15:30:00-00:00",
                "2026-09-12T15:30:00+09:99",
            ]
        ),
        ("REAL", "1e-99999999999999999999999999"),
        ("NUMBER", 3),
        ("TEXT", "\ud800"),
    ],
)
def test_failure(data_type, value):
    with pytest.raises(ValueNormalizationError, match="사전 자료형") as error:
        normalize_cell(cell(value), data_type)
    assert error.value.code == "CONVERSION_FAILED"


@pytest.mark.parametrize(
    "source,code",
    [
        (cell("=1+2", is_formula=True), "FORMULA_CELL"),
        (cell(None, value_type="f"), "FORMULA_CELL"),
        (cell(ExcelFormula("array", "=1+2", ())), "FORMULA_CELL"),
        (cell("#DIV/0!", value_type="e"), "EXCEL_ERROR_CELL"),
        (cell(None, value_type="e"), "EXCEL_ERROR_CELL"),
    ],
)
def test_formula_and_error_before_missing(source, code):
    with pytest.raises(ValueNormalizationError) as error:
        normalize_cell(source, "REAL")
    assert error.value.code == code
    assert "1+2" not in str(error.value) and "#DIV/0!" not in str(error.value)


def candidate(**changes):
    kwargs = dict(
        dictionary_id=7,
        data_type="TEXT",
        source_column_index=3,
        source_row=8,
        value_text="Synthetic",
        original_value="  Synthetic ",
        unit_id=2,
    )
    return PreparedCharacteristicValue(**(kwargs | changes))


def test_candidate_metadata_and_immutable():
    result = candidate()
    assert (
        result.dictionary_id,
        result.source_column_index,
        result.source_row,
        result.unit_id,
    ) == (7, 3, 8, 2)
    assert result.original_value == "  Synthetic " and "Synthetic" not in repr(result)
    with pytest.raises(FrozenInstanceError):
        result.value_text = "changed"


@pytest.mark.parametrize(
    "changes",
    [
        {"value_text": None},
        {"value_integer": 3},
        {"value_number": 3.0},
        {"data_type": "REAL"},
        {"value_text": ""},
        {"value_text": "  "},
        {"source_row": 0},
        {"source_column_index": 0},
        {"source_column_index": 16385},
        {"dictionary_id": True},
        {"unit_id": 0},
        {"data_type": "REAL", "value_text": None, "value_number": float("nan")},
        {"data_type": "INTEGER", "value_text": None, "value_integer": True},
        {"data_type": "INTEGER", "value_text": None, "value_integer": 2**63},
        {"data_type": "DATE", "value_text": None, "value_date": "2026-02-29"},
        {"data_type": "DATETIME", "value_text": None, "value_date": "2026-09-12"},
    ],
)
def test_invalid_candidate(changes):
    with pytest.raises(InvalidPreparationArgumentError):
        candidate(**changes)


def test_core_model():
    core = PreparedStreamData("12345678009", "12", "345", "678", "009", "Synthetic Stream A")
    with pytest.raises(FrozenInstanceError):
        core.stream_name = "changed"
    for changes in (
        {"stream_name": ""},
        {"stream_serial_no": "008"},
        {"optional_fields": (("source_latitude", 91.0),)},
        {"optional_fields": (("created_at", "synthetic"),)},
    ):
        with pytest.raises(InvalidPreparationArgumentError):
            replace(core, **changes)


def test_policy_immutable_exact_names():
    assert ImportFieldPolicy().excluded_internal_names == frozenset()
    for names in (set(), ["synthetic"], frozenset({" x "})):
        with pytest.raises(InvalidPreparationArgumentError):
            ImportFieldPolicy(names)
