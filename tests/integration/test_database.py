"""임시 SQLite에서 설계 제약을 검증한다. 모든 값은 synthetic이다."""

import sqlite3
from contextlib import closing
from itertools import combinations

import pytest

from small_stream_research_tool.database import (
    connect_database,
    get_schema_version,
    initialize_database,
)

STAMP = "2026-01-01T00:00:00Z"
CODE = "01002003004"
TABLES = {
    "schema_version",
    "app_user",
    "data_category",
    "dictionary_version",
    "unit_dictionary",
    "unit_conversion",
    "data_dictionary",
    "column_alias",
    "source_file",
    "import_history",
    "import_sheet",
    "import_column_mapping",
    "small_stream",
    "stream_relation",
    "characteristic_value",
    "stream_characteristic",
    "quality_rule",
    "data_quality_issue",
    "record_history",
}


def insert(connection, table, **values):
    """식별자는 테스트 내부 상수만 사용하고 값은 SQL 매개변수로 전달한다."""
    columns = ", ".join(values)
    markers = ", ".join("?" for _ in values)
    return connection.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({markers})", tuple(values.values())
    ).lastrowid


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "임시 DB" / "synthetic.sqlite3"
    assert initialize_database(path) == 1
    with closing(connect_database(path)) as connection:
        yield connection


@pytest.fixture
def seeded(db):
    timestamps = {"created_at": STAMP, "updated_at": STAMP}
    insert(
        db,
        "app_user",
        login_id="test.user",
        password_hash="synthetic-hash-placeholder",
        display_name="가상 연구자",
        **timestamps,
    )
    insert(db, "data_category", category_key="synthetic", category_name="가상 분류", **timestamps)
    insert(db, "dictionary_version", version="test-v1", is_current=1, created_at=STAMP)
    insert(db, "unit_dictionary", unit_name="synthetic", unit_symbol="test-unit", **timestamps)
    insert(db, "unit_conversion", from_unit_id=1, to_unit_id=1, factor=1.0, **timestamps)
    insert(
        db,
        "data_dictionary",
        standard_name="가상 항목",
        internal_name="test_value",
        category_id=1,
        data_type="REAL",
        unit_id=1,
        created_version_id=1,
        deprecated_version_id=1,
        **timestamps,
    )
    insert(
        db,
        "column_alias",
        dictionary_id=1,
        alias_name="가상 별칭",
        normalized_alias="test_alias",
        **timestamps,
    )
    insert(
        db,
        "source_file",
        file_name="synthetic.xlsx",
        original_path="synthetic.xlsx",
        file_hash="synthetic-hash",
        registered_at=STAMP,
    )
    insert(
        db,
        "import_history",
        source_file_id=1,
        created_by_user_id=1,
        batch_code="synthetic-1",
        import_type="synthetic",
        status="SUCCESS",
        started_at=STAMP,
        created_at=STAMP,
        dictionary_version_id=1,
        schema_version_id=1,
    )
    insert(
        db, "import_sheet", import_id=1, sheet_name="synthetic", status="SUCCESS", created_at=STAMP
    )
    insert(
        db,
        "import_column_mapping",
        import_sheet_id=1,
        source_column_index=1,
        dictionary_id=1,
        target_unit_id=1,
        mapping_status="MAPPED",
        mapping_method="USER",
        created_at=STAMP,
    )
    insert(
        db,
        "small_stream",
        stream_code=CODE,
        province_code="01",
        city_county_code="002",
        town_code="003",
        stream_serial_no="004",
        stream_name="가상 하천",
        **timestamps,
    )
    insert(
        db,
        "stream_relation",
        stream_code=CODE,
        related_stream_code=CODE,
        relation_type="synthetic",
        source_import_id=1,
        **timestamps,
    )
    insert(
        db,
        "characteristic_value",
        stream_code=CODE,
        dictionary_id=1,
        value_number=0,
        unit_id=1,
        import_id=1,
        import_sheet_id=1,
        mapping_id=1,
        source_row=2,
        **timestamps,
    )
    insert(
        db,
        "stream_characteristic",
        stream_code=CODE,
        dictionary_id=1,
        characteristic_value_id=1,
        updated_at=STAMP,
    )
    insert(
        db,
        "quality_rule",
        rule_code="TEST",
        rule_name="synthetic",
        target_type="synthetic",
        dictionary_id=1,
        rule_type="synthetic",
        default_severity="INFO",
        **timestamps,
    )
    insert(
        db,
        "data_quality_issue",
        characteristic_value_id=1,
        rule_id=1,
        import_id=1,
        import_sheet_id=1,
        stream_code=CODE,
        dictionary_id=1,
        reviewed_by_user_id=1,
        issue_type="synthetic",
        severity="INFO",
        message="synthetic",
        created_at=STAMP,
    )
    insert(
        db,
        "record_history",
        issue_id=1,
        import_id=1,
        table_name="characteristic_value",
        record_key="1",
        change_type="synthetic",
        actor_user_id=1,
        changed_at=STAMP,
    )
    return db


