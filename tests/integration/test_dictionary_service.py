"""6개 사전 테이블 기반을 임시 SQLite와 synthetic 값으로 검증한다."""

from contextlib import closing
from datetime import datetime, timedelta

import pytest

from small_stream_research_tool.database import connect_database, initialize_database
from small_stream_research_tool.models.dictionary import DataCategory
from small_stream_research_tool.models.dictionary_errors import (
    DictionaryEntryNotFoundError,
    DictionaryItemInUseError,
    DuplicateAliasError,
    DuplicateDefinitionError,
    InvalidDictionaryDefinitionError,
    UnitConversionError,
)
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.services.dictionary_service import DictionaryService

STAMP = "2026-01-01T00:00:00Z"


@pytest.fixture
def context(tmp_path):
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as connection:
        repository = DictionaryRepository(connection)
        yield connection, repository, DictionaryService(repository)


def foundation(service):
    category = service.create_category("TEST_CATEGORY", "가상 분류")
    version = service.create_version("synthetic-v1", make_current=True)
    unit = service.create_unit("가상 단위", "test-unit", dimension="synthetic")
    item = service.create_item(
        "가상 항목",
        "test_item",
        category.category_id,
        "REAL",
        version.version_id,
        unit_id=unit.unit_id,
    )
    return category, version, unit, item


def test_no_seed_or_schema_changes(context):
    connection, _, service = context
    assert service.list_categories() == [] and service.list_units() == []
    assert service.list_versions() == [] and service.get_current_version() is None
    assert service.list_items() == []
    assert connection.execute(
        "SELECT COUNT(*) FROM sqlite_schema WHERE type='table'"
    ).fetchone() == (19,)
    assert connection.execute("SELECT version FROM schema_version").fetchall() == [("001",)]


def test_category_create_find_duplicate_and_deactivate(context):
    connection, _, service = context
    parent = service.create_category(" TEST ", "가상 부모", sort_order=2)
    child = service.create_category(
        "CHILD", "가상 자식", parent_category_id=parent.category_id, sort_order=1
    )
    assert isinstance(parent, DataCategory)
    assert service.get_category(parent.category_id).category_key == "TEST"
    assert service.list_categories() == [child, parent]
    with pytest.raises(DuplicateDefinitionError):
        service.create_category("TEST", "중복")
    service.deactivate_category(parent.category_id)
    assert service.list_categories() == [child]
    assert len(service.list_categories(active_only=False)) == 2
    assert service.get_category(child.category_id).parent_category_id == parent.category_id
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_versions_current_and_relationships(context):
    _, _, service = context
    _, version, _, item = foundation(service)
    second = service.create_version("synthetic-v2")
    assert service.get_current_version() == version
    service.set_current_version(second.version_id)
    assert service.get_current_version().version_id == second.version_id
    assert not service.get_version(version.version_id).is_current
    assert service.get_item(item.dictionary_id).created_version_id == version.version_id
    assert len(service.list_versions()) == 2
    with pytest.raises(DuplicateDefinitionError):
        service.create_version("synthetic-v2", make_current=True)
    with pytest.raises(DictionaryEntryNotFoundError):
        service.set_current_version(999)
    assert service.get_current_version().version_id == second.version_id


def test_units_unique_and_deactivate(context):
    _, _, service = context
    unit = service.create_unit("가상", "unit²")
    assert service.get_unit(unit.unit_id) == unit and unit.dimension is None
    with pytest.raises(DuplicateDefinitionError):
        service.create_unit("다른 표시", "unit²")
    service.deactivate_unit(unit.unit_id)
    assert service.list_units() == []
    assert len(service.list_units(active_only=False)) == 1


def test_explicit_conversion_factor_offset_and_direction(context):
    _, _, service = context
    source = service.create_unit("synthetic source", "test-a")
    target = service.create_unit("synthetic target", "test-b")
    args = (source.unit_id, target.unit_id)
    with pytest.raises(UnitConversionError):
        service.register_conversion(*args, 2)
    rule = service.register_conversion(*args, 2, offset=3, approved=True)
    assert rule.formula_type == "LINEAR"
    assert service.get_conversion(*args) == rule
    assert service.convert_value(4, *args) == 11
    with pytest.raises(DuplicateDefinitionError):
        service.register_conversion(*args, 2, approved=True)
    with pytest.raises(UnitConversionError):
        service.convert_value(4, target.unit_id, source.unit_id)
    with pytest.raises(UnitConversionError):
        service.convert_value(4, source.unit_id, source.unit_id)
    service.deactivate_unit(target.unit_id)
    with pytest.raises(UnitConversionError):
        service.convert_value(4, *args)


