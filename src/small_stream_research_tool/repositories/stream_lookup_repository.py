"""기존 소하천 PK 존재 여부만 SELECT한다. 연결 생성·commit·쓰기는 하지 않는다."""

import sqlite3

from small_stream_research_tool.models.import_preview_errors import (
    InvalidPreviewArgumentError,
    StreamLookupError,
)


class StreamLookupRepository:
    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection

    def exists_by_stream_code(self, stream_code: str) -> bool:
        if not (
            isinstance(stream_code, str)
            and len(stream_code) == 11
            and all("0" <= char <= "9" for char in stream_code)
        ):
            raise InvalidPreviewArgumentError("검증된 11자리 ASCII 문자열 관리코드가 필요합니다.")
        try:
            return (
                self._connection.execute(
                    "SELECT 1 FROM small_stream WHERE stream_code = ?", (stream_code,)
                ).fetchone()
                is not None
            )
        except sqlite3.Error:
            raise StreamLookupError("기존 소하천 정보를 조회할 수 없습니다.") from None
