"""격리된 합성 Phase 9C UI smoke DB를 생성하고 그 DB로 GUI를 실행한다."""

import argparse
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from small_stream_research_tool.app.controller import ApplicationController  # noqa: E402
from small_stream_research_tool.config.settings import get_app_paths  # noqa: E402
from small_stream_research_tool.database import connect_database, initialize_database  # noqa: E402
from small_stream_research_tool.database.connection import transaction  # noqa: E402
from small_stream_research_tool.models.correction import CorrectionRequest  # noqa: E402
from small_stream_research_tool.repositories.dictionary_repository import (  # noqa: E402
    DictionaryRepository,
)
from small_stream_research_tool.repositories.import_persistence_repository import (  # noqa: E402
    CharacteristicValueRepository,
    ImportColumnMappingRepository,
    ImportHistoryRepository,
    ImportSheetRepository,
    SmallStreamRepository,
    SourceFileRepository,
)
from small_stream_research_tool.services.correction_service import CorrectionService  # noqa: E402
from small_stream_research_tool.services.current_value_service import (  # noqa: E402
    CurrentValueService,
)
from small_stream_research_tool.services.research_dictionary_bootstrap import (  # noqa: E402
    ResearchDictionaryBootstrapService,
)
from small_stream_research_tool.ui.theme import STYLESHEET  # noqa: E402

STAMP = "2026-09-17T00:00:00Z"
STREAMS = (
    ("99000000001", "테스트천A", "활성 문제 없음과 다수 현재값"),
    ("99000000002", "테스트천B", "확인 필요와 별도 검토상태"),
    ("99000000003", "테스트천C", "오류 상태"),
    ("99000000004", "테스트천D", "현재 사용값 미지정"),
    ("99000000005", "테스트천E", "현재값 연결 확인 필요"),
)
FOCUS_NAMES = (
    "stream_length_total",
    "stream_length_unimproved",
    "stream_length_improved",
    "basin_area",
    "flow_path_length",
    "basin_average_slope",
    "stream_bed_slope",
    "cn_amc_i",
    "cn_amc_ii",
    "cn_amc_iii",
    "source_plan_frequency",
    "source_plan_flood_discharge",
    "source_design_channel_width",
    "end_plan_frequency",
    "end_plan_flood_discharge",
    "end_design_channel_width",
)


def smoke_path(raw):
    path = Path(raw).expanduser().resolve()
    build = (ROOT / "build").resolve()
    default = (get_app_paths().database_dir / "research.sqlite3").resolve()
    if path.parent != build or "ui_smoke" not in path.stem.lower() or path.suffix != ".db":
        raise ValueError("smoke DB는 repository build 폴더의 *ui_smoke*.db 경로여야 합니다.")
    if path == default:
        raise ValueError("기본 local DB 경로는 smoke DB로 사용할 수 없습니다.")
    return path


def _stream(repo, code, name, note, index):
    repo.create(
        stream_code=code,
        province_code="99",
        city_county_code="000",
        town_code="000",
        stream_serial_no=f"{index:03d}",
        stream_name=name,
        province_name="테스트도",
        city_county_name="테스트군",
        town_name="테스트면",
        river_system="합성 수계",
        source_address=f"테스트 주소 {index} 시점",
        source_latitude=35.0 + index / 100,
        source_longitude=127.0 + index / 100,
        end_address=f"테스트 주소 {index} 종점",
        end_latitude=35.1 + index / 100,
        end_longitude=127.1 + index / 100,
        created_at=STAMP,
        updated_at=STAMP,
    )


def _value_data(item, number):
    typed = {"value_number": None, "value_integer": None, "value_text": None, "value_date": None}
    if item.data_type == "INTEGER":
        typed["value_integer"] = int(number)
    else:
        typed["value_number"] = float(number)
    return typed


