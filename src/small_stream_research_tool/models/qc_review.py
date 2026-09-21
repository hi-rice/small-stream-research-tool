"""QC 검토 명령의 내부 식별자와 안전한 결과."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class QCReviewRequest:
    issue_id: int = field(repr=False)
    actor_user_id: int = field(repr=False)
    review_status: str
    note: str | None = field(default=None, repr=False)
    result: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class QCReviewResult:
    changed: bool
    review_status: str
    reviewed_at: str | None


class QCReviewError(Exception):
    def __init__(self):
        super().__init__("QC 검토 요청을 확인해야 합니다.")


class QCReviewPersistenceError(QCReviewError):
    def __init__(self):
        Exception.__init__(self, "QC 검토를 저장하지 못했습니다.")
