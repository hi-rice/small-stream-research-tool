"""합성 값과 tmp SQLite로 저장·제약·출처·공유 transaction의 실제 효과를 검증한다."""

import sqlite3
import traceback
from contextlib import closing
from dataclasses import FrozenInstanceError, asdict, fields
from types import SimpleNamespace

import pytest

from small_stream_research_tool.database import connect_database, initialize_database
from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.models.column_mapping import MappingMethod, MappingStatus
from small_stream_research_tool.models.import_persistence import (
    CharacteristicValueRecord,
    ImportColumnMappingRecord,
    ImportHistoryRecord,
    ImportSheetRecord,
    SmallStreamRecord,
    SourceFileRecord,
)
from small_stream_research_tool.models.import_persistence_errors import (
    ConstraintViolationError,
    DuplicateRecordError,
    ForeignKeyReferenceError,
    InvalidPersistenceArgumentError,
    PersistenceError,
    RecordNotFoundError,
    TransactionRequiredError,
)
from small_stream_research_tool.models.import_preparation import (
    PreparedCharacteristicValue,
    PreparedStreamData,
)
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.repositories.import_persistence_repository import (
    CharacteristicValueRepository,
    ImportColumnMappingRepository,
    ImportHistoryRepository,
    ImportSheetRepository,
    SmallStreamRepository,
    SourceFileRepository,
)
from small_stream_research_tool.repositories.user_repository import UserRepository
from small_stream_research_tool.services.dictionary_service import DictionaryService
from small_stream_research_tool.utils.timestamps import utc_now_text

STAMP = "2026-09-12T01:02:03Z"
LATER = "2026-09-12T02:03:04Z"
STREAM = "12345678009"
NEW_STREAM = "12345678008"
HASH = "a" * 64
SYNTHETIC_PATH = "C:/synthetic-research-only/synthetic_input.xlsx"
REPOSITORIES = {
    "source_file": SourceFileRepository,
    "import_history": ImportHistoryRepository,
    "import_sheet": ImportSheetRepository,
    "import_column_mapping": ImportColumnMappingRepository,
    "small_stream": SmallStreamRepository,
    "characteristic_value": CharacteristicValueRepository,
}
MODELS = (
    SourceFileRecord,
    ImportHistoryRecord,
    ImportSheetRecord,
    ImportColumnMappingRecord,
    SmallStreamRecord,
    CharacteristicValueRecord,
)


@pytest.fixture
def context(tmp_path):
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as connection:
        dictionary = DictionaryService(DictionaryRepository(connection))
        category = dictionary.create_category("synthetic", "Synthetic Category")
        version = dictionary.create_version("synthetic-v1")
        unit = dictionary.create_unit("Synthetic Unit", "syn")
        item = dictionary.create_item(
            "Synthetic Metric",
            "synthetic_metric",
            category.category_id,
            "REAL",
            version.version_id,
            unit_id=unit.unit_id,
        )
        with transaction(connection):
            user = UserRepository(connection).create_user(
                login_id="synthetic_user",
                password_hash="SYNTHETIC_TEST_HASH_ONLY",
                display_name="Synthetic User",
                department=None,
                role=None,
                timestamp=STAMP,
            )
        ctx = SimpleNamespace(
            path=path,
            connection=connection,
            dictionary=dictionary,
            item=item,
            unit=unit,
            user=user,
            version=version,
            schema_id=connection.execute("SELECT schema_version_id FROM schema_version").fetchone()[
                0
            ],
            repos={name: cls(connection) for name, cls in REPOSITORIES.items()},
            records={},
        )
        with transaction(connection):
            source = ctx.repos["source_file"].create(
                file_name="synthetic_input.xlsx",
                original_path=SYNTHETIC_PATH,
                file_hash=HASH,
                registered_at=STAMP,
            )
            history = ctx.repos["import_history"].create(
                source_file_id=source.source_file_id,
                batch_code="synthetic-base",
                import_type="SYNTHETIC",
                status="RUNNING",
                started_at=STAMP,
                created_at=STAMP,
            )
            sheet = ctx.repos["import_sheet"].create(
                import_id=history.import_id,
                sheet_name="Synthetic Base",
                status="RUNNING",
                created_at=STAMP,
            )
            mapping = ctx.repos["import_column_mapping"].create(
                import_sheet_id=sheet.import_sheet_id,
                source_column_index=1,
                dictionary_id=item.dictionary_id,
                mapping_status="MAPPED",
                mapping_method="USER",
                created_at=STAMP,
            )
            stream = ctx.repos["small_stream"].create(
                stream_code=STREAM,
                province_code="12",
                city_county_code="345",
                town_code="678",
                stream_serial_no="009",
                stream_name="Synthetic Stream A",
                created_at=STAMP,
                updated_at=STAMP,
            )
        ctx.records = dict(
            zip(REPOSITORIES, (source, history, sheet, mapping, stream), strict=False)
        )
        yield ctx


