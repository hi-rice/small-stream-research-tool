"""I/O 없이 소하천 관리코드 후보를 구성·검증한다. 원본을 보정하지 않는다."""

import math
from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType

from small_stream_research_tool.models.excel import ExcelCell
from small_stream_research_tool.models.stream_code import (
    CodeStatus,
    ComparisonStatus,
    StreamCodeComponentResult,
    StreamCodeIssue,
    StreamCodeValidationResult,
)
from small_stream_research_tool.models.stream_code_errors import StreamCodeArgumentError

COMPONENT_WIDTHS = MappingProxyType(
    {
        "province_code": 2,
        "city_county_code": 3,
        "town_code": 3,
        "stream_serial_no": 3,
    }
)

_MESSAGES = {
    "VALID": "소하천 관리코드 형식의 문자열 후보입니다.",
    "MISSING": "소하천 관리코드 값이 없습니다.",
    "INVALID_FORMAT": "소하천 관리코드는 음이 아닌 정수 또는 ASCII 숫자 문자열이어야 합니다.",
    "INVALID_LENGTH": "소하천 관리코드 후보의 길이가 기대 길이와 다릅니다.",
    "AMBIGUOUS_NUMERIC_WIDTH": "숫자의 자릿수가 부족하며 선행 0을 복원할 서식 근거가 없습니다.",
    "UNSUPPORTED_NUMBER_FORMAT": "지원하지 않는 숫자 서식이므로 후보를 확정하지 않습니다.",
    "EXCEL_FORMULA_OR_ERROR": "수식 또는 Excel 오류 셀은 관리코드 후보로 사용하지 않습니다.",
}


def _normalize(name: str, value: object, width: int, number_format: str | None):
    if number_format is not None and not isinstance(number_format, str):
        raise StreamCodeArgumentError("number_format은 문자열 또는 None이어야 합니다.")
    candidate = None
    steps = []

    def result(status: CodeStatus, code: str | None = None):
        code = status.value if code is None else code
        return StreamCodeComponentResult(
            name,
            value,
            number_format,
            candidate,
            width,
            status,
            code,
            _MESSAGES[code],
            tuple(steps),
        )

    if value is None:
        return result(CodeStatus.MISSING)
    if isinstance(value, str):
        candidate = value.strip()
        if candidate != value:
            steps.append("TRIM_WHITESPACE")
        if not candidate:
            candidate = None
            return result(CodeStatus.MISSING)
        if not all("0" <= char <= "9" for char in candidate):
            return result(CodeStatus.INVALID_FORMAT)
        # 문자열은 이미 원본 자릿수가 있다. 숫자 서식으로 패딩하지 않는다.
        return result(CodeStatus.VALID if len(candidate) == width else CodeStatus.INVALID_LENGTH)
    if type(value) not in (int, float):
        return result(CodeStatus.INVALID_FORMAT)
    if type(value) is float:
        if not math.isfinite(value) or not value.is_integer() or math.copysign(1, value) < 0:
            return result(CodeStatus.INVALID_FORMAT)
    elif value < 0:
        return result(CodeStatus.INVALID_FORMAT)
    # 폭 초과 숫자는 변환 전에 거부한다. 거대 int/float를 잘라내거나 복원하지 않는다.
    if value >= 10**width:
        return result(CodeStatus.INVALID_LENGTH)
    candidate = str(int(value)) if type(value) is float else str(value)
    steps.append("INTEGRAL_FLOAT_TO_TEXT" if type(value) is float else "INTEGER_TO_TEXT")
    if number_format == "0" * width:
        if len(candidate) < width:
            candidate = candidate.zfill(width)
            steps.append("ZERO_FORMAT_PADDING")
        return result(CodeStatus.VALID)
    if number_format not in (None, "General"):
        return result(CodeStatus.AMBIGUOUS, "UNSUPPORTED_NUMBER_FORMAT")
    if len(candidate) != width:
        return result(CodeStatus.AMBIGUOUS, "AMBIGUOUS_NUMERIC_WIDTH")
    # 숫자 자체가 정확한 폭이면 패딩 없는 후보를 허용한다. 변환 사실과 원본은 유지한다.
    return result(CodeStatus.VALID)


