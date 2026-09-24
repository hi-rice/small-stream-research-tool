"""Phase 10D final review and mutation screen."""

from PySide6.QtCore import QThreadPool, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from small_stream_research_tool.models.import_execution_workflow import (
    ImportExecutionOutcome,
    ImportExecutionPlan,
)
from small_stream_research_tool.ui.workers import ImportExecutionTask


class ImportExecutionView(QWidget):
    back_requested = Signal()
    history_requested = Signal()
    import_completed = Signal()
    mutation_state_changed = Signal(bool)

    def __init__(self, db_path, user_id, workspace_dir=None):
        super().__init__()
        self.db_path = db_path
        self.user_id = user_id
        self.workspace_dir = workspace_dir
        self.pool = QThreadPool.globalInstance()
        self._generation = 0
        self._closed = False
        self._tasks = set()
        self._mutating = False
        self.state = None
        self.plan = None
        self._build_ui()

    @property
    def mutation_active(self):
        return self._mutating

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 26, 32, 32)
        layout.setSpacing(16)
        title = QLabel("Import 실행")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "검토한 Preview와 원본·사전·단위 확인 상태를 다시 검증한 뒤 데이터를 저장합니다."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        self.status = QLabel("실행 조건을 확인하는 중입니다.")
        self.status.setObjectName("secondaryText")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        heading = QLabel("최종 실행 요약")
        heading.setObjectName("sectionTitle")
        card_layout.addWidget(heading)
        grid = QGridLayout()
        self.values = {}
        labels = (
            ("file", "파일명"),
            ("sheet", "Sheet"),
            ("rows", "전체 / 저장 / 제외"),
            ("streams", "신규 / 기존 소하천"),
            ("values", "저장 특성값"),
            ("columns", "연구항목 / 제외 컬럼"),
            ("units", "원본 단위 확인"),
            ("duplicate", "동일 파일 이력"),
        )
        for row, (key, text) in enumerate(labels):
            label = QLabel(text)
            label.setObjectName("fieldLabel")
            value = QLabel("—")
            value.setWordWrap(True)
            self.values[key] = value
            grid.addWidget(label, row, 0)
            grid.addWidget(value, row, 1)
        card_layout.addLayout(grid)
        layout.addWidget(card)

        result_card = QFrame()
        result_card.setObjectName("card")
        result_layout = QVBoxLayout(result_card)
        result_title = QLabel("실행 상태")
        result_title.setObjectName("sectionTitle")
        result_layout.addWidget(result_title)
        self.result = QLabel("아직 실행하지 않았습니다.")
        self.result.setWordWrap(True)
        result_layout.addWidget(self.result)
        layout.addWidget(result_card)

        actions = QHBoxLayout()
        self.back_button = QPushButton("이전: Preview")
        self.back_button.clicked.connect(self.back_requested.emit)
        actions.addWidget(self.back_button)
        self.history_button = QPushButton("Import 이력")
        self.history_button.clicked.connect(self.history_requested.emit)
        actions.addWidget(self.history_button)
        actions.addStretch()
        self.execute_button = QPushButton("가져오기 실행")
        self.execute_button.setObjectName("primaryButton")
        self.execute_button.clicked.connect(self.execute_import)
        actions.addWidget(self.execute_button)
        layout.addLayout(actions)
        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self._controls()

    def open_workflow(self, state):
        if self._mutating:
            return
        self.state = state
        self.plan = None
        self.result.setText("아직 실행하지 않았습니다.")
        self._submit("prepare", (state, self.user_id), "실행 직전 무결성을 확인하는 중입니다.")

    def execute_import(self):
        if self._mutating or self.plan is None:
            return
        duplicate = self.plan.summary.duplicate_success
        if duplicate:
            answer = QMessageBox.question(
                self,
                "동일 파일 재가져오기",
                "동일한 내용의 파일을 이전에 가져온 기록이 있습니다.\n다시 가져오시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.status.setText("재가져오기를 취소했습니다.")
                return
        answer = QMessageBox.question(
            self,
            "가져오기 실행",
            "검토한 Preview 기준으로 데이터를 가져옵니다.\n"
            "저장이 시작된 뒤에는 작업을 강제로 취소할 수 없습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.status.setText("가져오기 실행을 취소했습니다.")
            return
        self._mutating = True
        self.mutation_state_changed.emit(True)
        self._submit(
            "execute",
            (self.state, self.user_id, duplicate, True),
            "저장 중입니다. 작업을 강제로 종료하지 마세요.",
        )

    def _submit(self, operation, args, message):
        self._generation += 1
        token = self._generation
        self.status.setText(message)
        self._controls(busy=True)
        task = ImportExecutionTask(self.db_path, self.workspace_dir, token, operation, args)
        self._tasks.add(task)
        task.signals.finished.connect(
            lambda generation, result, error, current=task: self._finished(
                current, operation, generation, result, error
            )
        )
        self.pool.start(task)

    def _finished(self, task, operation, generation, result, error):
        self._tasks.discard(task)
        if operation == "execute" and self._mutating:
            self._mutating = False
            self.mutation_state_changed.emit(False)
        if self._closed or generation != self._generation:
            return
        if error:
            self.status.setText(error)
            self._controls()
            return
        if operation == "prepare" and isinstance(result, ImportExecutionPlan):
            self.plan = result
            self.state = result.workflow_state
            self._show_plan(result)
            self.status.setText(
                "실행 조건을 확인했습니다. 저장을 시작하려면 명시적으로 확인해 주세요."
            )
        elif operation == "execute" and isinstance(result, ImportExecutionOutcome):
            self.plan = None
            self.status.setText(result.message)
            self.result.setText(
                f"상태: {result.status} · 신규 {result.created_stream_count} · "
                f"기존 {result.reused_stream_count} · 특성값 {result.characteristic_value_count}"
            )
            if result.status == "SUCCESS":
                self.import_completed.emit()
        else:
            self.status.setText("가져오기 결과를 확인하지 못했습니다.")
        self._controls()

    def _show_plan(self, plan):
        value = plan.summary
        self.values["file"].setText(value.file_name)
        self.values["sheet"].setText(value.sheet_name)
        self.values["rows"].setText(
            f"{value.total_rows} / {value.ready_rows} / {value.excluded_rows}"
        )
        self.values["streams"].setText(f"{value.new_stream_rows} / {value.existing_stream_rows}")
        self.values["values"].setText(str(value.prepared_value_count))
        self.values["columns"].setText(
            f"{value.mapped_characteristic_count} / {value.excluded_column_count}"
        )
        self.values["units"].setText("확인 완료")
        self.values["duplicate"].setText(
            "이전 SUCCESS 있음 · 실행 시 재확인" if value.duplicate_success else "없음"
        )
        if value.recovery_required:
            self.status.setText("먼저 이전 가져오기 상태를 점검하거나 복구해야 합니다.")

    def _controls(self, busy=False):
        blocked = bool(self.plan and self.plan.summary.recovery_required)
        self.execute_button.setEnabled(
            bool(self.plan and not blocked and not busy and not self._mutating)
        )
        self.back_button.setEnabled(not self._mutating and not busy)
        self.history_button.setEnabled(not self._mutating)

    def deactivate(self):
        if not self._mutating:
            self._generation += 1

    def closeEvent(self, event):
        if not self._mutating:
            self._closed = True
            self._generation += 1
        super().closeEvent(event)