def values(context, table):
    r = context.records
    return {
        "source_file": dict(
            file_name="synthetic_second.xlsx",
            original_path=SYNTHETIC_PATH,
            file_extension=".xlsx",
            file_size=123,
            file_hash=HASH,
            file_modified_at=STAMP,
            source_description="Synthetic Description",
            registered_at=STAMP,
        ),
        "import_history": dict(
            source_file_id=r["source_file"].source_file_id,
            created_by_user_id=context.user.user_id,
            batch_code="synthetic-next",
            import_type="SYNTHETIC",
            status="RUNNING",
            started_at=STAMP,
            finished_at=None,
            total_rows=4,
            accepted_rows=2,
            warning_rows=1,
            rejected_rows=1,
            dictionary_version_id=context.version.version_id,
            schema_version_id=context.schema_id,
            settings_json='{"synthetic_option":"SYNTHETIC_PRIVATE_SETTING"}',
            error_code="SYNTHETIC_ERROR",
            error_message="SYNTHETIC_PRIVATE_DIAGNOSTIC",
            created_at=STAMP,
        ),
        "import_sheet": dict(
            import_id=r["import_history"].import_id,
            sheet_name="Synthetic Next",
            sheet_index=0,
            header_start_row=1,
            header_end_row=2,
            data_start_row=3,
            total_rows=4,
            accepted_rows=2,
            warning_rows=1,
            rejected_rows=1,
            status="RUNNING",
            created_at=STAMP,
        ),
        "import_column_mapping": dict(
            import_sheet_id=r["import_sheet"].import_sheet_id,
            source_column_index=4,
            source_header=" Synthetic Header ",
            normalized_header="synthetic header",
            dictionary_id=context.item.dictionary_id,
            mapping_status="MAPPED",
            mapping_method="USER",
            source_unit="syn",
            target_unit_id=context.unit.unit_id,
            transform_rule="SYNTHETIC_OPAQUE",
            user_confirmed=True,
            created_at=STAMP,
        ),
        "small_stream": dict(
            stream_code=NEW_STREAM,
            province_code="12",
            city_county_code="345",
            town_code="678",
            stream_serial_no="008",
            stream_name="Synthetic Stream B",
            province_name="Synthetic P",
            city_county_name="Synthetic C",
            town_name="Synthetic T",
            river_system="Synthetic R",
            source_address="Synthetic Source",
            source_latitude=45.0,
            source_longitude=120.0,
            end_address="Synthetic End",
            end_latitude=-45.0,
            end_longitude=-120.0,
            created_at=STAMP,
            updated_at=STAMP,
        ),
        "characteristic_value": dict(
            stream_code=STREAM,
            dictionary_id=context.item.dictionary_id,
            value_number=4.24,
            unit_id=context.unit.unit_id,
            original_value=" 4.24 ",
            original_unit="syn",
            import_id=r["import_history"].import_id,
            import_sheet_id=r["import_sheet"].import_sheet_id,
            source_row=9,
            mapping_id=r["import_column_mapping"].mapping_id,
            source_reference="Synthetic Reference",
            reference_year=2026,
            created_at=STAMP,
            updated_at=STAMP,
        ),
    }[table]


def create(context, table, **changes):
    return context.repos[table].create(**(values(context, table) | changes))


def count(context, table):
    # table은 이 테스트에서 고정한 테이블 이름만 사용한다.
    return context.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


