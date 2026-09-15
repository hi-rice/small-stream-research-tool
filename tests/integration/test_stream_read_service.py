"""합성 SQLite에서 Phase 9A의 검색·페이지·안전한 표시 projection을 검증한다."""

from contextlib import closing
from dataclasses import replace
from types import SimpleNamespace

import pytest

from small_stream_research_tool.database import connect_database, initialize_database
from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.models.correction import CorrectionRequest
from small_stream_research_tool.models.stream_read import (
    CharacteristicDisplayPolicy,
    StreamListRequest,
)
from small_stream_research_tool.models.stream_read_errors import (
    InvalidStreamReadRequest,
    StreamReadFailure,
)
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.repositories.import_persistence_repository import (
    CharacteristicValueRepository,
    SmallStreamRepository,
)
from small_stream_research_tool.repositories.user_repository import UserRepository
from small_stream_research_tool.services.correction_service import CorrectionService
from small_stream_research_tool.services.current_value_service import CurrentValueService
from small_stream_research_tool.services.dictionary_service import DictionaryService
from small_stream_research_tool.services.stream_read_service import (
    MAX_PAGE_SIZE,
    StreamReadService,
)

STAMP = "2026-09-13T01:02:03Z"
RAW = "SYNTHETIC_RAW_ONLY"
PATH = "C:/synthetic-only/private-source.xlsx"


@pytest.fixture
def ctx(tmp_path):
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as conn:
        dictionary = DictionaryService(DictionaryRepository(conn))
        category = dictionary.create_category("synthetic", "Synthetic")
        version = dictionary.create_version("synthetic-v1")
        safe = dictionary.create_item(
            "Synthetic measurement",
            "synthetic_safe",
            category.category_id,
            "REAL",
            version.version_id,
        )
        private = dictionary.create_item(
            "Synthetic private",
            "synthetic_private",
            category.category_id,
            "TEXT",
            version.version_id,
        )
        with transaction(conn):
            actor = UserRepository(conn).create_user(
                login_id="synthetic_actor",
                password_hash="synthetic-not-for-login",
                display_name="Synthetic",
                department=None,
                role=None,
                timestamp=STAMP,
            )
        yield SimpleNamespace(
            conn=conn,
            path=path,
            actor=actor.user_id,
            safe=safe.dictionary_id,
            private=private.dictionary_id,
            service=StreamReadService(conn),
        )


def stream(
    ctx, serial, *, name="Synthetic Stream", province="01", city="234", town="567", active=True
):
    code = province + city + town + f"{serial:03d}"
    with transaction(ctx.conn):
        SmallStreamRepository(ctx.conn).create(
            stream_code=code,
            province_code=province,
            city_county_code=city,
            town_code=town,
            stream_serial_no=f"{serial:03d}",
            stream_name=name,
            province_name="Synthetic Province",
            city_county_name="Synthetic City",
            town_name="Synthetic Town",
            river_system="Synthetic System",
            source_address="Synthetic start",
            end_address="Synthetic end",
            is_active=active,
            created_at=STAMP,
            updated_at=STAMP,
        )
    return code


def value(ctx, code, item=None, **changes):
    item = ctx.safe if item is None else item
    data = dict(
        stream_code=code,
        dictionary_id=item,
        **({"value_number": 2.5} if item == ctx.safe else {"value_text": RAW}),
        original_value=RAW,
        created_at=STAMP,
        updated_at=STAMP,
    )
    data.update(changes)
    with transaction(ctx.conn):
        return CharacteristicValueRepository(ctx.conn).create(**data).characteristic_value_id


def issue(ctx, code, severity, value_id=None, active=True):
    ctx.conn.execute(
        "INSERT INTO data_quality_issue (stream_code,characteristic_value_id,issue_type,"
        "severity,message,is_active,created_at) VALUES (?,?,?,?,?,?,?)",
        (code, value_id, "SYNTHETIC", severity, "Synthetic", int(active), STAMP),
    )


def state(ctx):
    return {
        table: ctx.conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
        for table in (
            "small_stream",
            "characteristic_value",
            "stream_characteristic",
            "data_quality_issue",
            "record_history",
        )
    }


