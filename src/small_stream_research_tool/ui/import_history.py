"""Safe paged Import history and explicit finalize recovery UI."""

from PySide6.QtCore import QThreadPool, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from small_stream_research_tool.models.phase10_read import ImportHistoryPage, PageRequest
from small_stream_research_tool.ui.workers import ImportExecutionTask, Phase10QueryTask


class ImportHistoryView(QWidget):
    back_requested = Signal()
    mutation_state_changed = Signal(bool)

    def __init__(self, db_path, user_id, workspace_dir=None):
        super().__init__()
        self.db_path = db_path
        self.workspace_dir = workspace_dir
        self.user_id = user_id
        self.pool = QThreadPool.globalInstance()
        self._generation = 0
        self._closed = False
        self._tasks = set()
        self._mutating = False
        self.page = 1
        self.page_size = 25
        self.result = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 26, 32, 32)
        title = QLabel("Import 이력")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        self.status = QLabel("가져오기 이력을 조회합니다.")
        self.status.setObjectName("secondaryText")
        layout.addWidget(self.status)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ("파일명", "Sheet", "상태", "시작", "완료", "저장", "거부", "점검")
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().hide()
        for column in range(8):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        back = QPushButton("Excel 가져오기로 돌아가기")
        back.clicked.connect(self.back_requested.emit)
        actions.addWidget(back)
        self.prev = QPushButton("이전")
        self.prev.clicked.connect(lambda: self._move(-1))
        actions.addWidget(self.prev)
        self.page_label = QLabel("0 / 0 페이지 · 0건")
        actions.addWidget(self.page_label)
        self.next = QPushButton("다음")
        self.next.clicked.connect(lambda: self._move(1))
        actions.addWidget(self.next)
        self.recover = QPushButton("상태 복구")
        self.recover.clicked.connect(self._recover)
        actions.addWidget(self.recover)
        actions.addStretch()
        layout.addLayout(actions)

    def activate(self):
        self.refresh()

    def refresh(self):
        self._generation += 1
        token = self._generation
        task = Phase10QueryTask(
            self.db_path,
            token,
            "list_import_history",
            ((PageRequest(self.page, self.page_size),), {}),
        )
        self._tasks.add(task)
        task.signals.finished.connect(
            lambda generation, result, error, current=task: self._loaded(
                current, generation, result, error
            )
        )
        self.pool.start(task)

    def _loaded(self, task, generation, result, error):
        self._tasks.discard(task)
        if self._closed or generation != self._generation:
            return
        if error or not isinstance(result, ImportHistoryPage):
            self.status.setText(error or "Import 이력을 불러오지 못했습니다.")
            return
        self.result = result
        self.table.setRowCount(len(result.items))
        labels = {"SUCCESS": "완료", "FAILED": "실패", "RUNNING": "상태 점검 필요"}
        for row, item in enumerate(result.items):
            values = (
                item.file_name,
                item.sheet_name or "—",
                labels.get(item.status, item.status),
                item.started_at,
                item.finished_at or "—",
                "—" if item.accepted_rows is None else str(item.accepted_rows),
                "—" if item.rejected_rows is None else str(item.rejected_rows),
                "점검 필요" if item.recovery_state != "NONE" else "—",
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        pages = result.total_pages
        self.page_label.setText(
            f"{result.page if pages else 0} / {pages} 페이지 · {result.total_count}건"
        )
        self.prev.setEnabled(result.page > 1)
        self.next.setEnabled(result.page < pages)
        self.status.setText(
            "Import 이력을 확인했습니다." if result.items else "Import 이력이 없습니다."
        )

    def _move(self, amount):
        if self.result is None:
            return
        target = self.page + amount
        if 1 <= target <= max(1, self.result.total_pages):
            self.page = target
            self.refresh()

    def _recover(self):
        row = self.table.currentRow()
        if row < 0 or self.result is None or self.result.items[row].status != "RUNNING":
            self.status.setText("상태 점검이 필요한 이력을 선택해 주세요.")
            return
        self._mutating = True
        self.mutation_state_changed.emit(True)
        self._generation += 1
        token = self._generation
        task = ImportExecutionTask(
            self.db_path,
            self.workspace_dir,
            token,
            "recover",
            (self.page, self.page_size, row, self.user_id),
        )
        self._tasks.add(task)
        task.signals.finished.connect(
            lambda generation, result, error, current=task: self._recovered(
                current, generation, result, error
            )
        )
        self.pool.start(task)

    def _recovered(self, task, generation, result, error):
        self._tasks.discard(task)
        self._mutating = False
        self.mutation_state_changed.emit(False)
        if self._closed or generation != self._generation:
            return
        self.status.setText(error or result)
        self.refresh()

    def deactivate(self):
        if not self._mutating:
            self._generation += 1

    def closeEvent(self, event):
        if not self._mutating:
            self._closed = True
            self._generation += 1
        super().closeEvent(event)
