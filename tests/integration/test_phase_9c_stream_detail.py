"""합성 DB와 offscreen Qt에서 Phase 9C 상세 조회 계약을 검증한다."""

import json
import os
import time
from contextlib import closing
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from small_stream_research_tool.app.controller import GuiSession
from small_stream_research_tool.database import connect_database, initialize_database
from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.repositories.import_persistence_repository import (
    SmallStreamRepository,
)
from small_stream_research_tool.services.research_dictionary_bootstrap import (
    ResearchDictionaryBootstrapService,
)
from small_stream_research_tool.services.stream_read_service import StreamReadService
from small_stream_research_tool.ui.main_window import MainWindow
from small_stream_research_tool.ui.presentation import (
    CURRENT_TEXT,
    STATUS_TEXT,
    display_timestamp,
)

STAMP = "2026-09-16T01:02:03Z"
CODE = "01234567001"


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def wait_for(app, condition, seconds=5):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return
        time.sleep(0.02)
    pytest.fail("합성 DB GUI 작업이 끝나지 않았습니다.")


def seed_stream(connection):
    with transaction(connection):
        SmallStreamRepository(connection).create(
            stream_code=CODE,
            province_code="01",
            city_county_code="234",
            town_code="567",
            stream_serial_no="001",
            stream_name="합성 소하천",
            province_name="합성도",
            city_county_name="합성시",
            town_name="합성면",
            river_system="합성 수계",
            source_address="합성 시점",
            source_latitude=36.1,
            source_longitude=127.2,
            end_address="합성 종점",
            end_latitude=36.2,
            end_longitude=127.3,
            created_at=STAMP,
            updated_at=STAMP,
        )


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "phase9c.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as connection:
        seed_stream(connection)
    return path


def item_id(connection, internal_name):
    return connection.execute(
        "SELECT dictionary_id FROM data_dictionary WHERE internal_name=?", (internal_name,)
    ).fetchone()[0]


def add_value(connection, dictionary_id, value, *, source_type="IMPORT", active=1, current=0):
    cursor = connection.execute(
        "INSERT INTO characteristic_value (stream_code,dictionary_id,value_number,"
        "original_value,source_type,is_representative,is_active,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            CODE,
            dictionary_id,
            value,
            "RAW_NOT_FOR_DISPLAY",
            source_type,
            current,
            active,
            STAMP,
            STAMP,
        ),
    )
    value_id = cursor.lastrowid
    if current and active:
        connection.execute(
            "INSERT INTO stream_characteristic VALUES (?,?,?,?)",
            (CODE, dictionary_id, value_id, STAMP),
        )
    return value_id


def test_uninitialized_dictionary_is_distinct_from_no_values(database):
    with closing(connect_database(database)) as connection:
        detail = StreamReadService(connection).get_research_stream_detail(CODE)
    assert detail.dictionary_state == "UNINITIALIZED"
    assert detail.characteristics == ()
    assert detail.basic.source_latitude == 36.1
    assert detail.basic.end_longitude == 127.3


def test_approved_items_categories_metadata_and_unassigned_state(database):
    with closing(connect_database(database)) as connection:
        ResearchDictionaryBootstrapService(connection).bootstrap()
        detail = StreamReadService(connection).get_research_stream_detail(CODE)
    assert detail.dictionary_state == "READY" and len(detail.characteristics) == 70
    assert {row.category_key for row in detail.characteristics} == {
        "basic_characteristic",
        "basin_stream_characteristic",
        "soil_characteristic",
        "land_use",
        "planning_design",
    }
    assert sum(row.representative_six for row in detail.characteristics) == 39
    assert sum(row.focus_nine for row in detail.characteristics) == 45
    assert all(row.current_use_status == "UNASSIGNED" for row in detail.characteristics)