def test_empty_missing_and_one_stream(ctx):
    empty = ctx.service.list_streams()
    assert (empty.total_count, empty.total_pages, empty.rows) == (0, 0, ())
    assert ctx.service.get_stream_detail("01234567890") is None
    code = stream(ctx, 0)
    page = ctx.service.list_streams()
    assert page.total_count == page.total_pages == len(page.rows) == 1
    assert page.rows[0].stream_code == code
    assert page.rows[0].qc_display_state == "ACTIVE_ISSUES_NONE"
    detail = ctx.service.get_stream_detail(code)
    assert detail.basic.river_system == "Synthetic System"
    assert detail.basic.source_address == "Synthetic start"
    assert detail.characteristics == ()  # 명시적 항목 허용 없이는 값 자체를 조회하지 않는다.


def test_sql_pagination_search_region_sort_and_ties(ctx):
    for i in range(250):
        stream(
            ctx,
            i,
            name="Alpha" if i % 2 else "Beta",
            province="01" if i < 125 else "02",
            city="234" if i % 3 else "235",
        )
    first = ctx.service.list_streams(StreamListRequest(page=1, page_size=40))
    middle = ctx.service.list_streams(StreamListRequest(page=4, page_size=40))
    last = ctx.service.list_streams(StreamListRequest(page=7, page_size=40))
    beyond = ctx.service.list_streams(StreamListRequest(page=8, page_size=40))
    assert (first.total_count, first.total_pages) == (250, 7)
    assert (len(first.rows), len(middle.rows), len(last.rows), len(beyond.rows)) == (
        40,
        40,
        10,
        0,
    )
    codes = [r.stream_code for page in (first, middle, last) for r in page.rows]
    assert codes == sorted(codes) and len(codes) == len(set(codes))
    exact = ctx.service.list_streams(StreamListRequest(search="01234567005"))
    assert exact.total_count == 1 and exact.rows[0].stream_code == "01234567005"
    prefix = ctx.service.list_streams(StreamListRequest(search="01234567"))
    assert prefix.total_count == 83
    name = ctx.service.list_streams(StreamListRequest(search="Alp"))
    assert name.total_count == 125
    combined = ctx.service.list_streams(
        StreamListRequest(search="Alp", province_code="02", city_county_code="234", town_code="567")
    )
    assert combined.total_count > 0
    assert all(r.stream_code.startswith("02234") for r in combined.rows)
    sorted_page = ctx.service.list_streams(
        StreamListRequest(sort_field="stream_name", sort_direction="DESC", page_size=100)
    )
    assert all(r.stream_name == "Beta" for r in sorted_page.rows)
    assert [r.stream_code for r in sorted_page.rows] == sorted(
        r.stream_code for r in sorted_page.rows
    )


@pytest.mark.parametrize(
    "change",
    [
        {"page": 0},
        {"page": True},
        {"page_size": 0},
        {"page_size": MAX_PAGE_SIZE + 1},
        {"page_size": True},
        {"sort_field": "stream_code;DROP TABLE small_stream"},
        {"sort_field": []},
        {"sort_direction": "DOWN"},
        {"province_code": "1"},
        {"city_county_code": "AB3"},
        {"town_code": "１２３"},
        {"search": "012345678901"},
        {"search": " x "},
        {"active_only": 1},
    ],
)
def test_invalid_request_safe(ctx, change):
    with pytest.raises(InvalidStreamReadRequest) as error:
        ctx.service.list_streams(replace(StreamListRequest(), **change))
    assert "DROP" not in str(error.value)


@pytest.mark.parametrize(
    "severity,expected",
    [
        ("ERROR", "ERROR"),
        ("WARNING", "NEEDS_REVIEW"),
        ("INFO", "NEEDS_REVIEW"),
    ],
)
def test_page_qc_aggregate_is_not_qc_completion(ctx, severity, expected):
    a, b = stream(ctx, 0), stream(ctx, 1)
    issue(ctx, a, severity)
    issue(ctx, b, "ERROR", active=False)
    page = ctx.service.list_streams()
    assert [r.qc_display_state for r in page.rows] == [expected, "ACTIVE_ISSUES_NONE"]
    assert "QC_COMPLETE" not in repr(page) and "NORMAL" not in repr(page)


