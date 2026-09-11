"""DDL/DML/version 원자성과 재실행을 실제 임시 파일로 검증한다."""

import sqlite3
from contextlib import closing
from datetime import datetime
from importlib.resources import files

import pytest

from small_stream_research_tool.database import (
    apply_migrations,
    connect_database,
    get_schema_version,
    initialize_database,
    transaction,
)


@pytest.fixture
def migrations_dir(tmp_path):
    directory = tmp_path / "migrations"
    directory.mkdir()
    sql = (
        files("small_stream_research_tool.database")
        .joinpath("migrations", "001_initial.sql")
        .read_text(encoding="utf-8")
    )
    (directory / "001_initial.sql").write_text(sql, encoding="utf-8")
    return directory


def snapshot(connection):
    return list(connection.iterdump())


def test_new_database_and_repeated_initialization(tmp_path):
    path = tmp_path / "한글 경로" / "test.sqlite3"
    with closing(connect_database(path)) as connection:
        assert get_schema_version(connection) == 0
        assert apply_migrations(connection) == 1
        row = connection.execute(
            "SELECT version, migration_name, app_version, applied_at FROM schema_version"
        ).fetchone()
        assert row[:3] == ("001", "001_initial.sql", "0.1.0")
        assert row[3].endswith("Z")
        assert datetime.fromisoformat(row[3]).utcoffset().total_seconds() == 0
        before = snapshot(connection)
        changes = connection.total_changes
        assert apply_migrations(connection) == 1
        assert connection.total_changes == changes
        assert snapshot(connection) == before
    assert initialize_database(path) == 1
    with closing(connect_database(path)) as connection:
        assert snapshot(connection) == before
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)


def test_default_path_uses_phase_zero_config(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert initialize_database() == 1
    path = tmp_path / "NDMI" / "small-stream-research-tool" / "db" / "research.sqlite3"
    assert path.is_file()
    assert not (path.parent.parent / "workspace").exists()


def test_sequential_migrations_and_repeated_run(tmp_path, migrations_dir):
    (migrations_dir / "003_third.sql").write_text(
        "INSERT INTO migration_probe VALUES ('third');", encoding="utf-8"
    )
    (migrations_dir / "002_second.sql").write_text(
        "-- Semicolons in strings must survive.\n"
        "CREATE TABLE migration_probe (value TEXT); INSERT INTO migration_probe VALUES ('a;b');\n"
        "/* trailing comment ; */",
        encoding="utf-8",
    )
    with closing(connect_database(tmp_path / "test.sqlite3")) as connection:
        assert apply_migrations(connection, migration_dir=migrations_dir) == 3
        assert connection.execute(
            "SELECT value FROM migration_probe ORDER BY rowid"
        ).fetchall() == [("a;b",), ("third",)]
        before = snapshot(connection)
        assert apply_migrations(connection, migration_dir=migrations_dir) == 3
        assert snapshot(connection) == before


@pytest.mark.parametrize(
    "failure",
    [
        "INSERT INTO missing_table VALUES (1);",
        "COMMIT;",
        "PRAGMA foreign_keys=OFF;",
    ],
)
def test_initial_migration_failure_leaves_no_partial_schema(tmp_path, migrations_dir, failure):
    initial = migrations_dir / "001_initial.sql"
    with initial.open("a", encoding="utf-8") as file:
        file.write("\n" + failure)
    with closing(connect_database(tmp_path / "test.sqlite3")) as connection:
        with pytest.raises(sqlite3.DatabaseError):
            apply_migrations(connection, migration_dir=migrations_dir)
        assert connection.execute("SELECT name FROM sqlite_schema").fetchall() == []
        assert get_schema_version(connection) == 0
        assert not connection.in_transaction
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)