@pytest.mark.parametrize("table,model", tuple(zip(REPOSITORIES, MODELS, strict=True)))
def test_create_roundtrip_and_schema_columns(context, table, model):
    with transaction(context.connection):
        record = create(context, table)
    repository = context.repos[table]
    actual_columns = [row[1] for row in context.connection.execute(f"PRAGMA table_info({table})")]
    assert [f.name for f in fields(model)] == actual_columns
    assert type(record) is model
    for name, value in values(context, table).items():
        assert getattr(record, name) == value
    if table == "small_stream":
        assert repository.get_by_stream_code(record.stream_code) == record
    else:
        assert repository.get_by_id(getattr(record, actual_columns[0])) == record
    with pytest.raises(FrozenInstanceError):
        record.created_at = LATER


def test_source_hash_zero_one_multiple_and_not_unique(context):
    repo = context.repos["source_file"]
    assert repo.find_by_hash("b" * 64) == [] and repo.find_by_hash(None) == []
    assert len(repo.find_by_hash(HASH)) == 1
    with repo.transaction():
        second = create(context, "source_file")
        inactive = create(context, "source_file", is_active=False)
    assert repo.find_by_hash(HASH) == [context.records["source_file"], second, inactive]
    assert not inactive.is_active and second.is_active


def test_batch_exact_lookup_duplicate_and_no_uuid(context):
    repo = context.repos["import_history"]
    assert repo.get_by_batch_code("synthetic-missing") is None
    with transaction(context.connection):
        record = create(context, "import_history", batch_code=" Synthetic ' Batch ")
        assert repo.get_by_batch_code(" Synthetic ' Batch ") == record
        assert repo.get_by_batch_code("Synthetic ' Batch") is None
        with pytest.raises(DuplicateRecordError):
            create(context, "import_history", batch_code=" Synthetic ' Batch ")
    assert repo.get_by_id(record.import_id) == record


@pytest.mark.parametrize(
    "status", ["PENDING", "RUNNING", "SUCCESS", "FAILED", "ROLLED_BACK", "CANCELLED"]
)
def test_history_status_caller_controls_times_and_counts(context, status):
    repo = context.repos["import_history"]
    with repo.transaction():
        original = create(context, "import_history", status="SUCCESS", finished_at=LATER)
        result = repo.update_status(original.import_id, status)
        assert result.status == status and result.finished_at == LATER
        assert result.started_at == STAMP and result.created_at == STAMP
        cleared = repo.update_status(original.import_id, status, finished_at=None, accepted_rows=3)
        assert cleared.finished_at is None and cleared.accepted_rows == 3
        done = repo.update_status(original.import_id, status, finished_at=LATER, error_message=None)
        assert done.finished_at == LATER and done.error_message is None
    assert repo.list_by_status(status)[-1] == done
    assert repo.count_by_status(status) == len(repo.list_by_status(status))


def test_status_invalid_missing_record_and_no_implicit_commit(context):
    repo = context.repos["import_history"]
    before = context.records["import_history"]
    with pytest.raises(TransactionRequiredError):
        repo.update_status(before.import_id, "SUCCESS")
    with transaction(context.connection):
        with pytest.raises(ConstraintViolationError):
            repo.update_status(before.import_id, "SYNTHETIC_INVALID_STATUS")
        with pytest.raises(RecordNotFoundError):
            repo.update_status(999999, "SUCCESS")
        with pytest.raises(InvalidPersistenceArgumentError):
            repo.update_status(before.import_id, "SUCCESS", batch_code="changed")
    assert repo.get_by_id(before.import_id) == before


def test_sheet_and_mapping_lists_counts_and_unique(context):
    sheets = context.repos["import_sheet"]
    maps = context.repos["import_column_mapping"]
    import_id = context.records["import_history"].import_id
    sheet_id = context.records["import_sheet"].import_sheet_id
    assert sheets.list_by_import_id(999999) == [] and sheets.count_by_import_id(999999) == 0
    assert maps.list_by_import_sheet_id(999999) == [] and maps.count_by_import_sheet_id(999999) == 0
    with transaction(context.connection):
        sheet = create(context, "import_sheet")
        mapping = create(context, "import_column_mapping")
        with pytest.raises(DuplicateRecordError):
            create(context, "import_sheet")
        with pytest.raises(DuplicateRecordError):
            create(context, "import_column_mapping")
    assert sheets.list_by_import_id(import_id) == [context.records["import_sheet"], sheet]
    assert maps.list_by_import_sheet_id(sheet_id) == [
        context.records["import_column_mapping"],
        mapping,
    ]
    assert (
        sheets.count_by_import_id(import_id) == 2 and maps.count_by_import_sheet_id(sheet_id) == 2
    )
    assert sheet.header_start_row == 1 and mapping.source_column_index == 4


