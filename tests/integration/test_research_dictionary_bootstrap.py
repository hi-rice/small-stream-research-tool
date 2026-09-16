"""합성 DB에서 Phase 9C-0 연구 사전 bootstrap 계약을 검증한다."""

import copy
from contextlib import closing

import pytest

from small_stream_research_tool.database import connect_database, initialize_database
from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.services.research_dictionary_bootstrap import (
    ResearchDictionaryBootstrapService,
    ResearchDictionaryError,
    load_research_manifest,
    manifest_fingerprint,
    validate_research_manifest,
)


@pytest.fixture
def context(tmp_path):
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as connection:
        yield connection, ResearchDictionaryBootstrapService(connection)


def counts(connection):
    return {
        table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in (
            "data_category",
            "dictionary_version",
            "unit_dictionary",
            "unit_conversion",
            "data_dictionary",
            "column_alias",
            "quality_rule",
            "characteristic_value",
            "stream_characteristic",
            "record_history",
        )
    }


def changed(manifest, internal_name, **updates):
    result = copy.deepcopy(manifest)
    item = next(row for row in result["items"] if row["internal_name"] == internal_name)
    item.update(updates)
    return result


def test_fresh_bootstrap_manifest_shape_and_idempotency(context):
    connection, service = context
    manifest = load_research_manifest()
    first = service.bootstrap()
    state = counts(connection)
    second = service.bootstrap()
    assert first == second
    assert first.manifest_version == "research-dictionary-v1"
    assert first.fingerprint == manifest_fingerprint(manifest)
    assert (first.category_count, first.unit_count, first.item_count, first.alias_count) == (
        5,
        6,
        70,
        70,
    )
    assert state == counts(connection)
    assert counts(connection) == {
        "data_category": 5,
        "dictionary_version": 1,
        "unit_dictionary": 6,
        "unit_conversion": 0,
        "data_dictionary": 70,
        "column_alias": 70,
        "quality_rule": 0,
        "characteristic_value": 0,
        "stream_characteristic": 0,
        "record_history": 0,
    }
    version = connection.execute(
        "SELECT version,description,is_current FROM dictionary_version"
    ).fetchone()
    assert version == (
        "research-dictionary-v1",
        "research-manifest-sha256:" + first.fingerprint,
        1,
    )


def test_manifest_leaf_groups_types_units_categories_and_aliases(context):
    connection, service = context
    service.bootstrap()
    rows = connection.execute(
        "SELECT d.internal_name,d.data_type,u.unit_symbol,c.category_key,d.analyzable,"
        "a.alias_name,a.source_scope FROM data_dictionary d "
        "JOIN data_category c ON c.category_id=d.category_id "
        "LEFT JOIN unit_dictionary u ON u.unit_id=d.unit_id "
        "JOIN column_alias a ON a.dictionary_id=d.dictionary_id"
    ).fetchall()
    by_name = {row[0]: row[1:] for row in rows}
    assert by_name["stream_length_total"] == (
        "REAL",
        "km",
        "basic_characteristic",
        1,
        "소하천연장 | 전체",
        "NATIONAL_2024",
    )
    assert by_name["soil_group_d_area"][1:3] == ("km²", "soil_characteristic")
    assert by_name["cn_amc_iii"][0:2] == ("REAL", None)
    assert by_name["stream_order"][0::3] == ("INTEGER", 0)
    assert by_name["source_plan_frequency"][0::3] == ("INTEGER", 0)
    assert by_name["end_plan_flood_discharge"][1:3] == ("m³/s", "planning_design")
    assert sum(name.startswith("land_use_") for name in by_name) == 32
    assert sum(name.startswith("source_") for name in by_name) == 4
    assert sum(name.startswith("end_") for name in by_name) == 4
    assert all(row[5] == "NATIONAL_2024" for row in by_name.values())
    assert all(
        row[4] not in {"A", "B", "C", "D", "전체", "빈도", "하폭"} for row in by_name.values()
    )


def test_approved_display_policy_resolves_ids_and_is_deny_by_default(context):
    connection, service = context
    assert service.approved_display_policy().allowed_dictionary_ids == frozenset()
    service.bootstrap()
    policy = service.approved_display_policy()
    expected = {
        row[0]
        for row in connection.execute(
            "SELECT dictionary_id FROM data_dictionary WHERE is_active=1 "
            "AND deprecated_version_id IS NULL"
        )
    }
    assert policy.allowed_dictionary_ids == expected
    assert not policy.show_source_file_name and not policy.show_sheet_name
    names = {
        row[0]
        for row in connection.execute(
            "SELECT internal_name FROM data_dictionary WHERE dictionary_id IN ("
            + ",".join("?" for _ in policy.allowed_dictionary_ids)
            + ")",
            tuple(policy.allowed_dictionary_ids),
        )
    }
    forbidden = ("service_key", "cctv", "rtsp", "password", "contact", "phone", "_ip")
    assert all(not any(term in name for term in forbidden) for name in names)