def test_later_migration_failure_preserves_prior_schema_and_data(tmp_path, migrations_dir):
    path = tmp_path / "test.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as connection:
        before = snapshot(connection)
        second = migrations_dir / "002_probe.sql"
        second.write_text(
            "CREATE TABLE migration_probe (id INTEGER PRIMARY KEY);"
            "INSERT INTO migration_probe VALUES (1);"
            "UPDATE schema_version SET description='must roll back';"
            "INSERT INTO migration_probe VALUES (1);",
            encoding="utf-8",
        )
        with pytest.raises(sqlite3.IntegrityError):
            apply_migrations(connection, migration_dir=migrations_dir)
        assert snapshot(connection) == before
        assert get_schema_version(connection) == 1
        second.write_text(
            "CREATE TABLE migration_probe (id INTEGER PRIMARY KEY);", encoding="utf-8"
        )
        assert apply_migrations(connection, migration_dir=migrations_dir) == 2


def test_version_record_failure_rolls_back_ddl(tmp_path, migrations_dir):
    initial = migrations_dir / "001_initial.sql"
    with initial.open("a", encoding="utf-8") as file:
        file.write("\nINSERT INTO schema_version(version, applied_at) VALUES ('001','synthetic');")
    with closing(connect_database(tmp_path / "test.sqlite3")) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            apply_migrations(connection, migration_dir=migrations_dir)
        assert get_schema_version(connection) == 0
        assert connection.execute("SELECT name FROM sqlite_schema").fetchall() == []


@pytest.mark.parametrize(
    "filename",
    ["003_gap.sql", "001_duplicate.sql", "bad.sql", "000_zero.sql", "0002_noncanonical.sql"],
)
def test_bad_migration_numbers_rejected_before_changes(tmp_path, migrations_dir, filename):
    (migrations_dir / filename).write_text("SELECT 1;", encoding="utf-8")
    with closing(connect_database(tmp_path / "test.sqlite3")) as connection:
        with pytest.raises(ValueError):
            apply_migrations(connection, migration_dir=migrations_dir)
        assert get_schema_version(connection) == 0


def test_empty_migration_directory_rejected(tmp_path):
    directory = tmp_path / "empty"
    directory.mkdir()
    with closing(connect_database(tmp_path / "test.sqlite3")) as connection:
        with pytest.raises(ValueError, match="consecutive"):
            apply_migrations(connection, migration_dir=directory)


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE schema_version SET version='003'",
        "UPDATE schema_version SET version='invalid'",
        "UPDATE schema_version SET migration_name='001_other.sql'",
        "DELETE FROM schema_version",
        "INSERT INTO schema_version(version,migration_name,applied_at) "
        "VALUES ('002','002_future.sql','x')",
    ],
)
def test_incompatible_history_rejected_without_changes(tmp_path, change):
    path = tmp_path / "test.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as connection:
        connection.execute(change)
        before = snapshot(connection)
        with pytest.raises(ValueError):
            apply_migrations(connection)
        assert snapshot(connection) == before


def test_unversioned_existing_database_is_not_adopted(tmp_path):
    with closing(connect_database(tmp_path / "test.sqlite3")) as connection:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
        before = snapshot(connection)
        with pytest.raises(ValueError, match="adoption refused"):
            apply_migrations(connection)
        assert snapshot(connection) == before


def test_foreign_keys_off_and_active_transaction_rejected(tmp_path):
    with closing(connect_database(tmp_path / "test.sqlite3")) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        with pytest.raises(ValueError, match="foreign_keys"):
            apply_migrations(connection)
        connection.execute("PRAGMA foreign_keys=ON")
        with transaction(connection):
            connection.execute("CREATE TABLE pending (value TEXT)")
            with pytest.raises(ValueError, match="idle"):
                apply_migrations(connection)
            with pytest.raises(ValueError, match="active transaction"):
                with transaction(connection):
                    pass
            assert connection.in_transaction
        assert connection.execute("SELECT * FROM pending").fetchall() == []


def test_transaction_rolls_back_ddl_and_dml(tmp_path):
    with closing(connect_database(tmp_path / "test.sqlite3")) as connection:
        with pytest.raises(RuntimeError, match="synthetic"):
            with transaction(connection):
                connection.execute("CREATE TABLE pending (value TEXT)")
                connection.execute("INSERT INTO pending VALUES ('synthetic')")
                raise RuntimeError("synthetic")
        assert connection.execute("SELECT name FROM sqlite_schema").fetchall() == []
        assert not connection.in_transaction
