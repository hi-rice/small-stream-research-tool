"""Phase 10C-2 V2 dictionary and unit-evidence contract."""

from contextlib import closing

import pytest
from tests.integration.test_phase_10c_import_mapping import (
    CORE,
    _identity_workbook,
    _source,
    _workbook,
)

from small_stream_research_tool.database import connect_database, initialize_database
from small_stream_research_tool.services.app_read_service import AppReadService
from small_stream_research_tool.services.import_mapping_workflow_service import (
    ImportMappingWorkflowService,
)
from small_stream_research_tool.services.research_dictionary_bootstrap import (
    ResearchDictionaryBootstrapService,
    ResearchDictionaryError,
    load_research_manifest,
    manifest_fingerprint,
)
from small_stream_research_tool.services.research_unit_evidence_service import (
    ResearchUnitEvidenceService,
)


def _database(tmp_path):
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    return path


def _snapshot(connection):
    return "\n".join(connection.iterdump())


def test_v1_is_unchanged_and_v2_has_only_approved_unit_differences():
    v1 = load_research_manifest("research-dictionary-v1")
    v2 = load_research_manifest("research-dictionary-v2")
    assert manifest_fingerprint(v1) != manifest_fingerprint(v2)
    one = {item["internal_name"]: item for item in v1["items"]}
    two = {item["internal_name"]: item for item in v2["items"]}
    assert len(one) == len(two) == 70
    changed = {
        name: (one[name]["unit_symbol"], two[name]["unit_symbol"])
        for name in one
        if one[name] != two[name]
    }
    assert changed == {
        "arrival_time": (None, "hr"),
        "storage_constant": (None, "hr"),
        "initial_loss": (None, "mm"),
        "source_plan_frequency": (None, "year"),
        "end_plan_frequency": (None, "year"),
    }


def test_evidence_has_five_defined_two_unitless_and_thirteen_unresolved():
    policy = ResearchUnitEvidenceService().load()
    counts = {}
    for item in policy.items:
        counts[item.applicability.value] = counts.get(item.applicability.value, 0) + 1
    assert counts == {"UNIT_DEFINED": 5, "UNITLESS": 2, "UNRESOLVED": 13}
    assert policy.research_version == "research-dictionary-v2"


def test_zero_use_upgrade_is_atomic_idempotent_and_preserves_created_version(tmp_path):
    path = _database(tmp_path)
    with closing(connect_database(path)) as connection:
        service = ResearchDictionaryBootstrapService(connection)
        service.bootstrap()
        before = dict(
            connection.execute(
                "SELECT internal_name,created_version_id FROM data_dictionary"
            ).fetchall()
        )
        result = service.upgrade_to_v2()
        upgraded = _snapshot(connection)
        assert service.upgrade_to_v2() == result
        assert _snapshot(connection) == upgraded
        rows = connection.execute(
            "SELECT d.internal_name,u.unit_symbol,d.created_version_id "
            "FROM data_dictionary d LEFT JOIN unit_dictionary u ON u.unit_id=d.unit_id"
        ).fetchall()
        units = {name: unit for name, unit, _version in rows}
        assert units["arrival_time"] == units["storage_constant"] == "hr"
        assert units["initial_loss"] == "mm"
        assert units["source_plan_frequency"] == units["end_plan_frequency"] == "year"
        assert all(before[name] == version for name, _unit, version in rows if name in before)
        assert connection.execute(
            "SELECT version FROM dictionary_version WHERE is_current=1"
        ).fetchone() == ("research-dictionary-v2",)