@pytest.mark.parametrize("conflict", ["data_type", "unit", "category"])
def test_existing_item_semantic_conflict_rolls_back(context, conflict):
    connection, service = context
    service.bootstrap()
    if conflict == "data_type":
        connection.execute(
            "UPDATE data_dictionary SET data_type='TEXT' WHERE internal_name='basin_area'"
        )
    elif conflict == "unit":
        connection.execute(
            "UPDATE data_dictionary SET unit_id=(SELECT unit_id FROM unit_dictionary "
            "WHERE unit_symbol='m') WHERE internal_name='basin_area'"
        )
    else:
        connection.execute(
            "UPDATE data_dictionary SET category_id=(SELECT category_id FROM data_category "
            "WHERE category_key='land_use') WHERE internal_name='basin_area'"
        )
    before = counts(connection)
    with pytest.raises(ResearchDictionaryError):
        service.bootstrap()
    assert counts(connection) == before and not connection.in_transaction


def test_identical_preexisting_definitions_are_reused(context):
    connection, service = context
    service.bootstrap()
    item_ids = tuple(connection.execute("SELECT dictionary_id FROM data_dictionary ORDER BY 1"))
    service.bootstrap()
    assert (
        tuple(connection.execute("SELECT dictionary_id FROM data_dictionary ORDER BY 1"))
        == item_ids
    )


def test_alias_conflict_and_partial_failure_rollback(context):
    connection, service = context
    manifest = load_research_manifest()
    with transaction(connection):
        repository = DictionaryRepository(connection)
        version = repository.create_version(
            version="synthetic-prior", description=None, created_at="2026-09-16T00:00:00Z"
        )
        category = repository.create_category(
            category_key="synthetic",
            category_name="Synthetic",
            parent_category_id=None,
            sort_order=0,
            is_active=True,
            created_at="2026-09-16T00:00:00Z",
            updated_at="2026-09-16T00:00:00Z",
        )
        item = repository.create_item(
            standard_name="Synthetic",
            internal_name="synthetic_other",
            category_id=category.category_id,
            data_type="REAL",
            unit_id=None,
            description=None,
            storage_type="FLEX",
            analyzable=True,
            required=False,
            nullable=True,
            created_version_id=version.version_id,
            deprecated_version_id=None,
            is_active=True,
            created_at="2026-09-16T00:00:00Z",
            updated_at="2026-09-16T00:00:00Z",
        )
        repository.create_alias(
            dictionary_id=item.dictionary_id,
            alias_name="소하천연장 | 전체",
            normalized_alias="소하천연장 | 전체",
            source_scope="NATIONAL_2024",
            is_active=True,
            created_at="2026-09-16T00:00:00Z",
            updated_at="2026-09-16T00:00:00Z",
        )
    before = counts(connection)
    with pytest.raises(ResearchDictionaryError):
        service.bootstrap(manifest)
    assert counts(connection) == before
    assert connection.execute(
        "SELECT count(*) FROM data_category WHERE category_key='basic_characteristic'"
    ).fetchone() == (0,)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m.pop("units"),
        lambda m: m["items"].append(copy.deepcopy(m["items"][0])),
        lambda m: m["items"][1]["aliases"].__setitem__(
            0, copy.deepcopy(m["items"][0]["aliases"][0])
        ),
        lambda m: m["items"][0].__setitem__("unit_symbol", "unknown"),
        lambda m: m["items"][0]["aliases"][0].__setitem__("name", "전체"),
        lambda m: m["items"][0].__setitem__("internal_name", "service_key"),
    ],
)
def test_malformed_duplicate_ambiguous_unknown_and_sensitive_manifest_rejected(mutate):
    manifest = copy.deepcopy(load_research_manifest())
    mutate(manifest)
    with pytest.raises(ResearchDictionaryError):
        validate_research_manifest(manifest)


def test_fingerprint_is_deterministic_and_semantic(context):
    _connection, service = context
    manifest = load_research_manifest()
    reordered = {key: manifest[key] for key in reversed(tuple(manifest))}
    assert manifest_fingerprint(manifest) == manifest_fingerprint(reordered)
    changed_manifest = changed(manifest, "basin_area", standard_name="유역 면적")
    assert manifest_fingerprint(manifest) != manifest_fingerprint(changed_manifest)
    service.bootstrap()
    with pytest.raises(ResearchDictionaryError):
        service.bootstrap(changed_manifest)
