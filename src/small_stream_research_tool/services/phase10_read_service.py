"""Phase 10 GUI의 Import/QC 목록 조회를 안전한 projection으로 제한한다."""

import re

from small_stream_research_tool.database.connection import read_transaction
from small_stream_research_tool.models.phase10_read import (
    DuplicateImportSummary,
    ImportHistoryItem,
    ImportHistoryPage,
    InvalidPhase10ReadRequest,
    PageRequest,
    Phase10ReadError,
    QCIssueItem,
    QCIssuePage,
    QCIssueRequest,
)
from small_stream_research_tool.repositories.phase10_query_repository import (
    Phase10QueryRepository,
)
from small_stream_research_tool.services.research_dictionary_bootstrap import (
    ResearchDictionaryBootstrapService,
)

SEVERITIES = frozenset(("ERROR", "WARNING", "INFO"))
REVIEW_STATUSES = frozenset(("UNREVIEWED", "IN_REVIEW", "CONFIRMED", "CORRECTED", "DEFERRED"))
ISSUE_TYPES = frozenset(
    (
        "REQUIRED_VALUE_MISSING",
        "NEGATIVE_VALUE",
        "VALUE_OUT_OF_RANGE",
        "REFERENCE_VALUE_MISMATCH",
        "UNIT_MISMATCH",
        "UNIT_MISSING",
        "UNIT_CONVERSION_MISSING",
        "STATISTICAL_OUTLIER_CANDIDATE",
    )
)


def _page(page, size):
    return type(page) is int and 1 <= page <= 2**31 and type(size) is int and 1 <= size <= 100


def _file_name(value):
    return value.replace("\\", "/").rsplit("/", 1)[-1] if value else ""


class Phase10ReadService:
    def __init__(self, connection):
        self._connection = connection
        self._repository = Phase10QueryRepository(connection)

    @staticmethod
    def _issue(row, approved):
        (
            issue_id,
            kind,
            severity,
            status,
            code,
            stream,
            name,
            created,
            reviewed,
            reviewer,
            item_id,
        ) = row
        return QCIssueItem(
            issue_id,
            kind if kind in ISSUE_TYPES else "OTHER_ISSUE",
            severity,
            status,
            code,
            stream,
            name if item_id in approved else None,
            created,
            reviewed,
            reviewer,
        )

    def list_import_history(self, request=None):
        request = PageRequest() if request is None else request
        if type(request) is not PageRequest or not _page(request.page, request.page_size):
            raise InvalidPhase10ReadRequest()
        try:
            with read_transaction(self._connection):
                total = self._repository.count_imports()
                rows = self._repository.page_imports(
                    request.page_size, (request.page - 1) * request.page_size
                )
            items = tuple(
                ImportHistoryItem(
                    _file_name(row[0]),
                    *row[1:],
                    "INSPECTION_REQUIRED" if row[2] == "RUNNING" else "NONE",
                )
                for row in rows
            )
            return ImportHistoryPage(
                total,
                request.page,
                request.page_size,
                (total + request.page_size - 1) // request.page_size,
                items,
            )
        except Exception:
            raise Phase10ReadError() from None

    def find_duplicate_imports(self, file_hash):
        if type(file_hash) is not str or re.fullmatch(r"[0-9a-f]{64}", file_hash) is None:
            raise InvalidPhase10ReadRequest()
        try:
            with read_transaction(self._connection):
                rows = self._repository.same_hash(file_hash, 20)
            return tuple(DuplicateImportSummary(_file_name(row[0]), *row[1:]) for row in rows)
        except Exception:
            raise Phase10ReadError() from None

    def list_qc_issues(self, request=None):
        request = QCIssueRequest() if request is None else request
        if not (
            type(request) is QCIssueRequest
            and _page(request.page, request.page_size)
            and (
                request.severity is None
                or (type(request.severity) is str and request.severity in SEVERITIES)
            )
            and (
                request.review_status is None
                or (type(request.review_status) is str and request.review_status in REVIEW_STATUSES)
            )
            and (
                request.stream_code is None
                or (
                    type(request.stream_code) is str
                    and len(request.stream_code) == 11
                    and request.stream_code.isascii()
                    and request.stream_code.isdigit()
                )
            )
        ):
            raise InvalidPhase10ReadRequest()
        try:
            with read_transaction(self._connection):
                approved = (
                    ResearchDictionaryBootstrapService(self._connection)
                    .approved_display_policy()
                    .allowed_dictionary_ids
                )
                total = self._repository.count_qc(request)
                rows = self._repository.page_qc(request)
            items = tuple(self._issue(row, approved) for row in rows)
            return QCIssuePage(
                total,
                request.page,
                request.page_size,
                (total + request.page_size - 1) // request.page_size,
                items,
            )
        except Exception:
            raise Phase10ReadError() from None

    def get_qc_issue(self, issue_id):
        if type(issue_id) is not int or not 0 < issue_id < 2**63:
            raise InvalidPhase10ReadRequest()
        try:
            with read_transaction(self._connection):
                approved = (
                    ResearchDictionaryBootstrapService(self._connection)
                    .approved_display_policy()
                    .allowed_dictionary_ids
                )
                row = self._repository.qc_detail(issue_id)
            return None if row is None else self._issue(row, approved)
        except Exception:
            raise Phase10ReadError() from None
