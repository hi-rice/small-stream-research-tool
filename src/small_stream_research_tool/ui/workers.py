"""각 조회 작업의 스레드 안에서 SQLite 연결을 만들고 닫는다."""

from contextlib import closing

from PySide6.QtCore import QObject, QRunnable, Signal

from small_stream_research_tool.database import connect_database
from small_stream_research_tool.services.app_read_service import AppReadService
from small_stream_research_tool.services.import_execution_workflow_service import (
    ImportExecutionWorkflowService,
)
from small_stream_research_tool.services.import_inspection_service import ImportInspectionService
from small_stream_research_tool.services.import_mapping_workflow_service import (
    ImportMappingWorkflowService,
)
from small_stream_research_tool.services.phase10_read_service import Phase10ReadService
from small_stream_research_tool.services.stream_read_service import StreamReadService


class QuerySignals(QObject):
    finished = Signal(int, object, object)


class QueryTask(QRunnable):
    def __init__(self, db_path, generation, operation, args):
        super().__init__()
        self.db_path = db_path
        self.generation = generation
        self.operation = operation
        self.args = args
        self.signals = QuerySignals()

    def run(self):
        try:
            with closing(connect_database(self.db_path)) as connection:
                service = StreamReadService(connection)
                result = getattr(service, self.operation)(*self.args[0], **self.args[1])
            self.signals.finished.emit(self.generation, result, None)
        except Exception:
            self.signals.finished.emit(self.generation, None, "조회 중 오류가 발생했습니다.")


class AppQueryTask(QRunnable):
    """Application read projection을 worker 소유 connection에서 실행한다."""

    def __init__(self, db_path, generation, operation, args=((), {})):
        super().__init__()
        self.db_path = db_path
        self.generation = generation
        self.operation = operation
        self.args = args
        self.signals = QuerySignals()

    def run(self):
        try:
            with closing(connect_database(self.db_path)) as connection:
                service = AppReadService(connection)
                result = getattr(service, self.operation)(*self.args[0], **self.args[1])
            self.signals.finished.emit(self.generation, result, None)
        except Exception:
            self.signals.finished.emit(self.generation, None, "조회 중 오류가 발생했습니다.")


class MyPageQueryTask(QRunnable):
    """한 worker connection에서 현재 사용자 공개 profile과 최근 작업을 조회한다."""

    def __init__(self, db_path, generation, user_id):
        super().__init__()
        self.db_path = db_path
        self.generation = generation
        self.user_id = user_id
        self.signals = QuerySignals()

    def run(self):
        try:
            with closing(connect_database(self.db_path)) as connection:
                service = AppReadService(connection)
                result = (
                    service.get_user_profile(self.user_id),
                    service.recent_user_work(self.user_id),
                )
            self.signals.finished.emit(self.generation, result, None)
        except Exception:
            self.signals.finished.emit(
                self.generation, None, "현재 사용자 정보를 확인할 수 없습니다."
            )


class ImportInspectionTask(QRunnable):
    """파일 I/O·hash·workbook·workspace 작업을 GUI thread 밖에서 실행한다."""

    def __init__(self, db_path, workspace_dir, generation, operation, args):
        super().__init__()
        self.db_path = db_path
        self.workspace_dir = workspace_dir
        self.generation = generation
        self.operation = operation
        self.args = args
        self.signals = QuerySignals()

    def run(self):
        try:
            service = ImportInspectionService(self.db_path, self.workspace_dir)
            result = getattr(service, self.operation)(*self.args)
            self.signals.finished.emit(self.generation, result, None)
        except Exception as error:
            from small_stream_research_tool.models.import_workflow import ImportInspectionError

            message = (
                str(error)
                if isinstance(error, ImportInspectionError)
                else "작업을 완료하지 못했습니다."
            )
            self.signals.finished.emit(self.generation, None, message)


class ImportMappingTask(QRunnable):
    """매핑·Preview의 파일 및 DB 조회를 worker가 소유한다."""

    def __init__(self, db_path, workspace_dir, generation, operation, args):
        super().__init__()
        self.db_path = db_path
        self.workspace_dir = workspace_dir
        self.generation = generation
        self.operation = operation
        self.args = args
        self.signals = QuerySignals()

    def run(self):
        try:
            service = ImportMappingWorkflowService(self.db_path, self.workspace_dir)
            result = getattr(service, self.operation)(*self.args)
            self.signals.finished.emit(self.generation, result, None)
        except Exception as error:
            from small_stream_research_tool.models.import_mapping_workflow import (
                MappingWorkflowError,
            )

            message = (
                str(error)
                if isinstance(error, MappingWorkflowError)
                else "작업을 완료하지 못했습니다."
            )
            self.signals.finished.emit(self.generation, None, message)


class ImportExecutionTask(QRunnable):
    """Mutation worker with one owned SQLite lifecycle inside the workflow service."""

    def __init__(self, db_path, workspace_dir, generation, operation, args):
        super().__init__()
        self.db_path = db_path
        self.workspace_dir = workspace_dir
        self.generation = generation
        self.operation = operation
        self.args = args
        self.signals = QuerySignals()

    def run(self):
        try:
            service = ImportExecutionWorkflowService(self.db_path, self.workspace_dir)
            result = getattr(service, self.operation)(*self.args)
            self.signals.finished.emit(self.generation, result, None)
        except Exception as error:
            from small_stream_research_tool.models.import_execution_workflow import (
                ImportExecutionWorkflowError,
            )

            message = (
                str(error)
                if isinstance(error, ImportExecutionWorkflowError)
                else "가져오기 작업을 완료하지 못했습니다."
            )
            self.signals.finished.emit(self.generation, None, message)


class Phase10QueryTask(QRunnable):
    def __init__(self, db_path, generation, operation, args=((), {})):
        super().__init__()
        self.db_path = db_path
        self.generation = generation
        self.operation = operation
        self.args = args
        self.signals = QuerySignals()

    def run(self):
        try:
            with closing(connect_database(self.db_path)) as connection:
                result = getattr(Phase10ReadService(connection), self.operation)(
                    *self.args[0], **self.args[1]
                )
            self.signals.finished.emit(self.generation, result, None)
        except Exception:
            self.signals.finished.emit(self.generation, None, "Import 이력을 불러오지 못했습니다.")