@pytest.mark.parametrize(
    "status,method",
    [
        (MappingStatus.AUTO_MAPPED, MappingMethod.AUTO_ALIAS),
        (MappingStatus.USER_MAPPED, MappingMethod.USER),
        (MappingStatus.UNMAPPED, MappingMethod.NONE),
        (MappingStatus.DO_NOT_MAP, MappingMethod.USER),
        (MappingStatus.NEEDS_REVIEW, MappingMethod.USER),
        ("IGNORED", "NONE"),
        ("AMBIGUOUS", "AUTO_STANDARD_NAME"),
    ],
)
def test_mapping_text_no_implicit_adapter_nullable_dictionary(context, status, method):
    with transaction(context.connection):
        result = create(
            context,
            "import_column_mapping",
            dictionary_id=None,
            mapping_status=status,
            mapping_method=method,
        )
    assert result.mapping_status == status and result.mapping_method == method
    assert result.dictionary_id is None


@pytest.mark.parametrize(
    "changes",
    [
        {"stream_code": "bad"},
        {"stream_code": "1234567800X"},
        {"stream_code": "123456780080"},
        {"stream_code": "1234567800\0"},
        {"province_code": "1"},
        {"city_county_code": "34"},
        {"town_code": "67"},
        {"stream_serial_no": "08"},
        {"stream_name": None},
        {"source_latitude": 91.0},
        {"end_longitude": 181.0},
    ],
)
def test_malformed_stream_rejected_without_correction(context, changes):
    with transaction(context.connection), pytest.raises(ConstraintViolationError):
        create(context, "small_stream", **changes)
    assert context.repos["small_stream"].count() == 1


def test_stream_duplicate_no_upsert_and_leading_zero(context):
    repo = context.repos["small_stream"]
    assert repo.exists_by_stream_code(STREAM) and not repo.exists_by_stream_code(NEW_STREAM)
    assert repo.get_by_stream_code(NEW_STREAM) is None
    before = repo.get_by_stream_code(STREAM)
    with transaction(context.connection):
        with pytest.raises(DuplicateRecordError):
            create(context, "small_stream", stream_code=STREAM, stream_name="Synthetic Changed")
        result = create(context, "small_stream", stream_code="02345678008", province_code="02")
    assert repo.get_by_stream_code(STREAM) == before
    assert result.stream_code == "02345678008" and result.province_code == "02"


@pytest.mark.parametrize(
    "field,value",
    [
        ("value_number", 4.24),
        ("value_integer", 3),
        ("value_text", "  Synthetic Text  "),
        ("value_date", "2026-09-12"),
        ("value_date", "2026-09-12T15:30:00"),
        ("value_date", "2026-09-12T15:30:00+09:00"),
    ],
)
def test_typed_values_stored_without_normalization(context, field, value):
    changes = dict(value_number=None)
    changes[field] = value
    with transaction(context.connection):
        record = create(context, "characteristic_value", **changes)
    assert getattr(record, field) == value
    assert (
        sum(
            getattr(record, f) is not None
            for f in ("value_number", "value_integer", "value_text", "value_date")
        )
        == 1
    )
    assert record.original_value == " 4.24 " and record.unit_id == context.unit.unit_id
    assert record.original_unit == "syn" and record.source_row == 9
    assert record.quality_status == "UNREVIEWED" and record.source_type == "IMPORT"
    assert record.is_active and not record.is_representative


@pytest.mark.parametrize(
    "changes",
    [
        {"value_number": None},
        {"value_integer": 3},
        {"value_text": "Synthetic"},
        {"value_date": "2026-09-12"},
        {"value_number": None, "value_integer": 3, "value_text": "Synthetic"},
    ],
)
def test_exactly_one_db_constraint(context, changes):
    with transaction(context.connection), pytest.raises(ConstraintViolationError):
        create(context, "characteristic_value", **changes)
    assert count(context, "characteristic_value") == 0


