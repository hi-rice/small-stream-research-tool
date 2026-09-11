"""순차 SQL migration. 스크립트에는 transaction/PRAGMA 명령을 넣지 않는다."""

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path

from small_stream_research_tool.config.settings import APP_ID
from small_stream_research_tool.database.connection import transaction


@dataclass(frozen=True)
class Migration:
    number: int
    name: str
    sql: str


def _load_migrations(directory: Path | None) -> tuple[Migration, ...]:
    root = directory if directory is not None else files(__package__).joinpath("migrations")
    migrations = []
    for path in root.iterdir():
        if not path.is_file() or not path.name.endswith(".sql"):
            continue
        match = re.fullmatch(r"([0-9]{3,})_([a-z][a-z0-9_]*)\.sql", path.name)
        if match is None:
            raise ValueError("Invalid migration filename")
        number = int(match[1])
        if match[1] != f"{number:03d}":
            raise ValueError("Noncanonical migration number")
        migrations.append(Migration(number, path.name, path.read_text(encoding="utf-8")))
    migrations.sort(key=lambda migration: migration.number)
    if not migrations or [m.number for m in migrations] != list(range(1, len(migrations) + 1)):
        raise ValueError("Migration numbers must be unique and consecutive from 001")
    return tuple(migrations)


def _history(connection: sqlite3.Connection) -> list[tuple[str, str | None]]:
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    if "schema_version" not in tables:
        if tables:
            raise ValueError("Existing database has no schema_version; automatic adoption refused")
        return []
    rows = list(connection.execute("SELECT version, migration_name FROM schema_version"))
    if not rows:
        raise ValueError("Existing schema_version has no applied migration records")
    if any(not re.fullmatch(r"[0-9]{3,}", row[0]) for row in rows):
        raise ValueError("Invalid recorded schema version")
    rows.sort(key=lambda row: int(row[0]))
    if [row[0] for row in rows] != [f"{n:03d}" for n in range(1, len(rows) + 1)]:
        raise ValueError("Recorded schema versions are not consecutive")
    return rows


def get_schema_version(connection: sqlite3.Connection) -> int:
    """schema_version 기록을 검증하고 최신 번호를 반환한다. 빈 DB는 0이다."""
    return len(_history(connection))


def _execute_sql(connection: sqlite3.Connection, sql: str) -> None:
    # executescript()의 암묵적 COMMIT을 피한다. complete_statement는 문자열과
    # 주석 안의 세미콜론, 여러 문장, trigger 본문을 SQLite 문법으로 구분한다.
    blocked = {
        sqlite3.SQLITE_TRANSACTION,
        sqlite3.SQLITE_SAVEPOINT,
        sqlite3.SQLITE_ATTACH,
        sqlite3.SQLITE_DETACH,
        sqlite3.SQLITE_PRAGMA,
    }

    def authorize(action, _arg1, _arg2, _database, _source):
        return sqlite3.SQLITE_DENY if action in blocked else sqlite3.SQLITE_OK

    connection.set_authorizer(authorize)
    try:
        buffer = ""
        for char in sql:
            buffer += char
            if char == ";" and sqlite3.complete_statement(buffer):
                connection.execute(buffer)
                buffer = ""
        if buffer.strip():
            connection.execute(buffer)
    finally:
        connection.set_authorizer(None)


def apply_migrations(connection: sqlite3.Connection, *, migration_dir: Path | None = None) -> int:
    """각 migration을 원자적으로 적용한다. 최신이면 기록·스키마를 변경하지 않는다.

    전용 유휴 연결을 전달한다. 이미 적용된 파일은 변경하지 않고 다음 번호를 추가한다.
    migration_dir는 테스트/개발용 SQL 디렉터리 재정의다.
    """
    if connection.in_transaction:
        raise ValueError("Migrations require an idle connection")
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise ValueError("Migrations require foreign_keys = ON")
    migrations = _load_migrations(migration_dir)
    for migration in migrations:
        # 다른 연결의 초기화 완료를 기다린 뒤 잠금 안에서 이력을 다시 확인한다.
        with transaction(connection):
            history = _history(connection)
            if len(history) > len(migrations):
                raise ValueError("Database schema is newer than available migrations")
            if any(name != migrations[i].name for i, (_, name) in enumerate(history)):
                raise ValueError("Recorded migration names do not match available migrations")
            if migration.number <= len(history):
                continue
            _execute_sql(connection, migration.sql)
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ValueError("Migration left foreign key violations")
            connection.execute(
                "INSERT INTO schema_version "
                "(version, description, migration_name, app_version, applied_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    f"{migration.number:03d}",
                    migration.name.split("_", 1)[1].removesuffix(".sql"),
                    migration.name,
                    version(APP_ID),
                    datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                ),
            )
    return get_schema_version(connection)
