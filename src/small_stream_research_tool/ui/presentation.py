"""조회 UI에서 사용하는 안전한 표시 문자열만 변환한다."""

from datetime import datetime

from small_stream_research_tool.models.stream_read import StreamListRow

HEADERS = ("소하천 관리코드", "소하천명", "시·도", "시·군·구", "읍·면·동", "데이터 상태")
SORT_FIELDS = ("stream_code", "stream_name", "province", "city_county", "town", None)
STATUS_TEXT = {
    "ERROR": "오류",
    "NEEDS_REVIEW": "확인 필요",
    "ACTIVE_ISSUES_NONE": "활성 문제 없음",
}
CURRENT_TEXT = {
    "VALID_CURRENT": "현재 사용값 있음",
    "UNASSIGNED": "현재 사용값 미지정",
    "INCONSISTENT": "현재값 연결 확인 필요",
}
REVIEW_TEXT = {
    "UNREVIEWED": "미검토",
    "IN_REVIEW": "검토 중",
    "CONFIRMED": "검토 완료",
    "CORRECTED": "보정됨",
    "DEFERRED": "검토 보류",
}
SOURCE_TEXT = {
    "IMPORT": "Import 자료",
    "RESEARCHER_CORRECTION": "연구자 보정값",
    "OTHER_SOURCE": "기타 등록 자료",
}
SEVERITY_TEXT = {"ERROR": "오류", "WARNING": "경고", "INFO": "정보"}
DICTIONARY_STATE_TEXT = {
    "READY": "연구 사전 준비됨",
    "NOT_INITIALIZED": "연구 사전 미초기화",
    "INCONSISTENT": "연구 사전 확인 필요",
}
HISTORY_EVENT_TEXT = {
    "CORRECTION": "특성정보 보정",
    "CURRENT_VALUE_CHANGE": "현재 사용값 변경",
    "DEACTIVATE": "특성값 비활성화",
    "RESTORE": "특성값 복원",
    "CACHE_REBUILD": "현재값 캐시 재구축",
    "QC_REVIEW": "QC 검토",
}
HISTORY_REASON_TEXT = {
    "RESEARCHER_SELECTION": "연구자 선택",
    "SOURCE_REVIEW": "출처 검토",
    "QC_REVIEW_CONFIRMED": "QC 검토 확인",
}


def display_row(row: StreamListRow) -> tuple[str, ...]:
    return (
        row.stream_code,
        row.stream_name,
        row.province or "—",
        row.city_county or "—",
        row.town or "—",
        STATUS_TEXT.get(row.qc_display_state, "상태 확인 필요"),
    )


def display_value(value) -> str:
    return "현재 사용값 미지정" if value is None else str(value)


def display_timestamp(value: str | None) -> str:
    """저장된 UTC 의미를 보존하며 ISO 값을 사람이 읽기 쉽게 표시한다."""
    if not value:
        return "미등록"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return "시각 확인 필요"
    if parsed.utcoffset() is None:
        return parsed.strftime("%Y-%m-%d %H:%M")
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def display_history_target(item) -> str:
    """공개 projection만으로 작업 대상을 구성한다."""
    if item.target_state != "RESOLVED":
        return "대상 정보 확인 필요"
    stream = item.stream_name or item.stream_code or "소하천 정보 확인 필요"
    characteristic = item.dictionary_standard_name or "특성항목 정보 확인 필요"
    return f"{stream} · {characteristic}"