def test_current_qc_provenance_history_and_sensitive_boundaries(database):
    with closing(connect_database(database)) as connection:
        ResearchDictionaryBootstrapService(connection).bootstrap()
        dictionary_id = item_id(connection, "basin_area")
        imported_id = add_value(connection, dictionary_id, 1.0, active=0)
        connection.execute(
            "INSERT INTO source_file (file_name,original_path,registered_at) VALUES (?,?,?)",
            ("synthetic.xlsx", "C:/private/absolute/source.xlsx", STAMP),
        )
        connection.execute(
            "INSERT INTO import_history (source_file_id,batch_code,import_type,status,"
            "started_at,created_at) VALUES (1,'SYNTHETIC-BATCH','EXCEL','SUCCESS',?,?)",
            (STAMP, STAMP),
        )
        connection.execute(
            "UPDATE characteristic_value SET import_id=1,source_row=7 "
            "WHERE characteristic_value_id=?",
            (imported_id,),
        )
        current_id = add_value(
            connection, dictionary_id, 2.5, source_type="USER_CORRECTION", current=1
        )
        key = json.dumps(
            {"stream_code": CODE, "dictionary_id": dictionary_id},
            sort_keys=True,
            separators=(",", ":"),
        )
        connection.execute(
            "INSERT INTO record_history (table_name,record_key,old_value,new_value,"
            "change_type,changed_at) VALUES ('characteristic_value',?,?,?,?,?)",
            (
                key,
                json.dumps({"source_value_id": imported_id}),
                json.dumps({"correction_value_id": current_id}),
                "CORRECTION",
                STAMP,
            ),
        )
        connection.execute(
            "INSERT INTO data_quality_issue (characteristic_value_id,stream_code,dictionary_id,"
            "issue_type,severity,message,review_status,is_active,original_value,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                current_id,
                CODE,
                dictionary_id,
                "RANGE_CHECK",
                "WARNING",
                "raw internal message",
                "CONFIRMED",
                1,
                "PRIVATE_RAW",
                STAMP,
            ),
        )
        connection.execute(
            "INSERT INTO data_quality_issue (characteristic_value_id,stream_code,dictionary_id,"
            "issue_type,severity,message,review_status,is_active,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (current_id, CODE, dictionary_id, "OLD", "ERROR", "inactive", "UNREVIEWED", 0, STAMP),
        )
        detail = StreamReadService(connection).get_research_stream_detail(CODE)
    row = next(row for row in detail.characteristics if row.internal_name == "basin_area")
    assert row.current_value == 2.5 and row.current_use_status == "VALID_CURRENT"
    assert row.qc_display_state == "NEEDS_REVIEW"
    assert [(issue.severity, issue.review_status) for issue in row.qc_items] == [
        ("WARNING", "CONFIRMED")
    ]
    assert row.provenance.classification == "RESEARCHER_CORRECTION"
    assert len(row.value_history) == 2
    assert any(not value.is_active and value.value == 1.0 for value in row.value_history)
    assert any(value.is_current_use and value.value == 2.5 for value in row.value_history)
    imported = next(value for value in row.value_history if value.value == 1.0)
    corrected = next(value for value in row.value_history if value.value == 2.5)
    assert imported.provenance_summary == "Import 자료 · 원본 행 7"
    assert "SYNTHETIC-BATCH" not in imported.provenance_summary
    assert corrected.provenance_summary == "연구자 보정값 · 이전 값에서 생성"
    shown = repr(detail)
    assert "RAW_NOT_FOR_DISPLAY" not in shown and "PRIVATE_RAW" not in shown
    assert "raw internal message" not in shown
    assert "absolute" not in shown and "synthetic.xlsx" not in shown


def test_cache_inconsistency_is_not_shown_as_current(database):
    with closing(connect_database(database)) as connection:
        ResearchDictionaryBootstrapService(connection).bootstrap()
        dictionary_id = item_id(connection, "basin_area")
        add_value(connection, dictionary_id, 3.5, current=1)
        connection.execute("DELETE FROM stream_characteristic")
        row = next(
            row
            for row in StreamReadService(connection)
            .get_research_stream_detail(CODE)
            .characteristics
            if row.internal_name == "basin_area"
        )
    assert row.current_use_status == "INCONSISTENT" and row.current_value is None


def test_phase9c_query_count_is_batch_bounded(database):
    with closing(connect_database(database)) as connection:
        ResearchDictionaryBootstrapService(connection).bootstrap()
        trace = []
        connection.set_trace_callback(trace.append)
        try:
            detail = StreamReadService(connection).get_research_stream_detail(CODE)
        finally:
            connection.set_trace_callback(None)
    selects = [sql for sql in trace if sql.startswith("SELECT")]
    assert len(detail.characteristics) == 70
    assert len(selects) <= 13


