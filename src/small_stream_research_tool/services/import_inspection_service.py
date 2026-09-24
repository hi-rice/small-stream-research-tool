"""10B 파일·sheet·header 구조를 DB 변경 없이 공개 모델로 투영한다."""

from contextlib import closing
from dataclasses import replace
from pathlib import Path

from small_stream_research_tool.database import connect_database
from small_stream_research_tool.models.excel_errors import ExcelError
from small_stream_research_tool.models.import_workflow import (
    HeaderColumnSummary,
    ImportInspectionError,
    ImportWorkflowState,
    SheetSummary,
)
from small_stream_research_tool.models.workspace import WorkspaceStep
from small_stream_research_tool.models.workspace_errors import (
    WorkspaceError,
    WorkspaceSourceChangedError,
    WorkspaceSourceMissingError,
)
from small_stream_research_tool.services.excel_reader import ExcelReader
from small_stream_research_tool.services.phase10_read_service import Phase10ReadService
from small_stream_research_tool.services.workspace_service import WorkspaceService
from small_stream_research_tool.utils.file_hash import file_sha256


def _snapshot(path):
    try:
        stat = path.stat()
        if not path.is_file():
            raise ImportInspectionError("일반 파일을 선택해 주세요.")
        return stat.st_size, stat.st_mtime_ns
    except OSError:
        raise ImportInspectionError("파일을 읽을 수 없습니다.") from None


def _digest(path):
    before = _snapshot(path)
    try:
        digest = file_sha256(path)
    except OSError:
        raise ImportInspectionError("파일을 읽을 수 없습니다.") from None
    if _snapshot(path) != before:
        raise ImportInspectionError("파일 확인 중 원본이 변경되었습니다.")
    return digest, before