@pytest.mark.parametrize(
    "table,column",
    [
        ("import_history", "source_file_id"),
        ("import_history", "created_by_user_id"),
        ("import_history", "dictionary_version_id"),
        ("import_history", "schema_version_id"),
        ("import_sheet", "import_id"),
        ("import_column_mapping", "import_sheet_id"),
        ("import_column_mapping", "dictionary_id"),
        ("import_column_mapping", "target_unit_id"),
        ("characteristic_value", "stream_code"),
        ("characteristic_value", "dictionary_id"),
        ("characteristic_value", "unit_id"),
        ("characteristic_value", "import_id"),
        ("characteristic_value", "import_sheet_id"),
        ("characteristic_value", "mapping_id"),
    ],
)
def test_foreign_keys_enforced_and_translated(context, table, column):
    assert context.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    before = count(context, table)
    missing = NEW_STREAM if column == "stream_code" else 999999
    with transaction(context.connection), pytest.raises(ForeignKeyReferenceError):
        create(context, table, **{column: missing})
    assert count(context, table) == before


@pytest.mark.parametrize(
    "table,column",
    [
        ("source_file", "file_name"),
        ("source_file", "original_path"),
        ("source_file", "registered_at"),
        ("import_history", "batch_code"),
        ("import_history", "started_at"),
        ("import_sheet", "sheet_name"),
        ("import_sheet", "status"),
        ("import_column_mapping", "mapping_method"),
        ("import_column_mapping", "mapping_status"),
        ("characteristic_value", "created_at"),
    ],
)
def test_not_null_errors_safe(context, table, column):
    with transaction(context.connection), pytest.raises(ConstraintViolationError):
        create(context, table, **{column: None})


def test_characteristic_query_and_full_provenance(context):
    repo = context.repos["characteristic_value"]
    assert repo.get_by_id(999999) is None and repo.get_provenance(999999) is None
    assert repo.list_by_import_id(999999) == [] and repo.count_by_import_id(999999) == 0
    with transaction(context.connection):
        record = create(context, "characteristic_value")
    assert repo.list_by_import_id(record.import_id) == [record]
    assert repo.count_by_import_id(record.import_id) == 1
    assert repo.list_by_stream_code(STREAM) == [record] and repo.count_by_stream_code(STREAM) == 1
    assert repo.count_by_import_sheet_id(record.import_sheet_id) == 1
    provenance = repo.get_provenance(record.characteristic_value_id)
    assert provenance.value == record
    assert provenance.mapping == context.records["import_column_mapping"]
    assert provenance.sheet == context.records["import_sheet"]
    assert provenance.history == context.records["import_history"]
    assert provenance.source_file == context.records["source_file"]


def test_nullable_provenance_not_inferred_and_cross_import_not_rewritten(context):
    repo = context.repos["characteristic_value"]
    with transaction(context.connection):
        manual = create(
            context,
            "characteristic_value",
            import_id=None,
            import_sheet_id=None,
            mapping_id=None,
            source_row=None,
            source_type="MANUAL",
        )
        other = create(context, "import_history")
        crossed = create(context, "characteristic_value", import_id=other.import_id)
    provenance = repo.get_provenance(manual.characteristic_value_id)
    assert (
        provenance.mapping
        is provenance.sheet
        is provenance.history
        is provenance.source_file
        is None
    )
    assert repo.get_by_id(crossed.characteristic_value_id).import_id == other.import_id
    assert (
        context.repos["import_column_mapping"].get_by_id(crossed.mapping_id)
        == context.records["import_column_mapping"]
    )


@pytest.mark.parametrize("table", REPOSITORIES)
def test_each_repository_requires_transaction_and_caller_rollback(context, table):
    before = count(context, table)
    with pytest.raises(TransactionRequiredError):
        create(context, table)
    assert count(context, table) == before
    context.connection.execute("BEGIN")
    create(context, table)
    assert context.connection.in_transaction
    assert count(context, table) == before + 1
    context.connection.rollback()
    assert count(context, table) == before


def create_shared(context):
    sheet = create(context, "import_sheet")
    mapping = create(context, "import_column_mapping", import_sheet_id=sheet.import_sheet_id)
    stream = create(context, "small_stream")
    value = create(
        context,
        "characteristic_value",
        stream_code=stream.stream_code,
        import_sheet_id=sheet.import_sheet_id,
        mapping_id=mapping.mapping_id,
    )
    return sheet, mapping, stream, value