def test_valid_unassigned_inconsistent_and_historical_current(ctx):
    code = stream(ctx, 0)
    vid = value(ctx, code)
    policy = CharacteristicDisplayPolicy(frozenset({ctx.safe}))
    detail = ctx.service.get_stream_detail(code, display_policy=policy)
    assert detail.characteristics[0].current_use_status == "UNASSIGNED"
    assert detail.characteristics[0].current_value is None
    CurrentValueService(ctx.conn).select_current_value(vid, ctx.actor)
    valid = ctx.service.get_stream_detail(code, display_policy=policy).characteristics[0]
    assert valid.current_use_status == "VALID_CURRENT" and valid.current_value == 2.5
    issue(ctx, code, "WARNING", vid)
    assert (
        ctx.service.get_stream_detail(code, display_policy=policy)
        .characteristics[0]
        .qc_display_state
        == "NEEDS_REVIEW"
    )
    ctx.conn.execute("DELETE FROM stream_characteristic")
    before = state(ctx)
    inconsistent = ctx.service.get_stream_detail(code, display_policy=policy).characteristics[0]
    assert inconsistent.current_use_status == "INCONSISTENT"
    assert inconsistent.current_value is None and state(ctx) == before
    ctx.conn.execute("UPDATE characteristic_value SET is_active=0")
    historical = ctx.service.get_stream_detail(code, display_policy=policy).characteristics[0]
    assert historical.current_use_status == "UNASSIGNED" and historical.current_value is None


def test_unit_display_does_not_infer_missing_value_unit(ctx):
    code = stream(ctx, 0)
    ctx.conn.execute(
        "INSERT INTO unit_dictionary (unit_name,unit_symbol,created_at,updated_at) "
        "VALUES ('Synthetic meter','m',?,?)",
        (STAMP, STAMP),
    )
    ctx.conn.execute("UPDATE data_dictionary SET unit_id=1 WHERE dictionary_id=?", (ctx.safe,))
    vid = value(ctx, code, unit_id=None)
    CurrentValueService(ctx.conn).select_current_value(vid, ctx.actor)
    shown = ctx.service.get_stream_detail(
        code, display_policy=CharacteristicDisplayPolicy(frozenset({ctx.safe}))
    ).characteristics[0]
    assert shown.current_use_status == "VALID_CURRENT"
    assert shown.unit_display is None


def test_wrong_cache_pointer_and_active_filter(ctx):
    first = stream(ctx, 0)
    other = stream(ctx, 1, active=False)
    a = value(ctx, first)
    b = value(ctx, other)
    CurrentValueService(ctx.conn).select_current_value(a, ctx.actor)
    ctx.conn.execute("UPDATE stream_characteristic SET characteristic_value_id=?", (b,))
    policy = CharacteristicDisplayPolicy(frozenset({ctx.safe}))
    read = ctx.service.get_stream_detail(first, display_policy=policy).characteristics[0]
    assert read.current_use_status == "INCONSISTENT" and read.current_value is None
    assert ctx.service.list_streams().total_count == 1
    all_rows = ctx.service.list_streams(StreamListRequest(active_only=False))
    assert all_rows.total_count == 2 and not all_rows.rows[1].is_active


def test_safe_provenance_and_correction_parent(ctx):
    code = stream(ctx, 0)
    ctx.conn.execute(
        "INSERT INTO source_file (file_name,original_path,registered_at) VALUES (?,?,?)",
        ("synthetic.xlsx", PATH, STAMP),
    )
    ctx.conn.execute(
        "INSERT INTO import_history (source_file_id,batch_code,import_type,status,"
        "started_at,created_at) VALUES (1,'synthetic','EXCEL','SUCCESS',?,?)",
        (STAMP, STAMP),
    )
    ctx.conn.execute(
        "INSERT INTO import_sheet (import_id,sheet_name,status,created_at) "
        "VALUES (1,'Synthetic','SUCCESS',?)",
        (STAMP,),
    )
    ctx.conn.execute(
        "INSERT INTO import_column_mapping (import_sheet_id,source_column_index,"
        "dictionary_id,mapping_status,mapping_method,created_at) "
        "VALUES (1,4,?,'USER_MAPPED','USER',?)",
        (ctx.safe, STAMP),
    )
    source_id = value(ctx, code, import_id=1, import_sheet_id=1, mapping_id=1, source_row=5)
    CurrentValueService(ctx.conn).select_current_value(source_id, ctx.actor)
    policy = CharacteristicDisplayPolicy(frozenset({ctx.safe}))
    summary = ctx.service.get_stream_detail(code, display_policy=policy).characteristics[0]
    assert summary.provenance.classification == "IMPORT"
    assert summary.provenance.file_name is None and summary.provenance.sheet_name is None
    assert (summary.provenance.source_row, summary.provenance.source_column) == (5, 4)
    explicit = CharacteristicDisplayPolicy(
        frozenset({ctx.safe}), show_source_file_name=True, show_sheet_name=True
    )
    named = ctx.service.get_stream_detail(code, display_policy=explicit).characteristics[0]
    assert (named.provenance.file_name, named.provenance.sheet_name) == (
        "synthetic.xlsx",
        "Synthetic",
    )
    created = CorrectionService(ctx.conn).create_correction(
        CorrectionRequest(source_id, ctx.actor, 4.5, "SOURCE_REVIEW")
    )
    CurrentValueService(ctx.conn).select_current_value(created.correction_value_id, ctx.actor)
    corrected = ctx.service.get_stream_detail(code, display_policy=explicit).characteristics[0]
    assert corrected.provenance.classification == "RESEARCHER_CORRECTION"
    assert corrected.provenance.parent_value_id == source_id
    assert corrected.provenance.file_name is None and corrected.provenance.sheet_name is None
    assert PATH not in repr(corrected) and RAW not in repr(corrected)