def normalize_component(
    name: str,
    value: object,
    *,
    expected_width: int | None = None,
    number_format: str | None = None,
) -> StreamCodeComponentResult:
    if not isinstance(name, str) or name not in COMPONENT_WIDTHS:
        raise StreamCodeArgumentError("지원하는 소하천 관리코드 구성요소 이름이 필요합니다.")
    width = COMPONENT_WIDTHS[name]
    if expected_width is not None and (type(expected_width) is not int or expected_width != width):
        raise StreamCodeArgumentError("expected_width는 해당 구성요소의 확정 길이와 같아야 합니다.")
    return _normalize(name, value, width, number_format)


def validate_source_code(
    value: object,
    *,
    number_format: str | None = None,
) -> StreamCodeComponentResult:
    return _normalize("stream_code", value, 11, number_format)


def validate_stream_code(
    *,
    source_code: object = None,
    province_code: object = None,
    city_county_code: object = None,
    town_code: object = None,
    stream_serial_no: object = None,
    number_formats: Mapping[str, str | None] | None = None,
) -> StreamCodeValidationResult:
    if number_formats is None:
        number_formats = {}
    if not isinstance(number_formats, Mapping) or any(
        key not in (*COMPONENT_WIDTHS, "stream_code") for key in number_formats
    ):
        raise StreamCodeArgumentError(
            "number_formats에는 관리코드 필드별 서식만 지정할 수 있습니다."
        )
    source = validate_source_code(source_code, number_format=number_formats.get("stream_code"))
    raw_components = (province_code, city_county_code, town_code, stream_serial_no)
    components = tuple(
        normalize_component(name, value, number_format=number_formats.get(name))
        for name, value in zip(COMPONENT_WIDTHS, raw_components, strict=True)
    )
    return _combine_results(source, components)


def _combine_results(source, components) -> StreamCodeValidationResult:
    generated = (
        "".join(part.normalized_value for part in components)
        if all(part.valid for part in components)
        else None
    )
    issues = [
        StreamCodeIssue(part.name, part.code, part.message)
        for part in (source, *components)
        if not part.valid
    ]
    comparison = ComparisonStatus.NOT_COMPARABLE
    if source.valid and generated is not None:
        comparison = (
            ComparisonStatus.MATCH
            if source.normalized_value == generated
            else ComparisonStatus.MISMATCH
        )
        if comparison == ComparisonStatus.MISMATCH:
            issues.append(
                StreamCodeIssue(
                    "stream_code",
                    "SOURCE_COMPONENT_MISMATCH",
                    "원본 관리코드와 구성요소 조합값이 일치하지 않습니다.",
                )
            )
    elif source.status == CodeStatus.MISSING and generated is not None:
        issues.append(
            StreamCodeIssue(
                "stream_code",
                "SOURCE_MISSING_GENERATED_AVAILABLE",
                "원본 관리코드는 없으며 구성요소로 생성한 후보가 있습니다.",
            )
        )
    return StreamCodeValidationResult(source, components, generated, comparison, tuple(issues))


def normalize_excel_code_cell(name: str, cell: ExcelCell) -> StreamCodeComponentResult:
    """호출자가 이미 선택한 셀만 처리한다. workbook/컬럼 탐색은 하지 않는다."""
    if not isinstance(cell, ExcelCell):
        raise StreamCodeArgumentError("ExcelCell 인자가 필요합니다.")
    result = (
        validate_source_code(cell.value, number_format=cell.number_format)
        if name == "stream_code"
        else normalize_component(name, cell.value, number_format=cell.number_format)
    )
    if cell.is_formula or cell.value_type in ("f", "e"):
        return replace(
            result,
            normalized_value=None,
            status=CodeStatus.INVALID_FORMAT,
            code="EXCEL_FORMULA_OR_ERROR",
            message=_MESSAGES["EXCEL_FORMULA_OR_ERROR"],
            normalization_steps=(),
        )
    return result


def validate_stream_code_cells(cells: Mapping[str, ExcelCell]) -> StreamCodeValidationResult:
    """선택된 semantic별 ExcelCell을 기존 정규화/비교 로직에 연결한다."""
    if not isinstance(cells, Mapping) or any(
        key not in (*COMPONENT_WIDTHS, "stream_code") for key in cells
    ):
        raise StreamCodeArgumentError("관리코드 필드별 ExcelCell mapping이 필요합니다.")
    source = (
        normalize_excel_code_cell("stream_code", cells["stream_code"])
        if "stream_code" in cells
        else validate_source_code(None)
    )
    components = tuple(
        normalize_excel_code_cell(name, cells[name])
        if name in cells
        else normalize_component(name, None)
        for name in COMPONENT_WIDTHS
    )
    return _combine_results(source, components)