@pytest.mark.parametrize("fail", [False, True])
def test_shared_transaction_atomicity_and_no_internal_boundary(context, fail):
    before = {table: count(context, table) for table in REPOSITORIES}
    boundaries = []

    def authorizer(action, *args):
        if action in (sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_SAVEPOINT):
            boundaries.append(args[0])
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    try:
        with transaction(context.connection):
            context.connection.set_authorizer(authorizer)
            try:
                create_shared(context)
                assert boundaries == []
                with closing(connect_database(context.path)) as observer:
                    assert (
                        observer.execute("SELECT count(*) FROM characteristic_value").fetchone()[0]
                        == 0
                    )
                if fail:
                    raise RuntimeError("Synthetic forced failure")
            finally:
                context.connection.set_authorizer(None)
    except RuntimeError as error:
        assert fail and str(error) == "Synthetic forced failure"
    for table in REPOSITORIES:
        delta = int(not fail and table not in ("source_file", "import_history"))
        assert count(context, table) == before[table] + delta
    assert not context.connection.in_transaction


def test_status_update_rollback_and_no_recovery(context):
    repo = context.repos["import_history"]
    before = context.records["import_history"]
    context.connection.execute("BEGIN")
    repo.update_status(before.import_id, "SUCCESS", finished_at=LATER)
    context.connection.rollback()
    assert repo.get_by_batch_code(before.batch_code) == before
    assert repo.list_by_status("RUNNING") == [before]
    assert repo.count_by_status("RUNNING") == 1


def test_prepared_objects_transferred_without_changes(context):
    timestamp = utc_now_text()
    prepared_stream = PreparedStreamData(
        NEW_STREAM,
        "12",
        "345",
        "678",
        "008",
        "Synthetic Prepared Stream",
        (("source_latitude", 45.0), ("province_name", "Synthetic P")),
    )
    prepared_value = PreparedCharacteristicValue(
        context.item.dictionary_id,
        "REAL",
        1,
        7,
        value_number=4.24,
        original_value=" 4.24 ",
        original_unit="syn",
        unit_id=context.unit.unit_id,
    )
    before = (asdict(prepared_stream), asdict(prepared_value))
    with transaction(context.connection):
        stream = context.repos["small_stream"].create_prepared(prepared_stream, timestamp=timestamp)
        value = context.repos["characteristic_value"].create_prepared(
            prepared_value,
            stream_code=stream.stream_code,
            timestamp=timestamp,
            import_id=context.records["import_history"].import_id,
            import_sheet_id=context.records["import_sheet"].import_sheet_id,
            mapping_id=context.records["import_column_mapping"].mapping_id,
            reference_year=2026,
        )
    assert stream.source_latitude == 45.0 and stream.end_latitude is None
    assert stream.created_at == timestamp and stream.updated_at == timestamp
    assert value.value_number == 4.24 and value.source_row == 7 and value.original_value == " 4.24 "
    assert value.original_unit == "syn" and value.unit_id == context.unit.unit_id
    assert not value.is_representative and value.is_active and value.quality_status == "UNREVIEWED"
    assert before == (asdict(prepared_stream), asdict(prepared_value))


def test_no_current_use_qc_or_history_side_effects(context):
    with transaction(context.connection):
        old = create(context, "characteristic_value", is_representative=True)
        context.connection.execute(
            "INSERT INTO stream_characteristic VALUES (?,?,?,?)",
            (STREAM, context.item.dictionary_id, old.characteristic_value_id, STAMP),
        )
    cache = context.connection.execute("SELECT * FROM stream_characteristic").fetchall()
    with transaction(context.connection):
        new = create(context, "characteristic_value")
    assert not new.is_representative
    assert context.repos["characteristic_value"].get_by_id(old.characteristic_value_id) == old
    assert context.connection.execute("SELECT * FROM stream_characteristic").fetchall() == cache
    assert count(context, "data_quality_issue") == 0 and count(context, "record_history") == 0