@pytest.mark.parametrize(
    "factor,offset,formula",
    [
        (float("nan"), 0, "LINEAR"),
        (float("inf"), 0, "LINEAR"),
        (1, float("inf"), "LINEAR"),
        ("2", 0, "LINEAR"),
        (True, 0, "LINEAR"),
        (2, 0, "CUSTOM"),
    ],
)
def test_invalid_conversion_definition(context, factor, offset, formula):
    _, _, service = context
    a = service.create_unit("a", "test-a")
    b = service.create_unit("b", "test-b")
    with pytest.raises(UnitConversionError):
        service.register_conversion(
            a.unit_id, b.unit_id, factor, offset=offset, formula_type=formula, approved=True
        )
    assert service.get_conversion(a.unit_id, b.unit_id) is None


def test_conversion_overflow_and_inactive_rule(context):
    connection, _, service = context
    a = service.create_unit("a", "test-a")
    b = service.create_unit("b", "test-b")
    rule = service.register_conversion(a.unit_id, b.unit_id, 1e308, approved=True)
    with pytest.raises(UnitConversionError):
        service.convert_value(1e308, a.unit_id, b.unit_id)
    connection.execute(
        "UPDATE unit_conversion SET is_active=0 WHERE conversion_id=?", (rule.conversion_id,)
    )
    with pytest.raises(UnitConversionError):
        service.convert_value(1, a.unit_id, b.unit_id)


def test_item_queries_flags_and_duplicate(context):
    _, _, service = context
    category, version, unit, item = foundation(service)
    other = service.create_item(
        "가상 항목", "other", category.category_id, "TEXT", version.version_id, analyzable=False
    )
    assert service.get_item_by_internal_name(" test_item ") == item
    assert item.category_id == category.category_id and item.unit_id == unit.unit_id
    assert service.list_items(standard_name="가상 항목") == [item, other]
    assert service.list_items(category_id=category.category_id) == [item, other]
    assert service.list_items(analyzable_only=True) == [item]
    with pytest.raises(DuplicateDefinitionError):
        service.create_item("중복", "test_item", category.category_id, "REAL", version.version_id)
    service.deactivate_item(item.dictionary_id)
    assert service.list_items() == [other]
    assert len(service.list_items(active_only=False)) == 2
    assert not service.get_item(item.dictionary_id).is_active


@pytest.mark.parametrize("data_type", ["REAL", "INTEGER", "TEXT", "DATE", "DATETIME"])
def test_supported_types(context, data_type):
    _, _, service = context
    category = service.create_category("test", "가상")
    version = service.create_version("test-v1")
    item = service.create_item(
        "가상", "synthetic", category.category_id, data_type, version.version_id
    )
    assert item.data_type == data_type


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"category_id": 999}, DictionaryEntryNotFoundError),
        ({"unit_id": 999}, DictionaryEntryNotFoundError),
        ({"created_version_id": 999}, DictionaryEntryNotFoundError),
        ({"data_type": "NUMBER"}, InvalidDictionaryDefinitionError),
        ({"internal_name": " "}, InvalidDictionaryDefinitionError),
        ({"storage_type": "OTHER"}, InvalidDictionaryDefinitionError),
        ({"analyzable": 2}, InvalidDictionaryDefinitionError),
    ],
)
def test_bad_definition_rejected(context, overrides, error):
    _, _, service = context
    category, version, _, _ = foundation(service)
    values = dict(
        standard_name="가상",
        internal_name="new",
        category_id=category.category_id,
        data_type="REAL",
        created_version_id=version.version_id,
    )
    with pytest.raises(error):
        service.create_item(**(values | overrides))
    assert len(service.list_items()) == 1


def test_alias_normalization_collision_and_scopes(context):
    _, _, service = context
    category, version, _, item = foundation(service)
    other = service.create_item(
        "다른 가상 항목", "other", category.category_id, "REAL", version.version_id
    )
    global_alias = service.register_alias(item.dictionary_id, " TEST  AREA ")
    local_alias = service.register_alias(other.dictionary_id, "test area", source_scope="series-a")
    assert service.get_alias(global_alias.alias_id).alias_name == " TEST  AREA "
    assert global_alias.source_scope == "GLOBAL"
    assert service.get_alias(local_alias.alias_id).normalized_alias == "test area"
    with pytest.raises(DuplicateAliasError):
        service.register_alias(other.dictionary_id, "Test\tArea")
    assert service.find_dictionary_by_header("TEST AREA", "series-a") == other
    assert service.find_dictionary_by_header("TEST AREA", "series-b") == item
    assert service.find_dictionary_by_header("TEST AREA") == item
    assert service.find_dictionary_by_header("testarea") is None
    assert service.find_dictionary_by_header("area") is None
    service.deactivate_alias(local_alias.alias_id)
    assert service.find_dictionary_by_header("test area", "series-a") is None
    assert service.find_dictionary_by_header("test area", "series-b") == item
    with pytest.raises(DuplicateAliasError):
        service.register_alias(item.dictionary_id, "test area", source_scope="series-a")


