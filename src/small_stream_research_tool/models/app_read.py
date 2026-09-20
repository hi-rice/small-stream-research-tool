"""Phase 9D 홈·작업이력·마이페이지의 제한된 읽기 모델."""

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkHistoryRequest:
    page: int = 1
    page_size: int = 50
    change_type: str | None = None
    actor_user_id: int | None = None
    stream_code: str | None = None


@dataclass(frozen=True)
class WorkHistoryActorOption:
    user_id: int
    display_name: str


@dataclass(frozen=True)
class WorkHistoryItem:
    change_type: str
    actor_display_name: str | None
    actor_state: str
    stream_code: str | None
    stream_name: str | None
    dictionary_standard_name: str | None
    target_state: str
    reason_code: str | None
    reason_state: str
    changed_at: str


@dataclass(frozen=True)
class WorkHistoryPage:
    total_count: int
    page: int
    page_size: int
    total_pages: int
    items: tuple[WorkHistoryItem, ...]


@dataclass(frozen=True)
class HomeSummary:
    active_stream_count: int
    error_stream_count: int
    needs_review_stream_count: int
    dictionary_state: str
    recent_history: tuple[WorkHistoryItem, ...]


@dataclass(frozen=True)
class UserPublicProfile:
    login_id: str
    display_name: str
    department: str | None
    role: str | None
    is_active: bool
    created_at: str
    last_login_at: str | None
