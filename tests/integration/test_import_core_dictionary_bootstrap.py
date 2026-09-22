"""Import core 사전의 분리·충돌·연구 표시 경계를 검증한다."""

from contextlib import closing

import pytest

from small_stream_research_tool.database import connect_database, initialize_database
from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.services.import_core_dictionary_bootstrap import (
    ImportCoreDictionaryBootstrapService,
    ImportCoreDictionaryError,
    import_core_fingerprint,
    load_import_core_manifest,
)
from small_stream_research_tool.services.research_dictionary_bootstrap import (
    ResearchDictionaryBootstrapService,
    ResearchDictionaryError,
    load_research_manifest,
    manifest_fingerprint,
)

EXPECTED = {
    "stream_code": ("소하천 관리코드", "IDENTITY", "관리코드"),
    "province_code": ("시·도 코드", "IDENTITY", "시도코드"),
    "city_county_code": ("시·군·구 코드", "IDENTITY", "시군구코드"),
    "town_code": ("읍·면·동 코드", "IDENTITY", "읍면동코드"),
    "stream_serial_no": ("소하천 일련번호", "IDENTITY", "일련번호"),
    "stream_name": ("소하천명", "STREAM_MASTER", "소하천명"),
}


def _counts(connection):
    return tuple(
        connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in ("dictionary_version", "data_category", "data_dictionary", "column_alias")
    )


def test_core_definition_is_exact_idempotent_and_separate(tmp_path):
    path = tmp_path / "research.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as connection:
        research = ResearchDictionaryBootstrapService(connection)
        research_result = research.bootstrap()
        state = _counts(connection)
        core = ImportCoreDictionaryBootstrapService(connection)
        first = core.bootstrap()
        second = core.bootstrap()
        assert first == second
        assert state == _counts(connection) == (2, 6, 76, 76)
        assert first.fingerprint == import_core_fingerprint(load_import_core_manifest())
        assert (first.item_count, first.alias_count) == (6, 6)

        rows = connection.execute(
            "SELECT d.internal_name,d.standard_name,d.data_type,d.storage_type,d.analyzable,"
            "d.required,d.nullable,d.unit_id,d.description,c.category_key,a.alias_name,"
            "a.source_scope FROM data_dictionary d "
            "JOIN data_category c ON c.category_id=d.category_id "
            "JOIN column_alias a ON a.dictionary_id=d.dictionary_id "
            "WHERE d.storage_type='CORE' ORDER BY d.internal_name"
        ).fetchall()
        assert len(rows) == 6
        for row in rows:
            name, standard, data_type, storage, analyzable, required, nullable, unit_id = row[:8]
            description, category, alias, scope = row[8:]
            expected_standard, role, expected_alias = EXPECTED[name]
            assert (standard, data_type, storage, analyzable, required, nullable, unit_id) == (
                expected_standard,
                "TEXT",
                "CORE",
                0,
                0,
                1,
                None,
            )
            assert (description, category, alias, scope) == (
                "Import " + role,
                "import_core",
                expected_alias,
                "NATIONAL_2024",
            )

        policy = research.approved_display_policy()
        assert len(policy.allowed_dictionary_ids) == 70
        assert research_result.fingerprint == manifest_fingerprint(load_research_manifest())
        assert connection.execute(
            "SELECT version FROM dictionary_version WHERE is_current=1"
        ).fetchone() == ("research-dictionary-v1",)


@pytest.mark.parametrize("conflict", ["type", "category", "unit", "metadata", "version"])
def test_core_definition_conflict_rolls_back(tmp_path, conflict):
    path = tmp_path / "research.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as connection:
        ResearchDictionaryBootstrapService(connection).bootstrap()
        if conflict == "type":
            connection.execute(
                "UPDATE data_dictionary SET data_type='INTEGER' WHERE internal_name='stream_code'"
            )
        elif conflict == "category":
            connection.execute(
                "UPDATE data_dictionary SET category_id=(SELECT category_id FROM data_category "
                "WHERE category_key='basic_characteristic') WHERE internal_name='stream_code'"
            )
        elif conflict == "unit":
            connection.execute(
                "UPDATE data_dictionary SET unit_id=(SELECT unit_id FROM unit_dictionary "
                "WHERE unit_symbol='m') WHERE internal_name='stream_code'"
            )
        elif conflict == "metadata":
            connection.execute(
                "UPDATE data_dictionary SET description='changed' WHERE internal_name='stream_code'"
            )
        else:
            connection.execute(
                "UPDATE dictionary_version SET description='changed' "
                "WHERE version='import-core-dictionary-v1'"
            )
        before = _counts(connection)
        with pytest.raises(ImportCoreDictionaryError):
            ImportCoreDictionaryBootstrapService(connection).bootstrap()
        assert _counts(connection) == before
        assert not connection.in_transaction


