"""Phase 9D-1의 bounded read projection을 합성 임시 DB에서 검증한다."""

import json
from contextlib import closing
from types import SimpleNamespace

import pytest

from small_stream_research_tool.database import connect_database, initialize_database
from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.models.app_read import WorkHistoryRequest
from small_stream_research_tool.models.app_read_errors import (
    InactiveUserProfile,
    InvalidAppReadRequest,
    UserProfileNotFound,
)
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.repositories.import_persistence_repository import (
    CharacteristicValueRepository,
    SmallStreamRepository,
)
from small_stream_research_tool.repositories.user_repository import UserRepository
from small_stream_research_tool.services.app_read_service import AppReadService
from small_stream_research_tool.services.research_dictionary_bootstrap import (
    ResearchDictionaryBootstrapService,
)

STAMP = "2026-09-18T00:00:00Z"
STREAM = "01234567001"


@pytest.fixture
def ctx(tmp_path):
    path = tmp_path / "phase9d.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as conn:
        with transaction(conn):
            actor = UserRepository(conn).create_user(
                login_id="synthetic_actor",
                password_hash="synthetic-hash-only",
                display_name="합성 작업자",
                department="연구팀",
                role="연구원",
                timestamp=STAMP,
            )
            other = UserRepository(conn).create_user(
                login_id="other_actor",
                password_hash="other-hash-only",
                display_name="다른 작업자",
                department=None,
                role=None,
                timestamp=STAMP,
            )
            SmallStreamRepository(conn).create(
                stream_code=STREAM,
                province_code="01",
                city_county_code="234",
                town_code="567",
                stream_serial_no="001",
                stream_name="합성 소하천",
                province_name="합성도",
                city_county_name="합성군",
                town_name="합성면",
                created_at=STAMP,
                updated_at=STAMP,
            )
        ResearchDictionaryBootstrapService(conn).bootstrap()
        item = DictionaryRepository(conn).get_item_by_internal_name("basin_area")
        with transaction(conn):
            value = CharacteristicValueRepository(conn).create(
                stream_code=STREAM,
                dictionary_id=item.dictionary_id,
                value_number=12.5,
                original_value="12.5",
                is_active=True,
                is_representative=False,
                created_at=STAMP,
                updated_at=STAMP,
            )
            records = (
                (
                    "CORRECTION",
                    json.dumps({"stream_code": STREAM, "dictionary_id": item.dictionary_id}),
                    None,
                    actor.user_id,
                ),
                (
                    "CURRENT_VALUE_CHANGE",
                    json.dumps({"stream_code": STREAM, "dictionary_id": item.dictionary_id}),
                    "QC_REVIEW_CONFIRMED",
                    actor.user_id,
                ),
                (
                    "DEACTIVATE",
                    json.dumps({"characteristic_value_id": value.characteristic_value_id}),
                    "SOURCE_REVIEW",
                    other.user_id,
                ),
                (
                    "RESTORE",
                    json.dumps({"characteristic_value_id": value.characteristic_value_id}),
                    "RESEARCHER_SELECTION",
                    None,
                ),
                (
                    "CACHE_REBUILD",
                    json.dumps({"stream_code": STREAM, "dictionary_id": item.dictionary_id}),
                    None,
                    actor.user_id,
                ),
                ("CORRECTION", "not-json", "PRIVATE_RAW_REASON", None),
                ("IMPORT", "future-internal", "future raw", None),
            )
            for event, key, reason, user_id in records:
                conn.execute(
                    "INSERT INTO record_history "
                    "(table_name,record_key,change_type,reason,actor_user_id,changed_at) "
                    "VALUES (?,?,?,?,?,?)",
                    ("characteristic_value", key, event, reason, user_id, STAMP),
                )
        yield SimpleNamespace(
            conn=conn,
            service=AppReadService(conn),
            actor=actor.user_id,
            other=other.user_id,
            value=value.characteristic_value_id,
        )


def snapshot(conn):
    tables = tuple(
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        )
    )
    return tuple(
        (table, tuple(conn.execute(f"SELECT * FROM [{table}] ORDER BY 1").fetchall()))
        for table in tables
    )


def test_home_summary_counts_dictionary_and_bounds_history(ctx):
    before = snapshot(ctx.conn)
    summary = ctx.service.get_home_summary()
    assert summary.active_stream_count == 1
    assert summary.error_stream_count == 0
    assert summary.needs_review_stream_count == 0
    assert summary.dictionary_state == "READY"
    assert len(summary.recent_history) == 5
    assert snapshot(ctx.conn) == before


