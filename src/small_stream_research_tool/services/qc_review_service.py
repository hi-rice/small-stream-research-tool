"""사람의 QC 검토를 자동 QC와 분리해 원자적으로 기록한다."""

from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.models.qc_review import (
    QCReviewError,
    QCReviewPersistenceError,
    QCReviewRequest,
    QCReviewResult,
)
from small_stream_research_tool.repositories.qc_review_repository import QCReviewRepository
from small_stream_research_tool.utils.timestamps import utc_now_text

NOTE_LIMIT = 500
RESULT_LIMIT = 200
TRANSITIONS = {"UNREVIEWED": "IN_REVIEW", "IN_REVIEW": "CONFIRMED"}


def _id(value):
    return type(value) is int and 0 < value < 2**63


def _optional_text(value, limit):
    return value is None or (
        type(value) is str and bool(value.strip()) and len(value) <= limit and "\0" not in value
    )


class QCReviewService:
    def __init__(self, connection):
        self._connection = connection
        self._repository = QCReviewRepository(connection)

    def review(self, request: QCReviewRequest) -> QCReviewResult:
        if not (
            type(request) is QCReviewRequest
            and _id(request.issue_id)
            and _id(request.actor_user_id)
            and type(request.review_status) is str
            and request.review_status in ("IN_REVIEW", "CONFIRMED")
            and _optional_text(request.note, NOTE_LIMIT)
            and _optional_text(request.result, RESULT_LIMIT)
        ):
            raise QCReviewError()
        try:
            with transaction(self._connection):
                if not self._repository.actor_active(request.actor_user_id):
                    raise QCReviewError()
                issue = self._repository.issue(request.issue_id)
                if issue is None or not issue[1]:
                    raise QCReviewError()
                old, _, stream_code, dictionary_id, reviewed_at = issue
                if stream_code is None or not self._repository.target_exists(
                    stream_code, dictionary_id
                ):
                    raise QCReviewError()
                if old == request.review_status:
                    return QCReviewResult(False, old, reviewed_at)
                if TRANSITIONS.get(old) != request.review_status:
                    raise QCReviewError()
                timestamp = utc_now_text()
                if not self._repository.change(request, old, timestamp):
                    raise QCReviewPersistenceError()
                self._repository.audit(
                    request.issue_id,
                    stream_code,
                    dictionary_id,
                    old,
                    request.review_status,
                    request.actor_user_id,
                    timestamp,
                )
                return QCReviewResult(True, request.review_status, timestamp)
        except QCReviewError:
            raise
        except Exception:
            raise QCReviewPersistenceError() from None
