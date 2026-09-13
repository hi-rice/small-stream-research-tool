"""SQLite 연결과 명시적 transaction. 연결 종료는 호출자 책임이다."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from small_stream_research_tool.config.settings import get_app_paths


def connect_database(db_path: str | Path | None = None) -> sqlite3.Connection:
    """연결마다 FK를 활성화한다. 기본 경로도 명시적 호출 때만 생성한다.

    isolation_level=None: 자동 BEGIN 없이 SQL BEGIN/COMMIT으로 경계를 관리한다.
    업무 쓰기는 transaction() 안에서 수행해야 한다.
    """
    path = (
        Path(db_path) if db_path is not None else get_app_paths().database_dir / "research.sqlite3"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise RuntimeError("SQLite foreign key enforcement is unavailable")
    except BaseException:
        connection.close()
        raise
    return connection


@contextmanager
def read_transaction(connection: sqlite3.Connection) -> Iterator[None]:
    """유휴 연결에서 여러 SELECT가 하나의 snapshot을 보도록 한다. 종료는 rollback이다."""
    if connection.in_transaction:
        raise ValueError("An active transaction already exists")
    connection.execute("BEGIN")
    try:
        yield
    finally:
        if connection.in_transaction:
            connection.execute("ROLLBACK")


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[None]:
    """중첩 transaction을 거부하고 예외 시 DDL·DML을 함께 rollback한다."""
    if connection.in_transaction:
        raise ValueError("An active transaction already exists")
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
