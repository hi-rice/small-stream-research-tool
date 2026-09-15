"""Phase 9B 목록 표시 텍스트만 변환한다."""

from small_stream_research_tool.models.stream_read import StreamListRow

HEADERS = ("소하천 관리코드", "소하천명", "시·도", "시·군·구", "읍·면·동", "데이터 상태")
SORT_FIELDS = ("stream_code", "stream_name", "province", "city_county", "town", None)
STATUS_TEXT = {
    "ERROR": "오류",
    "NEEDS_REVIEW": "확인 필요",
    "ACTIVE_ISSUES_NONE": "활성 문제 없음",
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
