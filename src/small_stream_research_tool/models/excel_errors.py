"""원본 경로/값을 메시지에 포함하지 않는 Excel application 오류."""


class ExcelError(Exception):
    """Excel 읽기 오류의 공통 기반."""


class ExcelFileNotFoundError(ExcelError):
    """파일이 존재하지 않는다."""


class UnsupportedExcelFormatError(ExcelError):
    """지원하지 않는 파일 형식."""


class ExcelWorkbookReadError(ExcelError):
    """파일 접근 또는 workbook 해석 실패."""


class ExcelSheetNotFoundError(ExcelError):
    """시트가 존재하지 않는다."""


class UnsupportedExcelSheetError(ExcelError):
    """셀 데이터가 없는 chart sheet 등에 행 읽기를 요청했다."""


class InvalidHeaderRangeError(ExcelError):
    """헤더 범위가 유효하지 않다."""


class InvalidDataRangeError(ExcelError):
    """데이터/preview 범위가 유효하지 않다."""


class ExcelReaderClosedError(ExcelError):
    """닫힌 Reader를 사용했다."""