def test_explicit_allowlist_blocks_private_value_and_query_does_not_write(ctx):
    code = stream(ctx, 0)
    value(ctx, code, ctx.private)
    safe = value(ctx, code)
    CurrentValueService(ctx.conn).select_current_value(safe, ctx.actor)
    CurrentValueService(ctx.conn).select_current_value(
        ctx.conn.execute(
            "SELECT characteristic_value_id FROM characteristic_value WHERE dictionary_id=?",
            (ctx.private,),
        ).fetchone()[0],
        ctx.actor,
    )
    before = state(ctx)
    detail = ctx.service.get_stream_detail(
        code, display_policy=CharacteristicDisplayPolicy(frozenset({ctx.safe}))
    )
    assert len(detail.characteristics) == 1
    assert detail.characteristics[0].current_value == 2.5
    assert RAW not in repr(detail)
    assert state(ctx) == before
    assert not ctx.conn.in_transaction


def test_query_count_and_query_plan_on_synthetic_scale(ctx):
    with transaction(ctx.conn):
        repo = SmallStreamRepository(ctx.conn)
        for i in range(600):
            code = "01234567" + f"{i:03d}"
            repo.create(
                stream_code=code,
                province_code="01",
                city_county_code="234",
                town_code="567",
                stream_serial_no=f"{i:03d}",
                stream_name="Synthetic",
                created_at=STAMP,
                updated_at=STAMP,
            )
    trace = []
    ctx.conn.set_trace_callback(trace.append)
    try:
        page = ctx.service.list_streams(StreamListRequest(page_size=50))
    finally:
        ctx.conn.set_trace_callback(None)
    selects = [sql for sql in trace if sql.startswith("SELECT")]
    assert len(selects) == 3  # COUNT, bounded page, QC batch; page당 하천별 조회 없음.
    assert "LIMIT 50 OFFSET 0" in selects[1]
    assert " IN (" in selects[2]
    assert len(page.rows) == 50 and page.total_count == 600
    plan = ctx.conn.execute(
        "EXPLAIN QUERY PLAN SELECT stream_code FROM small_stream "
        "WHERE stream_code=? ORDER BY stream_code LIMIT 50",
        ("01234567000",),
    ).fetchall()
    assert any("sqlite_autoindex_small_stream" in row[3] for row in plan)


def test_detail_batch_query_count_is_independent_of_allowed_items(ctx):
    code = stream(ctx, 0)
    a = value(ctx, code)
    b = value(ctx, code, ctx.private)
    CurrentValueService(ctx.conn).select_current_value(a, ctx.actor)
    CurrentValueService(ctx.conn).select_current_value(b, ctx.actor)
    trace = []
    ctx.conn.set_trace_callback(trace.append)
    try:
        detail = ctx.service.get_stream_detail(
            code, display_policy=CharacteristicDisplayPolicy(frozenset({ctx.safe, ctx.private}))
        )
    finally:
        ctx.conn.set_trace_callback(None)
    assert len(detail.characteristics) == 2
    assert len([sql for sql in trace if sql.startswith("SELECT")]) == 7


def test_sql_failure_is_safe(ctx):
    ctx.conn.execute("DROP TABLE small_stream")
    with pytest.raises(StreamReadFailure) as error:
        ctx.service.list_streams()
    assert "small_stream" not in str(error.value)


def test_invalid_policy_and_no_gui_import(ctx):
    code = stream(ctx, 0)
    with pytest.raises(InvalidStreamReadRequest):
        ctx.service.get_stream_detail(
            code, display_policy=CharacteristicDisplayPolicy(frozenset({True}))
        )
    with pytest.raises(InvalidStreamReadRequest):
        ctx.service.get_stream_detail(
            code,
            display_policy=CharacteristicDisplayPolicy(
                frozenset({ctx.safe}), show_source_file_name=1
            ),
        )
    assert "PySide6" not in StreamReadService.__module__