def test_any_existing_value_blocks_upgrade_and_rolls_back(tmp_path):
    path = _database(tmp_path)
    with closing(connect_database(path)) as connection:
        service = ResearchDictionaryBootstrapService(connection)
        service.bootstrap()
        item_id = connection.execute(
            "SELECT dictionary_id FROM data_dictionary WHERE internal_name='arrival_time'"
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO small_stream(stream_code,province_code,city_county_code,town_code,"
            "stream_serial_no,stream_name,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (
                "01234567001",
                "01",
                "234",
                "567",
                "001",
                "합성천",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )
        connection.execute(
            "INSERT INTO characteristic_value(stream_code,dictionary_id,value_number,source_type,"
            "quality_status,is_active,is_representative,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (
                "01234567001",
                item_id,
                1.0,
                "IMPORT",
                "UNREVIEWED",
                0,
                0,
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )
        before = _snapshot(connection)
        with pytest.raises(ResearchDictionaryError):
            service.upgrade_to_v2()
        assert _snapshot(connection) == before
        assert connection.execute(
            "SELECT version FROM dictionary_version WHERE is_current=1"
        ).fetchone() == ("research-dictionary-v1",)
        assert connection.execute("SELECT count(*) FROM unit_dictionary").fetchone() == (6,)


def test_fresh_database_can_bootstrap_v2_directly(tmp_path):
    path = _database(tmp_path)
    with closing(connect_database(path)) as connection:
        result = ResearchDictionaryBootstrapService(connection).bootstrap_v2()
        assert result.manifest_version == "research-dictionary-v2"
        assert connection.execute(
            "SELECT version FROM dictionary_version WHERE is_current=1"
        ).fetchone() == ("research-dictionary-v2",)
        assert AppReadService(connection).get_home_summary().dictionary_state == "READY"
        definitions = ResearchDictionaryBootstrapService(connection).approved_display_policy()
        assert len(definitions.allowed_dictionary_ids) == 70


def test_v1_bootstrap_cannot_downgrade_current_v2(tmp_path):
    path = _database(tmp_path)
    with closing(connect_database(path)) as connection:
        service = ResearchDictionaryBootstrapService(connection)
        service.bootstrap_v2()
        before = _snapshot(connection)
        with pytest.raises(ResearchDictionaryError):
            service.bootstrap()
        assert connection.execute(
            "SELECT version FROM dictionary_version WHERE is_current=1"
        ).fetchone() == ("research-dictionary-v2",)
        assert _snapshot(connection) == before


def test_upgrade_rolls_back_definition_and_version_when_final_validation_fails(
    tmp_path, monkeypatch
):
    path = _database(tmp_path)
    with closing(connect_database(path)) as connection:
        service = ResearchDictionaryBootstrapService(connection)
        service.bootstrap()
        before = _snapshot(connection)

        def fail_validation(_manifest):
            raise ResearchDictionaryError()

        monkeypatch.setattr(service, "_verify_manifest", fail_validation)
        with pytest.raises(ResearchDictionaryError):
            service.upgrade_to_v2()
        assert _snapshot(connection) == before


def test_v2_mapping_requires_explicit_exact_source_unit(tmp_path):
    path = _database(tmp_path)
    workbook = tmp_path / "synthetic.xlsx"
    workspace = tmp_path / "workspace"
    with closing(connect_database(path)) as connection:
        ResearchDictionaryBootstrapService(connection).bootstrap()
        ResearchDictionaryBootstrapService(connection).upgrade_to_v2()
    _workbook(workbook)
    source = _source(workbook, path, workspace)
    workflow = ImportMappingWorkflowService(path, workspace)
    state = workflow.set_scope(workflow.start(source, 1), "NATIONAL_2024", 1)
    basin = next(row for row in state.rows if row.target == "유역면적")
    assert basin.unit_status == "확인 필요"
    wrong = next(option.unit_id for option in state.unit_options if option.symbol == "km")
    state = workflow.confirm_unit(state, basin.index, wrong, 1)
    assert next(row for row in state.rows if row.index == basin.index).unit_status == "단위 불일치"
    expected = next(option.unit_id for option in state.unit_options if option.symbol == "km²")
    state = workflow.confirm_unit(state, basin.index, expected, 1)
    assert next(row for row in state.rows if row.index == basin.index).unit_status == "확인됨"
    result = workflow.preview(state, 1)
    assert result.preview.ready_for_import_preparation
    assert result.preview.unit_review_count == 0


def test_v2_confirmation_preserves_evidence_source_notation(tmp_path):
    path = _database(tmp_path)
    workbook = tmp_path / "source-notation.xlsx"
    workspace = tmp_path / "workspace"
    with closing(connect_database(path)) as connection:
        ResearchDictionaryBootstrapService(connection).bootstrap_v2()
    headers = [*(label for _name, label in CORE), "초기손실"]
    values = ["01234567001", "01", "234", "567", "001", "합성 하천", 3.5]
    _identity_workbook(workbook, headers, values)
    source = _source(workbook, path, workspace)
    workflow = ImportMappingWorkflowService(path, workspace)
    state = workflow.set_scope(workflow.start(source, 1), "NATIONAL_2024", 1)
    row = next(row for row in state.rows if row.target == "초기손실")
    expected = next(option.unit_id for option in state.unit_options if option.symbol == "mm")
    state = workflow.confirm_unit(state, row.index, expected, 1)
    confirmation = next(
        item for item in state.unit_confirmations if item.source_column_index == row.index
    )
    assert confirmation.source_notation == "㎜"
    assert confirmation.selected_unit_id == confirmation.expected_unit_id == expected