def test_existing_research_only_database_adds_core_without_rewriting_ids(tmp_path, monkeypatch):
    path = tmp_path / "research.sqlite3"
    initialize_database(path)
    original = ImportCoreDictionaryBootstrapService.bootstrap
    with closing(connect_database(path)) as connection:
        monkeypatch.setattr(ImportCoreDictionaryBootstrapService, "bootstrap", lambda self: None)
        ResearchDictionaryBootstrapService(connection).bootstrap()
        research_ids = tuple(
            connection.execute(
                "SELECT dictionary_id,internal_name FROM data_dictionary ORDER BY dictionary_id"
            )
        )
        assert len(research_ids) == 70
        monkeypatch.setattr(ImportCoreDictionaryBootstrapService, "bootstrap", original)
        ResearchDictionaryBootstrapService(connection).bootstrap()
        assert (
            tuple(
                connection.execute(
                    "SELECT dictionary_id,internal_name FROM data_dictionary "
                    "WHERE storage_type='FLEX' ORDER BY dictionary_id"
                )
            )
            == research_ids
        )
        assert connection.execute(
            "SELECT count(*) FROM data_dictionary WHERE storage_type='CORE'"
        ).fetchone() == (6,)
        assert connection.execute("SELECT count(*) FROM record_history").fetchone() == (0,)


def test_core_failure_rolls_back_research_and_core_as_one_bootstrap(tmp_path):
    path = tmp_path / "research.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as connection:
        repository = DictionaryRepository(connection)
        with transaction(connection):
            version = repository.create_version(
                version="prior-v1", description=None, created_at="2026-09-23T00:00:00Z"
            )
            category = repository.create_category(
                category_key="prior",
                category_name="Prior",
                parent_category_id=None,
                sort_order=99,
                is_active=True,
                created_at="2026-09-23T00:00:00Z",
                updated_at="2026-09-23T00:00:00Z",
            )
            item = repository.create_item(
                standard_name="Prior",
                internal_name="prior_item",
                category_id=category.category_id,
                data_type="TEXT",
                unit_id=None,
                description=None,
                storage_type="FLEX",
                analyzable=False,
                required=False,
                nullable=True,
                created_version_id=version.version_id,
                deprecated_version_id=None,
                is_active=True,
                created_at="2026-09-23T00:00:00Z",
                updated_at="2026-09-23T00:00:00Z",
            )
            repository.create_alias(
                dictionary_id=item.dictionary_id,
                alias_name="관리코드",
                normalized_alias="관리코드",
                source_scope="NATIONAL_2024",
                is_active=True,
                created_at="2026-09-23T00:00:00Z",
                updated_at="2026-09-23T00:00:00Z",
            )
        before = _counts(connection)
        with pytest.raises(ResearchDictionaryError):
            ResearchDictionaryBootstrapService(connection).bootstrap()
        assert _counts(connection) == before
        assert connection.execute(
            "SELECT count(*) FROM data_dictionary WHERE internal_name='basin_area'"
        ).fetchone() == (0,)
        assert not connection.in_transaction


def test_core_alias_conflict_rolls_back(tmp_path):
    path = tmp_path / "research.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as connection:
        ResearchDictionaryBootstrapService(connection).bootstrap()
        other = connection.execute(
            "SELECT dictionary_id FROM data_dictionary WHERE internal_name='basin_area'"
        ).fetchone()[0]
        connection.execute(
            "UPDATE column_alias SET dictionary_id=? WHERE alias_name='관리코드'",
            (other,),
        )
        before = _counts(connection)
        with pytest.raises(ImportCoreDictionaryError):
            ImportCoreDictionaryBootstrapService(connection).bootstrap()
        assert _counts(connection) == before
        assert not connection.in_transaction