@pytest.mark.parametrize("target", ["alias", "item", "category", "unit", "deprecated"])
def test_lookup_excludes_unusable_definitions(context, target):
    _, _, service = context
    category, version, unit, item = foundation(service)
    alias = service.register_alias(item.dictionary_id, "synthetic")
    operations = {
        "alias": lambda: service.deactivate_alias(alias.alias_id),
        "item": lambda: service.deactivate_item(item.dictionary_id),
        "category": lambda: service.deactivate_category(category.category_id),
        "unit": lambda: service.deactivate_unit(unit.unit_id),
        "deprecated": lambda: service.deprecate_item(item.dictionary_id, version.version_id),
    }
    operations[target]()
    assert service.find_dictionary_by_header("synthetic") is None
    assert service.get_item(item.dictionary_id) is not None


def test_used_item_semantics_and_deprecation_preserve_values(context):
    connection, _, service = context
    category, version, unit, item = foundation(service)
    connection.execute(
        "INSERT INTO small_stream(stream_code,province_code,city_county_code,town_code,"
        "stream_serial_no,stream_name,created_at,updated_at) "
        "VALUES ('01002003004','01','002','003',"
        "'004','synthetic',?,?)",
        (STAMP, STAMP),
    )
    connection.execute(
        "INSERT INTO characteristic_value(stream_code,dictionary_id,value_number,"
        "created_at,updated_at,is_active) VALUES ('01002003004',?,7,?,?,0)",
        (item.dictionary_id, STAMP, STAMP),
    )
    changes = [
        {"data_type": "INTEGER"},
        {"unit_id": None},
        {"standard_name": "다른 의미"},
        {"internal_name": "reused"},
        {"description": "다른 의미"},
        {"storage_type": "CORE"},
    ]
    for change in changes:
        with pytest.raises(DictionaryItemInUseError):
            service.update_item_definition(item.dictionary_id, **change)
    assert service.get_item(item.dictionary_id) == item
    assert service.update_item_definition(item.dictionary_id, data_type="REAL") == item
    second = service.create_version("synthetic-v2", make_current=True)
    deprecated = service.deprecate_item(item.dictionary_id, second.version_id)
    assert deprecated.created_version_id == version.version_id
    assert deprecated.deprecated_version_id == second.version_id and not deprecated.is_active
    assert service.deprecate_item(item.dictionary_id, second.version_id) == deprecated
    with pytest.raises(InvalidDictionaryDefinitionError):
        service.deprecate_item(item.dictionary_id, version.version_id)
    assert connection.execute("SELECT value_number FROM characteristic_value").fetchone() == (7,)
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_unused_definition_update_and_duplicate_guard(context):
    _, _, service = context
    category, version, _, item = foundation(service)
    service.create_item("other", "other", category.category_id, "TEXT", version.version_id)
    changed = service.update_item_definition(
        item.dictionary_id, data_type="INTEGER", description="synthetic"
    )
    assert changed.data_type == "INTEGER" and changed.description == "synthetic"
    with pytest.raises(DuplicateDefinitionError):
        service.update_item_definition(item.dictionary_id, internal_name="other")
    assert service.get_item(item.dictionary_id) == changed


@pytest.mark.parametrize("operation", ["version", "deprecate", "alias", "deactivate"])
def test_service_write_failure_rolls_back(context, monkeypatch, operation):
    connection, repository, service = context
    category, version, _, item = foundation(service)
    before = list(connection.iterdump())
    method = {
        "version": "set_current_version",
        "deprecate": "deprecate_item",
        "alias": "create_alias",
        "deactivate": "deactivate",
    }[operation]
    original = getattr(repository, method)

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(repository, method, fail)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        if operation == "version":
            service.create_version("next", make_current=True)
        elif operation == "deprecate":
            service.deprecate_item(item.dictionary_id, version.version_id)
        elif operation == "alias":
            service.register_alias(item.dictionary_id, "synthetic")
        else:
            service.deactivate_category(category.category_id)
    assert list(connection.iterdump()) == before
    assert not connection.in_transaction


def test_repository_no_delete_and_requires_transaction(context):
    _, repository, service = context
    category = service.create_category("synthetic", "가상")
    assert not hasattr(repository, "delete") and not hasattr(repository, "delete_item")
    with pytest.raises(RuntimeError, match="explicit transaction"):
        repository.deactivate(DataCategory, category.category_id, STAMP)
    assert service.get_category(category.category_id).is_active
    assert datetime.fromisoformat(category.created_at).utcoffset() == timedelta(0)
    assert category.created_at.endswith("Z")


def test_parameterized_lookup(context):
    _, _, service = context
    foundation(service)
    assert service.get_item_by_internal_name("' OR 1=1 --") is None
    assert service.find_dictionary_by_header("' OR 1=1 --") is None
