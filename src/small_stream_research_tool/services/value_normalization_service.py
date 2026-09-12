"""I/O 없는 보수적 변환. 단위·timezone·자료 의미를 추정하지 않는다."""

import math
import re
from datetime import date, datetime
from decimal import Decimal, DecimalException

from small_stream_research_tool.models.excel import ExcelCell, ExcelFormula
from small_stream_research_tool.models.import_preparation_errors import ValueNormalizationError

_REAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_INTEGER = re.compile(r"[+-]?[0-9]+")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_DATETIME = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])?"
)


def normalize_cell(cell: ExcelCell, data_type: str) -> float | int | str | None:
    """결측은 None, 실패는 안전한 예외. formula/error는 결측보다 먼저 검사한다."""
    if cell.is_formula or cell.value_type == "f" or isinstance(cell.value, ExcelFormula):
        raise ValueNormalizationError("FORMULA_CELL", "수식 셀은 저장 후보로 사용할 수 없습니다.")
    if cell.value_type == "e":
        raise ValueNormalizationError("EXCEL_ERROR_CELL", "Excel 오류 셀은 저장할 수 없습니다.")
    value = cell.value
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        if isinstance(value, str):
            value.encode("utf-8")
            value = value.strip()
        if data_type == "REAL":
            if type(value) not in (int, float) and not (
                isinstance(value, str) and _REAL.fullmatch(value)
            ):
                raise ValueError
            result = float(value)
            if not math.isfinite(result) or (result == 0 and Decimal(str(value)) != 0):
                raise ValueError
            return result
        if data_type == "INTEGER":
            if type(value) is int:
                result = value
            elif type(value) is float and math.isfinite(value) and value.is_integer():
                result = int(value)
            elif isinstance(value, str) and _INTEGER.fullmatch(value):
                result = int(value)
            else:
                raise ValueError
            if not -(2**63) <= result < 2**63:
                raise ValueError
            return result
        if data_type == "TEXT" and isinstance(value, str):
            return value
        if data_type == "DATE":
            if type(value) is date:
                return value.isoformat()
            if isinstance(value, str) and _DATE.fullmatch(value):
                return date.fromisoformat(value).isoformat()
        if data_type == "DATETIME":
            if type(value) is datetime:
                return value.isoformat()
            if isinstance(value, str) and _DATETIME.fullmatch(value):
                # -00:00은 알려지지 않은 offset일 수 있으므로 UTC로 바꾸지 않는다.
                if value.endswith("-00:00"):
                    raise ValueError
                return datetime.fromisoformat(value).isoformat()
    except (ValueError, OverflowError, UnicodeError, DecimalException):
        pass
    raise ValueNormalizationError(
        "CONVERSION_FAILED", "값을 사전 자료형의 유효한 저장 후보로 변환할 수 없습니다."
    ) from None


def original_value_text(cell: ExcelCell) -> str:
    """성공한 변환에만 사용한다. 문자열은 공백까지 보존한다."""
    value = cell.value
    if isinstance(value, str):
        return value
    if type(value) in (date, datetime):
        return value.isoformat()
    if type(value) in (int, float):
        return str(value)
    raise ValueNormalizationError("ORIGINAL_VALUE_INVALID", "원본 표현을 준비할 수 없습니다.")