class ImportInspectionService:
    def __init__(self, db_path, workspace_dir=None):
        self._db_path = db_path
        self._workspace_dir = workspace_dir

    def inspect(self, source_path):
        try:
            path = Path(source_path).absolute()
            if path.suffix.lower() != ".xlsx":
                raise ImportInspectionError(".xlsx 파일만 지원합니다.")
            digest, before = _digest(path)
            with ExcelReader(path) as reader:
                sheets = []
                for name in reader.workbook_info.sheet_names:
                    info = reader.sheet_info(name)
                    has_cells = info.kind == "worksheet" and bool(info.max_row and info.max_column)
                    if has_cells:
                        has_cells = any(
                            column.display_header
                            for column in reader.read_columns(
                                name, header_start_row=1, header_end_row=1
                            )
                        )
                        if not has_cells and info.max_row > 1:
                            has_cells = any(
                                not row.is_blank
                                for row in reader.iter_rows(
                                    name,
                                    header_start_row=1,
                                    header_end_row=1,
                                    data_start_row=2,
                                    include_blank=False,
                                )
                            )
                    sheets.append(
                        SheetSummary(
                            info.name,
                            info.index,
                            info.max_row,
                            info.max_column,
                            info.state,
                            info.kind,
                            has_cells,
                        )
                    )
            if _snapshot(path) != before:
                raise ImportInspectionError("파일 확인 중 원본이 변경되었습니다.")
            with closing(connect_database(self._db_path)) as connection:
                duplicates = Phase10ReadService(connection).find_duplicate_imports(digest)
            return ImportWorkflowState(
                str(path), digest, path.name, before[0], tuple(sheets), duplicates
            )
        except ImportInspectionError:
            raise
        except (ExcelError, OSError, TypeError, ValueError):
            raise ImportInspectionError("Excel workbook을 확인할 수 없습니다.") from None
        except Exception:
            raise ImportInspectionError("파일 이력을 확인할 수 없습니다.") from None

    def structure(self, state, sheet_name, header_start, header_end, data_start):
        if type(state) is not ImportWorkflowState:
            raise ImportInspectionError("파일을 다시 선택해 주세요.")
        sheet = next((item for item in state.sheets if item.name == sheet_name), None)
        if sheet is None or not sheet.selectable:
            raise ImportInspectionError("가져올 수 있는 worksheet를 선택해 주세요.")
        if not (
            all(type(value) is int for value in (header_start, header_end, data_start))
            and 1 <= header_start <= header_end < data_start <= sheet.row_count + 1
        ):
            raise ImportInspectionError("헤더와 데이터 행 범위를 확인해 주세요.")
        try:
            path = Path(state.source_path)
            digest, before = _digest(path)
            if digest != state.file_hash:
                raise ImportInspectionError("원본 파일이 변경되었습니다. 다시 선택해 주세요.")
            with ExcelReader(path) as reader:
                columns = reader.read_columns(
                    sheet_name, header_start_row=header_start, header_end_row=header_end
                )
            if _snapshot(path) != before:
                raise ImportInspectionError("구조 확인 중 원본이 변경되었습니다.")
            if not columns or not any(column.display_header for column in columns):
                raise ImportInspectionError("선택한 범위에서 헤더를 찾지 못했습니다.")
            return replace(
                state,
                selected_sheet=sheet_name,
                header_start_row=header_start,
                header_end_row=header_end,
                data_start_row=data_start,
                columns=tuple(
                    HeaderColumnSummary(
                        column.column_index, column.column_letter, column.display_header
                    )
                    for column in columns
                ),
                workspace_saved_at=None,
            )
        except ImportInspectionError:
            raise
        except (ExcelError, OSError, TypeError, ValueError):
            raise ImportInspectionError("헤더 구조를 확인하지 못했습니다.") from None

    def save(self, state, user_id):
        if type(state) is not ImportWorkflowState or not state.columns:
            raise ImportInspectionError("먼저 헤더 구조를 확인해 주세요.")
        try:
            workspace = WorkspaceService(self._workspace_dir)
            draft = workspace.create_workspace(
                current_user_id=user_id,
                source_file_path=state.source_path,
                selected_sheet_name=state.selected_sheet,
                header_start_row=state.header_start_row,
                header_end_row=state.header_end_row,
                data_start_row=state.data_start_row,
                current_step=WorkspaceStep.HEADER_CONFIGURED,
            )
            if draft.source_file_sha256 != state.file_hash:
                raise ImportInspectionError("원본 파일이 변경되었습니다. 다시 선택해 주세요.")
            saved = workspace.save_workspace(draft, user_id)
            return replace(state, workspace_saved_at=saved.saved_at)
        except ImportInspectionError:
            raise
        except WorkspaceError:
            raise ImportInspectionError("작업을 저장하지 못했습니다.") from None

    def resume(self, user_id):
        try:
            draft = WorkspaceService(self._workspace_dir).load_workspace(user_id)
            if draft is None:
                raise ImportInspectionError("저장된 작업이 없습니다.")
            state = self.inspect(draft.source_file_path)
            if state.file_hash != draft.source_file_sha256:
                raise ImportInspectionError("원본 파일이 변경되어 재개할 수 없습니다.")
            if draft.current_step == WorkspaceStep.FILE_SELECTED:
                return replace(state, workspace_saved_at=draft.saved_at)
            if draft.current_step not in (
                WorkspaceStep.HEADER_CONFIGURED,
                WorkspaceStep.MAPPING,
                WorkspaceStep.CODE_VALIDATION,
                WorkspaceStep.PREVIEW,
                WorkspaceStep.COMPLETED,
            ):
                raise ImportInspectionError("이 작업 단계는 현재 화면에서 재개할 수 없습니다.")
            if draft.selected_sheet_name is None or draft.header_start_row is None:
                raise ImportInspectionError("저장된 작업 상태를 확인할 수 없습니다.")
            structured = self.structure(
                state,
                draft.selected_sheet_name,
                draft.header_start_row,
                draft.header_end_row,
                draft.data_start_row,
            )
            return replace(structured, workspace_saved_at=draft.saved_at)
        except ImportInspectionError:
            raise
        except (WorkspaceSourceChangedError, WorkspaceSourceMissingError):
            raise ImportInspectionError("원본 파일이 변경되거나 없어 재개할 수 없습니다.") from None
        except WorkspaceError:
            raise ImportInspectionError("저장된 작업을 재개하지 못했습니다.") from None
