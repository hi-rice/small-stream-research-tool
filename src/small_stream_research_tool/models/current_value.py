"""현재 사용값 선택 결과. 연구값과 사용자 입력 원문을 반환하지 않는다."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CurrentValueSelectionResult:
    changed: bool
    stream_code: str = field(repr=False)
    dictionary_id: int
    previous_value_id: int | None
    current_value_id: int
    qc_status_before_selection: str
    confirmation_required: bool
    confirmation_used: bool
    history_id: int | None
    completed_at: str