def test_gui_navigation_loading_categories_read_only_and_safe_states(database, app):
    with closing(connect_database(database)) as connection:
        ResearchDictionaryBootstrapService(connection).bootstrap()
        with transaction(connection):
            add_value(connection, item_id(connection, "basin_area"), 2.5, current=1)
    window = MainWindow(database, GuiSession(1, "합성 연구자", None, None))
    try:
        window.resize(1440, 900)
        window.show()
        app.processEvents()
        wait_for(app, lambda: window.stream_list.model.rowCount() == 1)
        window.stream_list.table.selectRow(0)
        wait_for(app, lambda: window.stream_list.detail_button.isEnabled())
        window.stream_list.detail_button.click()
        assert window.stack.currentWidget() is window.stream_detail
        assert window.stream_detail.status.text() == "상세정보를 조회하고 있습니다."
        wait_for(app, lambda: window.stream_detail.status.text() == "읽기 전용 상세정보")
        detail = window.stream_detail
        assert detail.model.rowCount() > 0
        assert detail.table.editTriggers() == detail.table.EditTrigger.NoEditTriggers
        assert detail.scroll_area.widgetResizable()
        assert detail.scroll_area.widget() is detail.detail_content
        assert detail.table.minimumHeight() >= 250
        assert detail.detail_tabs.minimumHeight() >= 230
        assert detail.scroll_area.horizontalScrollBar().maximum() == 0
        assert detail.basic_labels["source_coordinates"].text() == "36.1, 127.2"
        assert detail.category.count() == 5
        assert [detail.category.tabText(index) for index in range(5)] == [
            "기본 특성",
            "유역·하천",
            "토양",
            "토지이용",
            "계획정보",
        ]
        assert all(
            detail.category.tabSizeHint(index).width()
            > detail.category.fontMetrics().horizontalAdvance(detail.category.tabText(index))
            for index in range(5)
        )
        assert [detail.detail_tabs.tabText(index) for index in range(3)] == [
            "값 상세",
            "QC · 검토",
            "값 이력",
        ]
        detail.category.setCurrentIndex(1)
        basin_row = next(
            index
            for index in range(detail.model.rowCount())
            if detail.model.row(index).internal_name == "basin_area"
        )
        detail.table.selectRow(basin_row)
        app.processEvents()
        assert detail.selection_badge.text() == "현재 사용값 있음"
        assert detail.qc_empty.text() == "현재 사용값에 활성 QC 문제가 없습니다."
        assert [detail.history_table.horizontalHeaderItem(index).text() for index in range(7)] == [
            "값",
            "단위",
            "출처",
            "활성",
            "현재 사용",
            "등록 시각",
            "출처 요약",
        ]
        assert detail.history_table.item(0, 4).text() == "예"
        assert detail.history_table.item(0, 5).text() == "2026-09-16 01:02 UTC"
        assert detail._basic_mode == "wide"
        window.resize(1200, 800)
        app.processEvents()
        assert detail._basic_mode == "wide"
        assert detail.scroll_area.horizontalScrollBar().maximum() == 0
        detail.detail_tabs.setCurrentIndex(2)
        app.processEvents()
        assert detail.history_table.horizontalScrollBar().maximum() > 0
        detail.history_table.horizontalScrollBar().setValue(
            detail.history_table.horizontalScrollBar().maximum()
        )
        assert detail.history_table.horizontalScrollBar().value() > 0
        window.resize(1080, 640)
        app.processEvents()
        assert detail.table.horizontalScrollBar().maximum() > 0
        assert detail.qc_table.horizontalScrollBar().maximum() > 0
        assert detail.history_table.horizontalScrollBar().maximum() > 0
        window.resize(window.minimumWidth(), window.minimumHeight())
        app.processEvents()
        assert detail._basic_mode == "compact"
        assert detail.category.count() == 5
        assert detail.detail_tabs.count() == 3
        assert detail.scroll_area.horizontalScrollBar().maximum() == 0
        assert detail.table.horizontalScrollBar().maximum() > 0
        assert detail.history_table.horizontalScrollBar().maximum() > 0
        window.resize(1440, 900)
        app.processEvents()
        assert detail._basic_mode == "wide"
        window.resize(1440, 700)
        app.processEvents()
        assert detail.scroll_area.verticalScrollBar().maximum() > 0
        assert not detail.category.isHidden()
        assert not detail.detail_tabs.isHidden()
        detail.scroll_area.ensureWidgetVisible(detail.detail_tabs)
        app.processEvents()
        assert detail.scroll_area.verticalScrollBar().value() > 0
        assert detail.scroll_area.horizontalScrollBar().maximum() == 0
        assert "정상" not in STATUS_TEXT["ACTIVE_ISSUES_NONE"]
        assert CURRENT_TEXT["UNASSIGNED"] == "현재 사용값 미지정"
        detail.back.click()
        assert window.stack.currentWidget() is window.stream_list
    finally:
        window.close()
        app.processEvents()


def test_no_selection_and_stale_detail_result(database, app):
    window = MainWindow(database, GuiSession(1, "합성 연구자", None, None))
    try:
        window.navigate("소하천 조회")
        assert not window.stream_list.detail_button.isEnabled()
        window.stream_list.open_detail()
        assert window.stack.currentWidget() is window.stream_list
        view = window.stream_detail
        view._generation = 2
        view._result(1, None, "internal exception text")
        assert "internal exception" not in view.status.text()
        view._result(2, None, "internal exception text")
        assert view.status.text() == "상세정보 조회 중 오류가 발생했습니다."
    finally:
        window.close()
        app.processEvents()


def test_gui_layer_has_no_database_access():
    from small_stream_research_tool.ui import stream_detail

    source = Path(stream_detail.__file__).read_text(encoding="utf-8")
    assert "sqlite3" not in source
    assert "Repository" not in source
    assert "SELECT " not in source
    assert not CharacteristicTableModelFlags() & Qt.ItemFlag.ItemIsEditable


def CharacteristicTableModelFlags():
    from small_stream_research_tool.ui.table_model import CharacteristicTableModel

    model = CharacteristicTableModel()
    return model.flags(model.index(0, 0))


def test_timestamp_presentation_preserves_timezone_meaning():
    assert display_timestamp("2026-09-17T00:00:00Z") == "2026-09-17 00:00 UTC"
    assert display_timestamp(None) == "미등록"
    assert display_timestamp("invalid") == "시각 확인 필요"