def test_home_qc_aggregate_and_dictionary_states(ctx):
    ctx.conn.execute(
        "INSERT INTO data_quality_issue "
        "(stream_code,issue_type,severity,message,is_active,created_at) "
        "VALUES (?,?,?,?,?,?)",
        (STREAM, "SYNTHETIC_ERROR", "ERROR", "private raw", 1, STAMP),
    )
    summary = ctx.service.get_home_summary()
    assert (summary.error_stream_count, summary.needs_review_stream_count) == (1, 0)
    ctx.conn.execute("UPDATE data_quality_issue SET severity='WARNING'")
    summary = ctx.service.get_home_summary()
    assert (summary.error_stream_count, summary.needs_review_stream_count) == (0, 1)
    ctx.conn.execute(
        "INSERT INTO data_quality_issue "
        "(stream_code,issue_type,severity,message,is_active,created_at) VALUES (?,?,?,?,?,?)",
        (STREAM, "SYNTHETIC_INFO", "INFO", "private raw", 1, STAMP),
    )
    summary = ctx.service.get_home_summary()
    assert (summary.error_stream_count, summary.needs_review_stream_count) == (0, 1)
    ctx.conn.execute(
        "INSERT INTO data_quality_issue "
        "(stream_code,issue_type,severity,message,is_active,created_at) VALUES (?,?,?,?,?,?)",
        (STREAM, "SYNTHETIC_ERROR_2", "ERROR", "private raw", 1, STAMP),
    )
    summary = ctx.service.get_home_summary()
    assert (summary.error_stream_count, summary.needs_review_stream_count) == (1, 0)


def test_dictionary_not_initialized_and_inconsistent(tmp_path):
    path = tmp_path / "empty.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as conn:
        service = AppReadService(conn)
        assert service.get_home_summary().dictionary_state == "NOT_INITIALIZED"
        ResearchDictionaryBootstrapService(conn).bootstrap()
        conn.execute("UPDATE data_dictionary SET is_active=0 WHERE internal_name='basin_area'")
        assert service.get_home_summary().dictionary_state == "INCONSISTENT"
        conn.execute("UPDATE data_dictionary SET is_active=1 WHERE internal_name='basin_area'")
        conn.execute("UPDATE dictionary_version SET description='tampered' WHERE is_current=1")
        assert service.get_home_summary().dictionary_state == "INCONSISTENT"


def test_history_projection_resolves_targets_and_hides_raw_fields(ctx):
    page = ctx.service.list_work_history(WorkHistoryRequest(page_size=3))
    assert page.total_count == 6 and page.total_pages == 2
    assert [item.change_type for item in page.items] == ["CORRECTION", "CACHE_REBUILD", "RESTORE"]
    assert all(item.stream_code is None or item.stream_code == STREAM for item in page.items)
    assert any(item.dictionary_standard_name == "유역면적" for item in page.items)
    assert all("private" not in repr(item) for item in page.items)
    assert all("characteristic_value_id" not in repr(item) for item in page.items)
    assert any(item.target_state == "UNRESOLVED" for item in ctx.service.list_work_history().items)
    assert any(item.actor_state == "UNKNOWN" for item in ctx.service.list_work_history().items)


def test_history_filters_pagination_and_validation(ctx):
    page = ctx.service.list_work_history(
        WorkHistoryRequest(page=1, page_size=2, change_type="CORRECTION", stream_code=STREAM)
    )
    assert page.total_count == 1 and len(page.items) == 1
    assert (
        ctx.service.list_work_history(
            WorkHistoryRequest(page_size=2, actor_user_id=ctx.other)
        ).total_count
        == 1
    )
    with pytest.raises(InvalidAppReadRequest):
        ctx.service.list_work_history(WorkHistoryRequest(change_type="IMPORT"))
    with pytest.raises(InvalidAppReadRequest):
        ctx.service.list_work_history(WorkHistoryRequest(page_size=101))
    with pytest.raises(InvalidAppReadRequest):
        ctx.service.list_work_history(WorkHistoryRequest(stream_code="bad"))


def test_public_profile_and_recent_work(ctx):
    profile = ctx.service.get_user_profile(ctx.actor)
    assert profile.login_id == "synthetic_actor"
    assert profile.display_name == "합성 작업자"
    assert "hash" not in repr(profile)
    assert len(ctx.service.recent_user_work(ctx.actor, limit=5)) == 3
    with pytest.raises(UserProfileNotFound):
        ctx.service.get_user_profile(999999)
    ctx.conn.execute("UPDATE app_user SET is_active=0 WHERE user_id=?", (ctx.actor,))
    with pytest.raises(InactiveUserProfile):
        ctx.service.get_user_profile(ctx.actor)


def test_read_projection_does_not_write_or_n_plus_one(ctx):
    statements = []
    before = snapshot(ctx.conn)
    ctx.conn.set_trace_callback(statements.append)
    ctx.service.list_work_history(WorkHistoryRequest(page_size=50))
    ctx.conn.set_trace_callback(None)
    after = snapshot(ctx.conn)
    assert after == before
    selects = [
        statement for statement in statements if statement.lstrip().upper().startswith("SELECT")
    ]
    assert len(selects) <= 5
    assert not any(
        statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE"))
        for statement in statements
    )
