"""명시적으로 호출하는 DB 초기화 API. 앱 시작점에서는 호출하지 않는다."""

from contextlib import closing
from pathlib import Path

from small_stream_research_tool.database.connection import connect_database, transaction
from small_stream_research_tool.database.migrations import apply_migrations, get_schema_version

__all__ = [
    "apply_migrations",
    "connect_database",
    "get_schema_version",
    "initialize_database",
    "transaction",
]


def initialize_database(db_path: str | Path | None = None) -> int:
    """DB를 초기화하고 연결을 닫은 뒤 적용된 버전 번호를 반환한다."""
    with closing(connect_database(db_path)) as connection:
        return apply_migrations(connection)
