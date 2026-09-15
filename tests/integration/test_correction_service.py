"""합성 임시 DB에서 보정 보존·입력 계약·원자성·선택 분리를 검증한다."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from small_stream_research_tool.database import connect_database, initialize_database
from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.models.correction import CorrectionRequest
from small_stream_research_tool.models.correction_errors import (
    CorrectionError,
    CorrectionPersistenceError,
    CorrectionValidationError,
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

STAMP = "2026-09-13T01:02:03Z"
STREAM = "01234567890"
SECRET = "SYNTHETIC_PRIVATE_VALUE"


@pytest.fixture
def ctx(tmp_path):
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as conn:
        dictionary = DictionaryService(DictionaryRepository(conn))
        category = dictionary.create_category("synthetic", "Synthetic")
        version = dictionary.create_version("synthetic-v1")
        items = {
            t: dictionary.create_item(
                t, "synthetic_" + t.lower(), category.category_id, t, version.version_id
            )
            for t in ("INTEGER", "REAL", "TEXT", "DATE", "DATETIME")
        }
        with transaction(conn):
            SmallStreamRepository(conn).create(
                stream_code=STREAM,
                province_code="01",
                city_county_code="234",
                town_code="567",
                stream_serial_no="890",
                stream_name="Synthetic",
                created_at=STAMP,
                updated_at=STAMP,
            )
            actor = UserRepository(conn).create_user(
                login_id="synthetic",
                password_hash="synthetic-not-a-password",
                display_name="Synthetic",
                department=None,
                role=None,
                timestamp=STAMP,
            )
        yield SimpleNamespace(
            conn=conn, path=path, items=items, actor=actor.user_id, service=CorrectionService(conn)
        )


def source(ctx, dtype="REAL", **changes):
    field, value = {
        "REAL": ("value_number", 1.5),
        "INTEGER": ("value_integer", 2),
        "TEXT": ("value_text", SECRET),
        "DATE": ("value_date", "2020-01-01"),
        "DATETIME": ("value_date", "2020-01-01T01:02:03"),
    }[dtype]
    data = dict(
        stream_code=STREAM,
        dictionary_id=ctx.items[dtype].dictionary_id,
        **{field: value},
        original_value=SECRET,
        original_unit="synthetic raw unit",
        source_reference="C:/synthetic-only/source.xlsx",
        reference_year=2020,
        created_at=STAMP,
        updated_at=STAMP,
    )
    data.update(changes)
    with transaction(ctx.conn):
        return CharacteristicValueRepository(ctx.conn).create(**data)


def request(ctx, value, corrected=3.5, **changes):
    return CorrectionRequest(
        value.characteristic_value_id, ctx.actor, corrected, "SOURCE_REVIEW", **changes
    )


def snapshot(conn):
    tables = [
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    ]
    return {table: conn.execute(f'SELECT * FROM "{table}"').fetchall() for table in tables}


@pytest.mark.parametrize(
    ("dtype", "value", "field", "stored"),
    [
        ("INTEGER", 4, "value_integer", 4),
        ("REAL", 3.5, "value_number", 3.5),
        ("REAL", "2.5e1", "value_number", 25.0),
        ("REAL", 2, "value_number", 2.0),
        ("TEXT", "  MiXeD\t ", "value_text", "  MiXeD\t "),
        ("TEXT", "", "value_text", ""),
        ("TEXT", "   ", "value_text", "   "),
        ("DATE", date(2024, 2, 29), "value_date", "2024-02-29"),
        ("DATE", "2024-02-29", "value_date", "2024-02-29"),
        ("DATETIME", datetime(2024, 1, 1, 2, 3, 4), "value_date", "2024-01-01T02:03:04"),
        ("DATETIME", "2024-01-01T02:03:04+09:00", "value_date", "2024-01-01T02:03:04+09:00"),
    ],
)
def test_creation_contract(ctx, dtype, value, field, stored):
    original = source(ctx, dtype)
    before = snapshot(ctx.conn)
    result = ctx.service.create_correction(request(ctx, original, value))
    after = snapshot(ctx.conn)
    created = CharacteristicValueRepository(ctx.conn).get_by_id(result.correction_value_id)
    assert result.correction_value_id != original.characteristic_value_id
    assert result.source_value_id == original.characteristic_value_id
    assert created.stream_code == STREAM and created.dictionary_id == original.dictionary_id
    assert getattr(created, field) == stored
    assert (
        sum(
            getattr(created, f) is not None
            for f in ("value_number", "value_integer", "value_text", "value_date")
        )
        == 1
    )
    assert created.is_active and not created.is_representative
    assert created.source_type == "USER_CORRECTION"
    assert created.quality_status == "UNREVIEWED"
    assert created.reference_year == 2020
    assert all(
        getattr(created, f) is None
        for f in (
            "original_value",
            "original_unit",
            "source_reference",
            "import_id",
            "import_sheet_id",
            "mapping_id",
            "source_row",
        )
    )
    assert created.created_at == created.updated_at == result.created_at
    assert result.created_at.endswith("Z")
    datetime.fromisoformat(result.created_at)
    assert (
        CharacteristicValueRepository(ctx.conn).get_by_id(original.characteristic_value_id)
        == original
    )
    for table in before.keys() - {"characteristic_value", "record_history"}:
        assert after[table] == before[table]
    history = ctx.service._repository.get_history(result.history_id)
    assert history[0] == "characteristic_value" and history[4] == "CORRECTION"
    assert json.loads(history[1]) == {
        "stream_code": STREAM,
        "dictionary_id": original.dictionary_id,
    }
    assert json.loads(history[2]) == {"source_value_id": original.characteristic_value_id}
    assert json.loads(history[3]) == {
        "correction_value_id": result.correction_value_id,
        "event": "USER_CORRECTION_CREATE",
    }
    assert history[5:8] == ("SOURCE_REVIEW", ctx.actor, result.created_at)
    assert SECRET not in repr(history) and "source.xlsx" not in repr(history)
    assert SECRET not in repr(request(ctx, original, SECRET))
    with pytest.raises(FrozenInstanceError):
        result.source_value_id = 0


@pytest.mark.parametrize(
    ("dtype", "value"),
    [
        ("INTEGER", 1.2),
        ("INTEGER", 1.0),
        ("INTEGER", "1"),
        ("INTEGER", True),
        ("INTEGER", 2**63),
        ("INTEGER", -(2**63) - 1),
        ("INTEGER", None),
        ("REAL", float("nan")),
        ("REAL", float("inf")),
        ("REAL", -float("inf")),
        ("REAL", True),
        ("REAL", "1e999"),
        ("REAL", "1e-999"),
        ("REAL", SECRET),
        ("REAL", None),
        ("TEXT", None),
        ("TEXT", 4),
        ("TEXT", "\ud800"),
        ("DATE", "2023-02-29"),
        ("DATE", "2024-13-01"),
        ("DATE", 123),
        ("DATETIME", "2024-01-01"),
        ("DATETIME", "2024-01-01T12:00:00-00:00"),
        ("DATETIME", "2024-01-01T25:00:00"),
    ],
)
def test_invalid_typed_input_rolls_back(ctx, dtype, value):
    original = source(ctx, dtype)
    before = snapshot(ctx.conn)
    with pytest.raises(CorrectionValidationError) as error:
        ctx.service.create_correction(request(ctx, original, value))
    assert SECRET not in str(error.value)
    assert snapshot(ctx.conn) == before
    assert not ctx.conn.in_transaction


@pytest.mark.parametrize(
    "change",
    [
        "source_missing",
        "source_inactive",
        "actor_missing",
        "actor_inactive",
        "stream_inactive",
        "dictionary_inactive",
        "category_inactive",
        "deprecated",
        "core",
        "type",
    ],
)
def test_source_actor_metadata_validation(ctx, change):
    original = source(ctx)
    req = request(ctx, original)
    sql = {
        "source_inactive": "UPDATE characteristic_value SET is_active=0",
        "actor_inactive": "UPDATE app_user SET is_active=0",
        "stream_inactive": "UPDATE small_stream SET is_active=0",
        "dictionary_inactive": "UPDATE data_dictionary SET is_active=0",
        "category_inactive": "UPDATE data_category SET is_active=0",
        "deprecated": "UPDATE data_dictionary SET deprecated_version_id=created_version_id",
        "core": "UPDATE data_dictionary SET storage_type='CORE'",
    }
    if change in sql:
        ctx.conn.execute(sql[change])
    elif change == "type":
        ctx.conn.execute("PRAGMA ignore_check_constraints=ON")
        ctx.conn.execute("UPDATE data_dictionary SET data_type='UNKNOWN'")
        ctx.conn.execute("PRAGMA ignore_check_constraints=OFF")
    else:
        req = replace(
            req, **{("source_value_id" if change == "source_missing" else "actor_user_id"): 999}
        )
    before = snapshot(ctx.conn)
    with pytest.raises(CorrectionValidationError):
        ctx.service.create_correction(req)
    assert snapshot(ctx.conn) == before


def units(ctx):
    with transaction(ctx.conn):
        repo = DictionaryRepository(ctx.conn)
        return tuple(
            repo.create_unit(
                unit_name=n, unit_symbol=n, dimension=d, created_at=STAMP, updated_at=STAMP
            ).unit_id
            for n, d in (("m", "length"), ("km", "length"), ("s", "time"))
        )


@pytest.mark.parametrize(
    "mode",
    ["inherit", "expected", "incompatible", "other_scale", "inactive", "missing", "null", "bool"],
)
def test_unit_policy(ctx, mode):
    meter, km, second = units(ctx)
    ctx.conn.execute(
        "UPDATE data_dictionary SET unit_id=? WHERE dictionary_id=?",
        (meter, ctx.items["REAL"].dictionary_id),
    )
    original = source(ctx, unit_id=km)
    req = request(ctx, original, 2000)
    if mode == "inactive":
        ctx.conn.execute("UPDATE unit_dictionary SET is_active=0 WHERE unit_id=?", (km,))
    elif mode != "inherit":
        req = replace(
            req,
            corrected_unit_id={
                "expected": meter,
                "incompatible": second,
                "other_scale": km,
                "missing": 999,
                "null": None,
                "bool": True,
            }[mode],
        )
    before = snapshot(ctx.conn)
    if mode in ("inherit", "expected"):
        result = ctx.service.create_correction(req)
        created = CharacteristicValueRepository(ctx.conn).get_by_id(result.correction_value_id)
        assert created.unit_id == (km if mode == "inherit" else meter)
        assert created.value_number == 2000
    else:
        with pytest.raises(CorrectionValidationError):
            ctx.service.create_correction(req)
        assert snapshot(ctx.conn) == before


def test_null_unit_and_reference_year(ctx):
    original = source(ctx, reference_year=None)
    result = ctx.service.create_correction(request(ctx, original, corrected_unit_id=None))
    created = CharacteristicValueRepository(ctx.conn).get_by_id(result.correction_value_id)
    assert created.unit_id is None and created.reference_year is None


def test_duplicate_and_correction_chain(ctx):
    original = source(ctx)
    req = request(ctx, original)
    a = ctx.service.create_correction(req)
    b = ctx.service.create_correction(req)
    c = ctx.service.create_correction(replace(req, source_value_id=a.correction_value_id))
    assert len({a.correction_value_id, b.correction_value_id, c.correction_value_id}) == 3
    assert json.loads(ctx.service._repository.get_history(c.history_id)[2]) == {
        "source_value_id": a.correction_value_id
    }


@pytest.mark.parametrize("failure", ["history", "verify", "commit"])
def test_atomic_failures(ctx, monkeypatch, failure):
    original = source(ctx)
    before = snapshot(ctx.conn)
    if failure == "history":
        ctx.conn.execute(
            "CREATE TRIGGER fail_history BEFORE INSERT ON record_history "
            "BEGIN SELECT RAISE(ABORT, 'SYNTHETIC_PRIVATE_VALUE'); END"
        )
    elif failure == "verify":
        monkeypatch.setattr(ctx.service._repository, "get_history", lambda _: None)
    else:
        ctx.conn.set_authorizer(
            lambda action, arg, *_: (
                sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_TRANSACTION and arg == "COMMIT"
                else sqlite3.SQLITE_OK
            )
        )
    try:
        with pytest.raises(CorrectionPersistenceError) as error:
            ctx.service.create_correction(request(ctx, original))
    finally:
        ctx.conn.set_authorizer(None)
    assert SECRET not in str(error.value)
    assert snapshot(ctx.conn) == before
    assert not ctx.conn.in_transaction


def test_no_updates_or_automatic_selection(ctx):
    original = source(ctx)
    CurrentValueService(ctx.conn).select_current_value(original.characteristic_value_id, ctx.actor)
    before = snapshot(ctx.conn)
    ctx.conn.set_authorizer(
        lambda action, *_: (
            sqlite3.SQLITE_DENY
            if action in (sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE)
            else sqlite3.SQLITE_OK
        )
    )
    try:
        result = ctx.service.create_correction(request(ctx, original))
    finally:
        ctx.conn.set_authorizer(None)
    after = snapshot(ctx.conn)
    assert after["stream_characteristic"] == before["stream_characteristic"]
    assert after["data_quality_issue"] == before["data_quality_issue"]
    assert after["characteristic_value"][:-1] == before["characteristic_value"]
    assert (
        not CharacteristicValueRepository(ctx.conn)
        .get_by_id(result.correction_value_id)
        .is_representative
    )
    with pytest.raises(TypeError):
        ctx.service.create_correction(request(ctx, original), select_as_current=True)


def test_concurrent_corrections(ctx):
    original = source(ctx)

    def create(value):
        with closing(connect_database(ctx.path)) as conn:
            return CorrectionService(conn).create_correction(request(ctx, original, value))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, (4.5, 5.5)))
    assert len({r.correction_value_id for r in results}) == 2
    assert ctx.conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert ctx.conn.execute("SELECT count(*) FROM stream_characteristic").fetchone()[0] == 0


@pytest.mark.parametrize("code", ["RESEARCHER_SELECTION", "SOURCE_REVIEW", "QC_REVIEW_CONFIRMED"])
def test_reason_codes(ctx, code):
    req = replace(request(ctx, source(ctx)), reason_code=code)
    result = ctx.service.create_correction(req)
    assert ctx.service._repository.get_history(result.history_id)[5] == code


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_value_id", True),
        ("source_value_id", 0),
        ("actor_user_id", None),
        ("actor_user_id", 2**63),
        ("reason_code", None),
        ("reason_code", SECRET),
    ],
)
def test_request_validation(ctx, field, value):
    req = replace(request(ctx, source(ctx)), **{field: value})
    before = snapshot(ctx.conn)
    with pytest.raises(CorrectionError):
        ctx.service.create_correction(req)
    assert snapshot(ctx.conn) == before


@pytest.mark.parametrize("value", [-(2**63), 2**63 - 1])
def test_integer_boundaries(ctx, value):
    original = source(ctx, "INTEGER")
    result = ctx.service.create_correction(request(ctx, original, value))
    assert (
        CharacteristicValueRepository(ctx.conn).get_by_id(result.correction_value_id).value_integer
        == value
    )


def test_explicit_inactive_expected_unit(ctx):
    meter, _, _ = units(ctx)
    ctx.conn.execute("UPDATE data_dictionary SET unit_id=?", (meter,))
    original = source(ctx)
    ctx.conn.execute("UPDATE unit_dictionary SET is_active=0 WHERE unit_id=?", (meter,))
    with pytest.raises(CorrectionValidationError):
        ctx.service.create_correction(request(ctx, original, corrected_unit_id=meter))


@pytest.mark.parametrize("target", ["source", "correction", "history"])
def test_final_invariant_detects_mutation(ctx, target):
    original = source(ctx)
    before = snapshot(ctx.conn)
    sql = {
        "source": """UPDATE characteristic_value SET value_number=99
        WHERE characteristic_value_id=1;""",
        "correction": """UPDATE characteristic_value SET is_active=0
        WHERE source_type='USER_CORRECTION';""",
        "history": "UPDATE record_history SET reason='INVALID' WHERE history_id=NEW.history_id;",
    }[target]
    ctx.conn.execute("CREATE TRIGGER corrupt AFTER INSERT ON record_history BEGIN " + sql + " END")
    with pytest.raises(CorrectionPersistenceError):
        ctx.service.create_correction(request(ctx, original))
    assert snapshot(ctx.conn) == before


def test_nested_transaction_preserves_callers_work(ctx):
    original = source(ctx)
    with transaction(ctx.conn):
        ctx.conn.execute("UPDATE small_stream SET stream_name='caller work'")
        before = snapshot(ctx.conn)
        with pytest.raises(CorrectionPersistenceError):
            ctx.service.create_correction(request(ctx, original))
        assert ctx.conn.in_transaction and snapshot(ctx.conn) == before


def test_import_provenance_stays_only_on_source(ctx):
    conn = ctx.conn
    conn.execute(
        "INSERT INTO source_file (file_name,original_path,registered_at) VALUES (?,?,?)",
        ("synthetic.xlsx", "C:/synthetic-only/source.xlsx", STAMP),
    )
    conn.execute(
        "INSERT INTO import_history (source_file_id,batch_code,import_type,status,"
        "started_at,created_at) VALUES (1,'synthetic','EXCEL','SUCCESS',?,?)",
        (STAMP, STAMP),
    )
    conn.execute(
        "INSERT INTO import_sheet (import_id,sheet_name,status,created_at) "
        "VALUES (1,'synthetic','SUCCESS',?)",
        (STAMP,),
    )
    conn.execute(
        "INSERT INTO import_column_mapping (import_sheet_id,source_column_index,"
        "mapping_status,mapping_method,created_at) VALUES (1,4,'USER_MAPPED','USER',?)",
        (STAMP,),
    )
    original = source(ctx, import_id=1, import_sheet_id=1, mapping_id=1, source_row=5)
    result = ctx.service.create_correction(request(ctx, original))
    repo = CharacteristicValueRepository(conn)
    assert repo.get_by_id(original.characteristic_value_id) == original
    created = repo.get_by_id(result.correction_value_id)
    assert (created.import_id, created.import_sheet_id, created.mapping_id, created.source_row) == (
        None,
    ) * 4


def test_correction_qc_then_separate_selection(ctx):
    from small_stream_research_tool.models.current_value_errors import (
        CurrentValueBlockedByQualityError,
    )
    from small_stream_research_tool.models.import_preparation import ImportFieldPolicy
    from small_stream_research_tool.models.quality_control import QualityControlRequest
    from small_stream_research_tool.services.quality_control_service import QualityControlService

    original = source(ctx)
    result = ctx.service.create_correction(request(ctx, original, -2.0))
    ctx.conn.execute(
        "INSERT INTO quality_rule (rule_code,rule_name,target_type,dictionary_id,rule_type,"
        "default_severity,rule_version,is_enabled,created_at,updated_at) "
        "VALUES ('synthetic','Synthetic','CHARACTERISTIC_VALUE',?,"
        "'NON_NEGATIVE','ERROR','v1',1,?,?)",
        (original.dictionary_id, STAMP, STAMP),
    )
    assert ctx.conn.execute("SELECT count(*) FROM data_quality_issue").fetchone()[0] == 0
    QualityControlService(ctx.conn).run(
        QualityControlRequest((result.correction_value_id,), ()),
        field_policy=ImportFieldPolicy(frozenset()),
    )
    with pytest.raises(CurrentValueBlockedByQualityError):
        CurrentValueService(ctx.conn).select_current_value(result.correction_value_id, ctx.actor)
    assert CharacteristicValueRepository(ctx.conn).get_by_id(result.correction_value_id) is not None
    assert ctx.conn.execute("SELECT count(*) FROM stream_characteristic").fetchone()[0] == 0
