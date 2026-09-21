"""Phase 10 GUI가 내부 record나 원본 경로를 받지 않도록 하는 읽기 모델."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PageRequest:
    page: int = 1
    page_size: int = 50


@dataclass(frozen=True)
class ImportHistoryItem:
    file_name: str
    sheet_name: str | None
    status: str
    started_at: str
    finished_at: str | None
    accepted_rows: int | None
    rejected_rows: int | None
    recovery_state: str


@dataclass(frozen=True)
class ImportHistoryPage:
    total_count: int
    page: int
    page_size: int
    total_pages: int
    items: tuple[ImportHistoryItem, ...]


@dataclass(frozen=True)
class DuplicateImportSummary:
    file_name: str
    status: str
    started_at: str
    finished_at: str | None
    accepted_rows: int | None


@dataclass(frozen=True)
class QCIssueRequest:
    page: int = 1
    page_size: int = 50
    severity: str | None = None
    review_status: str | None = None
    stream_code: str | None = None


@dataclass(frozen=True)
class QCIssueItem:
    issue_id: int = field(repr=False)
    issue_type: str
    severity: str
    review_status: str
    stream_code: str | None
    stream_name: str | None
    standard_name: str | None
    created_at: str
    reviewed_at: str | None
    reviewer_display_name: str | None


@dataclass(frozen=True)
class QCIssuePage:
    total_count: int
    page: int
    page_size: int
    total_pages: int
    items: tuple[QCIssueItem, ...]


class Phase10ReadError(Exception):
    def __init__(self):
        super().__init__("목록을 불러오지 못했습니다.")


class InvalidPhase10ReadRequest(Phase10ReadError):
    def __init__(self):
        Exception.__init__(self, "조회 조건을 확인해야 합니다.")