def create_database(path):
    path = smoke_path(path)
    if path.exists():
        raise FileExistsError("기존 DB를 덮어쓰지 않습니다. 새 smoke DB 파일명을 사용하세요.")
    path.parent.mkdir(parents=True, exist_ok=True)
    initialize_database(path)
    try:
        with closing(connect_database(path)) as connection:
            ResearchDictionaryBootstrapService(connection).bootstrap()
            dictionary = DictionaryRepository(connection)
            approved = (
                ResearchDictionaryBootstrapService(connection)
                .approved_display_policy()
                .allowed_dictionary_ids
            )
            items = [item for item in dictionary.list_items() if item.dictionary_id in approved]
            by_name = {item.internal_name: item for item in items}
            with transaction(connection):
                streams = SmallStreamRepository(connection)
                for index, (code, name, note) in enumerate(STREAMS, 1):
                    _stream(streams, code, name, note, index)
                source = SourceFileRepository(connection).create(
                    file_name="synthetic_ui_smoke.xlsx",
                    original_path="synthetic://ui-smoke/synthetic_ui_smoke.xlsx",
                    file_extension=".xlsx",
                    source_description="UI_SMOKE_SYNTHETIC_ONLY",
                    registered_at=STAMP,
                )
                imported = ImportHistoryRepository(connection).create(
                    source_file_id=source.source_file_id,
                    batch_code="UI-SMOKE-SYNTHETIC-001",
                    import_type="EXCEL",
                    status="SUCCESS",
                    started_at=STAMP,
                    finished_at=STAMP,
                    total_rows=len(STREAMS),
                    accepted_rows=len(STREAMS),
                    warning_rows=0,
                    rejected_rows=0,
                    created_at=STAMP,
                )
                sheet = ImportSheetRepository(connection).create(
                    import_id=imported.import_id,
                    sheet_name="UI_SMOKE_SYNTHETIC",
                    sheet_index=0,
                    data_start_row=2,
                    total_rows=len(STREAMS),
                    accepted_rows=len(STREAMS),
                    warning_rows=0,
                    rejected_rows=0,
                    status="SUCCESS",
                    created_at=STAMP,
                )
                mappings = {}
                mapping_repo = ImportColumnMappingRepository(connection)
                for column, item in enumerate(items, 1):
                    mappings[item.dictionary_id] = mapping_repo.create(
                        import_sheet_id=sheet.import_sheet_id,
                        source_column_index=column,
                        source_header="UI_SMOKE_" + item.internal_name,
                        normalized_header="ui_smoke_" + item.internal_name,
                        dictionary_id=item.dictionary_id,
                        mapping_status="USER_MAPPED",
                        mapping_method="USER",
                        target_unit_id=item.unit_id,
                        user_confirmed=True,
                        created_at=STAMP,
                    )
                values = CharacteristicValueRepository(connection)
                plans = {
                    STREAMS[0][0]: items,
                    STREAMS[1][0]: [by_name[name] for name in FOCUS_NAMES],
                    STREAMS[2][0]: [by_name[name] for name in FOCUS_NAMES[:10]],
                    STREAMS[3][0]: [by_name[name] for name in FOCUS_NAMES[:8]],
                    STREAMS[4][0]: [by_name[name] for name in FOCUS_NAMES[:10]],
                }
                row_number = 2
                for stream_index, (code, planned) in enumerate(plans.items(), 1):
                    for item_index, item in enumerate(planned, 1):
                        marker = "UI_SMOKE_CURRENT"
                        if code == STREAMS[0][0] and item.internal_name == "basin_area":
                            marker = "UI_SMOKE_CORRECTION_SOURCE"
                        elif code == STREAMS[1][0] and item.internal_name == "basin_area":
                            marker = "UI_SMOKE_WARNING_CURRENT"
                        record = values.create(
                            stream_code=code,
                            dictionary_id=item.dictionary_id,
                            **_value_data(item, stream_index * 100 + item_index / 10),
                            unit_id=item.unit_id,
                            original_value=f"UI_SMOKE_{stream_index}_{item_index}",
                            import_id=imported.import_id,
                            import_sheet_id=sheet.import_sheet_id,
                            source_row=row_number,
                            mapping_id=mappings[item.dictionary_id].mapping_id,
                            source_type="IMPORT",
                            source_reference=marker,
                            reference_year=2099,
                            is_representative=False,
                            quality_status="UNREVIEWED",
                            is_active=True,
                            created_at=STAMP,
                            updated_at=STAMP,
                        )
                        if marker == "UI_SMOKE_WARNING_CURRENT":
                            connection.execute(
                                "INSERT INTO data_quality_issue "
                                "(characteristic_value_id,stream_code,dictionary_id,issue_type,"
                                "severity,message,review_status,is_active,created_at) "
                                "VALUES (?,?,?,?,?,?,?,?,?)",
                                (
                                    record.characteristic_value_id,
                                    code,
                                    item.dictionary_id,
                                    "UI_SMOKE_WARNING",
                                    "WARNING",
                                    "합성 UI 확인용 문제",
                                    "CONFIRMED",
                                    1,
                                    STAMP,
                                ),
                            )
                    row_number += 1
                for code, severity, review in (
                    (STREAMS[1][0], "INFO", "CONFIRMED"),
                    (STREAMS[2][0], "ERROR", "UNREVIEWED"),
                ):
                    connection.execute(
                        "INSERT INTO data_quality_issue "
                        "(stream_code,issue_type,severity,message,review_status,is_active,"
                        "created_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (
                            code,
                            "UI_SMOKE_STREAM_STATE",
                            severity,
                            "합성 UI 확인용 상태",
                            review,
                            1,
                            STAMP,
                        ),
                    )
        return path
    except BaseException:
        # 새로 만든 smoke 파일만 실패 시 제거한다. 기존 파일은 위에서 거부한다.
        path.unlink(missing_ok=True)
        raise


