"""각 조회 작업의 스레드 안에서 SQLite 연결을 만들고 닫는다."""

from contextlib import closing

from PySide6.QtCore import QObject, QRunnable, Signal

from small_stream_research_tool.database import connect_database
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