def test_schema_and_all_foreign_keys(seeded):
    actual = {r[0] for r in seeded.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
    assert actual == TABLES
    assert get_schema_version(seeded) == 1
    assert seeded.execute("PRAGMA foreign_keys").fetchone() == (1,)
    assert seeded.execute("PRAGMA foreign_key_check").fetchall() == []
    assert seeded.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    count = 0
    for table in sorted(TABLES):
        for _, _, parent, child_col, parent_col, on_update, on_delete, _ in seeded.execute(
            f"PRAGMA foreign_key_list({table})"
        ).fetchall():
            count += 1
            assert parent in TABLES
            parent_info = {r[1]: r for r in seeded.execute(f"PRAGMA table_info({parent})")}
            assert parent_info[parent_col][5] > 0
            assert (on_delete, on_update) == ("RESTRICT", "NO ACTION")
            bad = "99999999999" if parent_col == "stream_code" else 99999
            with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
                seeded.execute(f"UPDATE {table} SET {child_col} = ?", (bad,))
    assert count == 39
    assert seeded.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize(
    "table,key",
    [
        ("app_user", "user_id"),
        ("small_stream", "stream_code"),
        ("characteristic_value", "characteristic_value_id"),
        ("data_dictionary", "dictionary_id"),
        ("source_file", "source_file_id"),
    ],
)
def test_referenced_parent_delete_and_key_update_rejected(seeded, table, key):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        seeded.execute(f"DELETE FROM {table}")
    replacement = "99999999999" if key == "stream_code" else 99999
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        seeded.execute(f"UPDATE {table} SET {key} = ?", (replacement,))
    seeded.execute(f"UPDATE {table} SET is_active = 0")
    assert seeded.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize(
    "code",
    [
        None,
        "",
        "0123456789",
        "012345678901",
        "0123456789x",
        "０１２３４５６７８９０",
        "01002003004\0",
        b"01002003004",
    ],
)
def test_bad_stream_code_rejected(db, code):
    with pytest.raises(sqlite3.IntegrityError):
        insert(
            db,
            "small_stream",
            stream_code=code,
            province_code="01",
            city_county_code="002",
            town_code="003",
            stream_serial_no="004",
            stream_name="synthetic",
            created_at=STAMP,
            updated_at=STAMP,
        )


@pytest.mark.parametrize(
    "column,valid",
    [
        ("province_code", "01"),
        ("city_county_code", "002"),
        ("town_code", "003"),
        ("stream_serial_no", "004"),
    ],
)
def test_component_lengths(seeded, column, valid):
    for invalid in (None, "", valid[:-1], valid + "0"):
        with pytest.raises(sqlite3.IntegrityError):
            seeded.execute(f"UPDATE small_stream SET {column} = ?", (invalid,))
    # 구성 연결 검사는 Service 책임이며 DB는 값을 자동 수정하지 않는다.
    seeded.execute(f"UPDATE small_stream SET {column} = ?", ("9" * len(valid),))
    assert seeded.execute(
        "SELECT stream_code, typeof(stream_code) FROM small_stream"
    ).fetchone() == (CODE, "text")


@pytest.mark.parametrize(
    "login_id",
    [
        None,
        "abc",
        "a" * 51,
        "Uppercase",
        "test user",
        "테스트계정",
        "test@id",
        "test/id",
        "test\nid",
        "test\0",
        b"test",
    ],
)
def test_bad_login_id_rejected(db, login_id):
    with pytest.raises(sqlite3.IntegrityError):
        insert(
            db,
            "app_user",
            login_id=login_id,
            password_hash="synthetic-hash-placeholder",
            display_name="가상 연구자",
            created_at=STAMP,
            updated_at=STAMP,
        )


@pytest.mark.parametrize("login_id", ["a._-", "a" * 50, "test01"])
def test_login_id_boundaries_and_unique(db, login_id):
    values = dict(
        login_id=login_id,
        password_hash="synthetic-hash-placeholder",
        display_name="가상 연구자",
        created_at=STAMP,
        updated_at=STAMP,
    )
    insert(db, "app_user", **values)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        insert(db, "app_user", **values)
    assert db.execute("SELECT role, department, last_login_at FROM app_user").fetchone() == (
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    "column,limit",
    [
        ("source_latitude", 90),
        ("end_latitude", 90),
        ("source_longitude", 180),
        ("end_longitude", 180),
    ],
)
def test_coordinate_ranges_and_null(seeded, column, limit):
    for value in (-limit - 0.1, limit + 0.1, "not a coordinate"):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            seeded.execute(f"UPDATE small_stream SET {column} = ?", (value,))
    for value in (None, -limit, 0, limit):
        seeded.execute(f"UPDATE small_stream SET {column} = ?", (value,))


VALUE_COLUMNS = ("value_number", "value_integer", "value_text", "value_date")


@pytest.mark.parametrize(
    "selected", [()] + [c for n in (2, 3, 4) for c in combinations(VALUE_COLUMNS, n)]
)
def test_zero_or_multiple_typed_values_rejected(seeded, selected):
    values = {c: (1 if c in selected else None) for c in VALUE_COLUMNS}
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        seeded.execute(
            "UPDATE characteristic_value SET value_number=?, value_integer=?, "
            "value_text=?, value_date=?",
            tuple(values.values()),
        )


@pytest.mark.parametrize(
    "column,value",
    [
        ("value_number", 0.0),
        ("value_integer", 0),
        ("value_text", "synthetic"),
        ("value_date", "2026-01-01"),
    ],
)
def test_exactly_one_typed_value_allowed(seeded, column, value):
    values = {c: value if c == column else None for c in VALUE_COLUMNS}
    seeded.execute(
        "UPDATE characteristic_value SET value_number=?, value_integer=?, "
        "value_text=?, value_date=?",
        tuple(values.values()),
    )


def test_representative_partial_unique_and_inactive_history(seeded):
    seeded.execute("UPDATE characteristic_value SET is_representative = 1")
    values = dict(
        stream_code=CODE, dictionary_id=1, value_number=2, created_at=STAMP, updated_at=STAMP
    )
    insert(seeded, "characteristic_value", **values)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        insert(seeded, "characteristic_value", is_representative=1, **values)
    inactive = insert(seeded, "characteristic_value", is_representative=1, is_active=0, **values)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        seeded.execute(
            "UPDATE characteristic_value SET is_active=1 WHERE characteristic_value_id=?",
            (inactive,),
        )
    assert seeded.execute("SELECT COUNT(*) FROM characteristic_value").fetchone() == (3,)


def test_cache_columns_and_composite_key(seeded):
    assert [r[1] for r in seeded.execute("PRAGMA table_info(stream_characteristic)")] == [
        "stream_code",
        "dictionary_id",
        "characteristic_value_id",
        "updated_at",
    ]
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        insert(
            seeded,
            "stream_characteristic",
            stream_code=CODE,
            dictionary_id=1,
            characteristic_value_id=1,
            updated_at=STAMP,
        )
    for col in ("stream_code", "dictionary_id"):
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            seeded.execute(f"UPDATE stream_characteristic SET {col}=NULL")


def test_all_boolean_constraints_and_defaults(seeded):
    count = 0
    for table in sorted(TABLES):
        for _, col, _, notnull, default, _ in seeded.execute(
            f"PRAGMA table_info({table})"
        ).fetchall():
            if col not in {
                "is_active",
                "is_current",
                "is_representative",
                "is_enabled",
                "analyzable",
                "required",
                "nullable",
                "user_confirmed",
            }:
                continue
            count += 1
            assert notnull == 1 and default in ("0", "1")
            for invalid in (-1, 2, None):
                with pytest.raises(sqlite3.IntegrityError):
                    seeded.execute(f"UPDATE {table} SET {col}=?", (invalid,))
    assert count == 18


@pytest.mark.parametrize(
    "table,column,allowed",
    [
        ("import_history", "status", "PENDING RUNNING SUCCESS FAILED ROLLED_BACK CANCELLED"),
        ("import_sheet", "status", "RUNNING SUCCESS FAILED"),
        ("quality_rule", "default_severity", "ERROR WARNING INFO"),
        ("data_quality_issue", "severity", "ERROR WARNING INFO"),
        (
            "data_quality_issue",
            "review_status",
            "UNREVIEWED IN_REVIEW CONFIRMED CORRECTED DEFERRED",
        ),
        ("data_dictionary", "data_type", "REAL INTEGER TEXT DATE DATETIME"),
        ("data_dictionary", "storage_type", "CORE FLEX"),
    ],
)
def test_closed_enums(seeded, table, column, allowed):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        seeded.execute(f"UPDATE {table} SET {column}='NOT_DEFINED'")
    for value in allowed.split():
        seeded.execute(f"UPDATE {table} SET {column}=?", (value,))


def test_issue_nullable_value_and_independent_review(seeded):
    issue_id = insert(
        seeded,
        "data_quality_issue",
        issue_type="synthetic",
        severity="ERROR",
        message="synthetic",
        created_at=STAMP,
    )
    assert seeded.execute(
        "SELECT characteristic_value_id, is_active, review_status "
        "FROM data_quality_issue WHERE issue_id=?",
        (issue_id,),
    ).fetchone() == (None, 1, "UNREVIEWED")
    seeded.execute(
        "UPDATE data_quality_issue SET review_status='CORRECTED' WHERE issue_id=?", (issue_id,)
    )
    assert seeded.execute(
        "SELECT is_active FROM data_quality_issue WHERE issue_id=?", (issue_id,)
    ).fetchone() == (1,)


def test_dictionary_current_unique(seeded):
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        insert(seeded, "dictionary_version", version="test-v2", is_current=1, created_at=STAMP)
    insert(seeded, "dictionary_version", version="test-v2", created_at=STAMP)


@pytest.mark.parametrize(
    "table,columns",
    [
        ("unit_conversion", "from_unit_id,to_unit_id,factor,created_at,updated_at"),
        (
            "column_alias",
            "dictionary_id,alias_name,normalized_alias,source_scope,created_at,updated_at",
        ),
        ("import_sheet", "import_id,sheet_name,status,created_at"),
        (
            "import_column_mapping",
            "import_sheet_id,source_column_index,mapping_status,mapping_method,created_at",
        ),
    ],
)
def test_composite_uniques(seeded, table, columns):
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        seeded.execute(f"INSERT INTO {table} ({columns}) SELECT {columns} FROM {table}")


def test_unmapped_metadata_and_nonunique_file_hash(seeded):
    insert(
        seeded,
        "import_column_mapping",
        import_sheet_id=1,
        source_column_index=2,
        mapping_status="UNMAPPED",
        mapping_method="NONE",
        created_at=STAMP,
    )
    insert(
        seeded,
        "source_file",
        file_name="copy.xlsx",
        original_path="copy.xlsx",
        file_hash="synthetic-hash",
        registered_at=STAMP,
    )
    assert seeded.execute(
        "SELECT dictionary_id FROM import_column_mapping WHERE mapping_id=2"
    ).fetchone() == (None,)


def test_child_fk_indexes_cover_reference_checks(seeded):
    for table in sorted(TABLES):
        prefixes = set()
        for row in seeded.execute(f"PRAGMA index_list({table})").fetchall():
            if row[4] == 0:  # 부분 인덱스만으로 전체 FK 참조 검사를 커버하지 않는다.
                prefixes.add(seeded.execute(f"PRAGMA index_info('{row[1]}')").fetchone()[2])
        for fk in seeded.execute(f"PRAGMA foreign_key_list({table})"):
            assert fk[3] in prefixes
    plan = seeded.execute(
        "EXPLAIN QUERY PLAN SELECT 1 FROM data_quality_issue "
        "WHERE characteristic_value_id=? AND is_active=1 AND severity='ERROR'",
        (1,),
    ).fetchall()
    assert any("ix_data_quality_issue_characteristic_value_id" in row[3] for row in plan)