def finalize_after_registration(path):
    path = smoke_path(path)
    with closing(connect_database(path)) as connection:
        users = connection.execute(
            "SELECT user_id FROM app_user WHERE is_active=1 ORDER BY user_id"
        ).fetchall()
        if len(users) != 1:
            return False
        actor = users[0][0]
        current = CurrentValueService(connection)
        correction_source = connection.execute(
            "SELECT characteristic_value_id FROM characteristic_value "
            "WHERE source_reference='UI_SMOKE_CORRECTION_SOURCE'"
        ).fetchone()[0]
        correction = connection.execute(
            "SELECT characteristic_value_id,is_representative FROM characteristic_value "
            "WHERE source_type='USER_CORRECTION' AND stream_code=? AND dictionary_id=("
            "SELECT dictionary_id FROM characteristic_value WHERE characteristic_value_id=?)",
            (STREAMS[0][0], correction_source),
        ).fetchone()
        rows = connection.execute(
            "SELECT characteristic_value_id,source_reference,is_representative "
            "FROM characteristic_value WHERE source_reference LIKE 'UI_SMOKE_%' "
            "ORDER BY characteristic_value_id"
        ).fetchall()
        for value_id, marker, representative in rows:
            if representative:
                continue
            if marker == "UI_SMOKE_CORRECTION_SOURCE" and correction is not None:
                continue
            if marker == "UI_SMOKE_WARNING_CURRENT":
                current.select_current_value(
                    value_id, actor, confirm_review_required=True, reason="QC_REVIEW_CONFIRMED"
                )
            else:
                current.select_current_value(value_id, actor, reason="RESEARCHER_SELECTION")
        if correction is None:
            created = CorrectionService(connection).create_correction(
                CorrectionRequest(correction_source, actor, 321.5, "SOURCE_REVIEW")
            )
            correction_id = created.correction_value_id
            current.select_current_value(correction_id, actor, reason="SOURCE_REVIEW")
        else:
            correction_id = correction[0]
            if not correction[1]:
                current.select_current_value(correction_id, actor, reason="SOURCE_REVIEW")
        if not connection.execute(
            "SELECT 1 FROM data_quality_issue WHERE issue_type='UI_SMOKE_ERROR_CURRENT'"
        ).fetchone():
            error_value = connection.execute(
                "SELECT characteristic_value_id,dictionary_id FROM characteristic_value "
                "WHERE stream_code=? AND is_representative=1 LIMIT 1",
                (STREAMS[2][0],),
            ).fetchone()
            with transaction(connection):
                connection.execute(
                    "INSERT INTO data_quality_issue "
                    "(characteristic_value_id,stream_code,dictionary_id,issue_type,severity,"
                    "message,review_status,is_active,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        error_value[0],
                        STREAMS[2][0],
                        error_value[1],
                        "UI_SMOKE_ERROR_CURRENT",
                        "ERROR",
                        "합성 UI 확인용 오류",
                        "IN_REVIEW",
                        1,
                        STAMP,
                    ),
                )
        with transaction(connection):
            connection.execute(
                "DELETE FROM stream_characteristic WHERE stream_code=?",
                (STREAMS[4][0],),
            )
        return correction_id > 0


def run_gui(path):
    path = smoke_path(path)
    if not path.is_file():
        raise FileNotFoundError("먼저 create 명령으로 smoke DB를 생성하세요.")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    app.setApplicationName("소하천 데이터 관리 · UI Smoke")
    app.setStyleSheet(STYLESHEET)
    controller = ApplicationController(path)
    if not controller.auth_service.needs_initial_user_setup():
        finalize_after_registration(path)
    controller.start()
    if controller.login_window.initial_setup:
        controller.login_window.registered.connect(lambda: finalize_after_registration(path))
    app.aboutToQuit.connect(controller.close)
    return app.exec()


def main(argv=None):
    parser = argparse.ArgumentParser(description="격리된 합성 UI smoke DB 도구")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "run"):
        command = subparsers.add_parser(name)
        command.add_argument("--db", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            print(create_database(args.db))
            return 0
        return run_gui(args.db)
    except Exception as error:
        print(f"UI smoke 작업 실패: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