def test_repr_and_exception_do_not_leak(context, caplog):
    records = []
    with transaction(context.connection):
        for table in REPOSITORIES:
            records.append(create(context, table))
        with pytest.raises(ConstraintViolationError) as caught:
            create(context, "source_file", file_name=None, original_path=SYNTHETIC_PATH)
    output = (
        repr(records)
        + str(caught.value)
        + "".join(traceback.format_exception(caught.value))
        + caplog.text
    )
    for marker in (
        SYNTHETIC_PATH,
        "SYNTHETIC_PRIVATE_SETTING",
        "SYNTHETIC_PRIVATE_DIAGNOSTIC",
        " 4.24 ",
        "Synthetic Stream B",
        "Synthetic Header",
    ):
        assert marker not in output
    assert caught.value.__suppress_context__
    assert "NOT NULL constraint failed" not in output


def test_sqlite_read_write_errors_are_sanitized(context):
    context.connection.set_authorizer(lambda *_: sqlite3.SQLITE_DENY)
    try:
        with pytest.raises(PersistenceError, match="저장소에 접근"):
            context.repos["source_file"].get_by_id(1)
    finally:
        context.connection.set_authorizer(None)
    with transaction(context.connection):
        context.connection.set_authorizer(lambda *_: sqlite3.SQLITE_DENY)
        try:
            with pytest.raises(PersistenceError, match="저장소에 접근"):
                create(context, "source_file")
        finally:
            context.connection.set_authorizer(None)


def test_bound_values_and_column_whitelist(context):
    payload = "Synthetic '); DROP TABLE source_file; --"
    with transaction(context.connection):
        record = create(context, "source_file", file_name=payload)
        assert record.file_name == payload
        with pytest.raises(InvalidPersistenceArgumentError):
            create(context, "source_file", **{"unsafe); DROP TABLE source_file; --": "synthetic"})
        with pytest.raises(InvalidPersistenceArgumentError):
            create(context, "source_file", source_file_id=999999)
    assert context.repos["source_file"].get_by_id(record.source_file_id) == record


def test_no_delete_or_upsert_public_api(context):
    for repo in context.repos.values():
        assert not any(name.startswith(("delete", "upsert", "replace")) for name in dir(repo))


def test_committed_shared_rows_visible_from_another_connection(context):
    with transaction(context.connection):
        sheet, mapping, stream, value = create_shared(context)
    with closing(connect_database(context.path)) as observer:
        assert ImportSheetRepository(observer).get_by_id(sheet.import_sheet_id) == sheet
        assert ImportColumnMappingRepository(observer).get_by_id(mapping.mapping_id) == mapping
        assert SmallStreamRepository(observer).get_by_stream_code(stream.stream_code) == stream
        assert (
            CharacteristicValueRepository(observer).get_by_id(value.characteristic_value_id)
            == value
        )


def test_unit_conversion_is_never_applied(context):
    other = context.dictionary.create_unit("Synthetic Other Unit", "other")
    context.dictionary.register_conversion(
        context.unit.unit_id, other.unit_id, 1000, offset=7, approved=True
    )
    with transaction(context.connection):
        result = create(context, "characteristic_value", unit_id=other.unit_id, original_unit="syn")
    assert result.value_number == 4.24 and result.unit_id == other.unit_id
    assert result.original_unit == "syn"


@pytest.mark.parametrize(
    "table,column,value",
    [
        ("source_file", "is_active", 2),
        ("import_history", "status", "SYNTHETIC_INVALID"),
        ("import_sheet", "status", "PENDING"),
        ("import_column_mapping", "user_confirmed", 2),
        ("characteristic_value", "is_representative", 2),
        ("characteristic_value", "is_active", 2),
    ],
)
def test_closed_checks_enforced_on_create(context, table, column, value):
    with transaction(context.connection), pytest.raises(ConstraintViolationError):
        create(context, table, **{column: value})


def test_closed_connection_and_bad_bound_values_do_not_leak(context):
    with transaction(context.connection):
        for value in (2**100, "\ud800"):
            with pytest.raises(InvalidPersistenceArgumentError):
                create(context, "source_file", file_size=value)
        with pytest.raises(PersistenceError):
            create(context, "source_file", file_name=object())
    context.connection.close()
    with pytest.raises(PersistenceError, match="저장소에 접근"):
        context.repos["source_file"].get_by_id(1)
