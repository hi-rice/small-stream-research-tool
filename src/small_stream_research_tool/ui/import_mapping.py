"""Phase 10C 컬럼 매핑·관리코드/Import Preview의 읽기 전용 화면."""

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from small_stream_research_tool.models.import_mapping_workflow import MappingWorkflowState
from small_stream_research_tool.ui.workers import ImportMappingTask


class ImportMappingView(QWidget):
    back_requested = Signal()

    def __init__(self, db_path, user_id, workspace_dir=None):
        super().__init__()
        self.db_path = db_path
        self.user_id = user_id
        self.workspace_dir = workspace_dir
        self.pool = QThreadPool.globalInstance()
        self._generation = 0
        self._closed = False
        self._tasks = set()
        self.state = None
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("importScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("importContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 26, 32, 32)
        layout.setSpacing(16)
        title = QLabel("Excel 가져오기")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        self.step = QLabel("파일 구조 완료  ›  컬럼 매핑  ›  Preview  ›  Import (다음 단계)")
        self.step.setObjectName("pageSubtitle")
        self.step.setWordWrap(True)
        layout.addWidget(self.step)
        self.status = QLabel("저장된 파일 구조와 연구 사전을 확인하는 중입니다.")
        self.status.setObjectName("secondaryText")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        mapping_card = QFrame()
        mapping_card.setObjectName("card")
        mapping_layout = QVBoxLayout(mapping_card)
        mapping_layout.setContentsMargins(18, 16, 18, 16)
        mapping_layout.setSpacing(10)
        mapping_title = QLabel("컬럼 매핑")
        mapping_title.setObjectName("sectionTitle")
        mapping_layout.addWidget(mapping_title)
        note = QLabel(
            "자동 매핑은 등록된 별칭의 정확한 일치 결과입니다. "
            "단위가 있는 항목은 원본 단위 확인이 필요합니다."
        )
        note.setObjectName("secondaryText")
        note.setWordWrap(True)
        mapping_layout.addWidget(note)
        scope_line = QHBoxLayout()
        self.scope = QComboBox()
        self.scope.addItem("자료 범위: 일반 Excel (공통 별칭)", None)
        self.scope.addItem("자료 범위: 2024 전국 연구자료", "NATIONAL_2024")
        scope_line.addWidget(self.scope)
        self.scope_button = QPushButton("자료 범위 적용")
        self.scope_button.clicked.connect(self._set_scope)
        scope_line.addWidget(self.scope_button)
        scope_line.addStretch()
        mapping_layout.addLayout(scope_line)
        self.summary = QLabel("원본 열을 확인하는 중입니다.")
        self.summary.setObjectName("secondaryText")
        mapping_layout.addWidget(self.summary)
        self.mapping_table = QTableWidget(0, 5)
        self.mapping_table.setHorizontalHeaderLabels(
            ("원본 열", "원본 헤더", "매핑 상태", "표준 항목", "기준 단위")
        )
        self.mapping_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.mapping_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.mapping_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.mapping_table.verticalHeader().hide()
        self.mapping_table.setMinimumHeight(250)
        for index, width in enumerate((85, 260, 150, 220, 110)):
            self.mapping_table.horizontalHeader().setSectionResizeMode(
                index, QHeaderView.ResizeMode.Interactive
            )
            self.mapping_table.setColumnWidth(index, width)
        self.mapping_table.itemSelectionChanged.connect(self._controls)
        mapping_layout.addWidget(self.mapping_table)
        actions = QVBoxLayout()
        target_line = QHBoxLayout()
        self.target = QComboBox()
        self.target.setMinimumWidth(260)
        target_line.addWidget(self.target, 1)
        actions.addLayout(target_line)
        button_line = QHBoxLayout()
        self.map_button = QPushButton("선택 항목 매핑")
        self.map_button.clicked.connect(lambda: self._change("map"))
        button_line.addWidget(self.map_button)
        self.exclude_button = QPushButton("매핑 제외")
        self.exclude_button.clicked.connect(lambda: self._change("exclude"))
        button_line.addWidget(self.exclude_button)
        self.clear_button = QPushButton("미매핑으로 변경")
        self.clear_button.clicked.connect(lambda: self._change("clear"))
        button_line.addWidget(self.clear_button)
        button_line.addStretch()
        actions.addLayout(button_line)
        mapping_layout.addLayout(actions)
        self.auto_button = QPushButton("자동 매핑 다시 적용")
        self.auto_button.clicked.connect(lambda: self._change("auto"))
        mapping_layout.addWidget(self.auto_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(mapping_card)

        preview_card = QFrame()
        preview_card.setObjectName("card")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(18, 16, 18, 16)
        preview_layout.setSpacing(10)
        preview_title = QLabel("관리코드 검증 · Import Preview")
        preview_title.setObjectName("sectionTitle")
        preview_layout.addWidget(preview_title)
        self.preview_button = QPushButton("관리코드 검증 및 Preview 생성")
        self.preview_button.setObjectName("primaryButton")
        self.preview_button.clicked.connect(self._preview)
        preview_layout.addWidget(self.preview_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.preview_summary = QLabel("현재 매핑으로 Preview를 생성해야 합니다.")
        self.preview_summary.setObjectName("secondaryText")
        self.preview_summary.setWordWrap(True)
        preview_layout.addWidget(self.preview_summary)
        self.preview_table = QTableWidget(0, 5)
        self.preview_table.setHorizontalHeaderLabels(
            ("Excel 행", "관리코드", "소하천 상태", "준비 상태", "확인 사항")
        )
        self.preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.preview_table.verticalHeader().hide()
        self.preview_table.setMinimumHeight(220)
        for index, width in enumerate((90, 140, 130, 120, 500)):
            self.preview_table.horizontalHeader().setSectionResizeMode(
                index, QHeaderView.ResizeMode.Interactive
            )
            self.preview_table.setColumnWidth(index, width)
        preview_layout.addWidget(self.preview_table)
        layout.addWidget(preview_card)

        footer = QHBoxLayout()
        self.back_button = QPushButton("이전: 파일 구조")
        self.back_button.clicked.connect(self.back_requested.emit)
        footer.addWidget(self.back_button)
        footer.addStretch()
        self.next_button = QPushButton("다음: Import 실행")
        self.next_button.setEnabled(False)
        self.next_button.setToolTip("실제 Import 실행은 Phase 10D에서 연결됩니다.")
        footer.addWidget(self.next_button)
        layout.addLayout(footer)
        layout.addStretch()
        self.scroll_area.setWidget(content)
        outer.addWidget(self.scroll_area)
        self._controls()

    def open_workflow(self, source):
        self.state = None
        self.mapping_table.setRowCount(0)
        self.preview_table.setRowCount(0)
        self.preview_summary.setText("현재 매핑으로 Preview를 생성해야 합니다.")
        self._controls()
        self._submit("start", (source, self.user_id), "파일 구조와 연구 사전을 확인하는 중입니다.")

    def resume_workflow(self):
        self.state = None
        self.mapping_table.setRowCount(0)
        self.preview_table.setRowCount(0)
        self.preview_summary.setText("현재 매핑으로 Preview를 다시 생성해야 합니다.")
        self._controls()
        self._submit("resume", (self.user_id,), "저장된 매핑을 다시 확인하는 중입니다.")

    def _change(self, action):
        if self.state is None:
            return
        row = self.mapping_table.currentRow()
        if row < 0 and action != "auto":
            return
        index = 0 if action == "auto" else self.state.rows[row].index
        target_id = self.target.currentData() if action == "map" else None
        self._submit(
            "update",
            (self.state, index, action, target_id, self.user_id),
            "매핑을 저장하는 중입니다.",
        )

    def _set_scope(self):
        if self.state is not None:
            self._submit(
                "set_scope",
                (self.state, self.scope.currentData(), self.user_id),
                "선택한 자료 범위의 별칭을 확인하는 중입니다.",
            )

    def _preview(self):
        if self.state is not None:
            self._submit("preview", (self.state, self.user_id), "전체 행을 검증하는 중입니다.")

    def _submit(self, operation, args, message):
        self._generation += 1
        token = self._generation
        self.status.setText(message)
        self._controls(busy=True)
        task = ImportMappingTask(self.db_path, self.workspace_dir, token, operation, args)
        self._tasks.add(task)
        task.signals.finished.connect(
            lambda generation, result, error, current=task: self._result(
                current, generation, result, error
            )
        )
        self.pool.start(task)

    def _result(self, task, generation, result, error):
        self._tasks.discard(task)
        if self._closed or generation != self._generation:
            return
        if error or not isinstance(result, MappingWorkflowState):
            self.status.setText(error or "작업을 완료하지 못했습니다.")
            self._controls()
            return
        self.state = result
        self._show_mapping()
        self._show_preview()
        self._controls()
        self.status.setText("매핑 상태를 확인했습니다.")

    def _show_mapping(self):
        state = self.state
        self.scope.blockSignals(True)
        self.scope.setCurrentIndex(1 if state.source_scope == "NATIONAL_2024" else 0)
        self.scope.blockSignals(False)
        self.target.clear()
        for candidate in state.candidates:
            self.target.addItem(
                f"{candidate.category} · {candidate.label} ({candidate.unit})",
                candidate.dictionary_id,
            )
        self.mapping_table.blockSignals(True)
        self.mapping_table.setRowCount(len(state.rows))
        for row, entry in enumerate(state.rows):
            for column, value in enumerate(
                (entry.letter, entry.header, entry.status, entry.target, entry.unit)
            ):
                self.mapping_table.setItem(row, column, QTableWidgetItem(value))
        self.mapping_table.clearSelection()
        self.mapping_table.blockSignals(False)
        unmapped = sum(entry.status == "미매핑" for entry in state.rows)
        review = sum(entry.status == "확인 필요" for entry in state.rows)
        excluded = sum(entry.status == "가져오지 않음" for entry in state.rows)
        self.summary.setText(
            f"원본 열 {len(state.rows)}개 · 미매핑 {unmapped}개 · "
            f"확인 필요 {review}개 · 제외 {excluded}개"
        )

    def _show_preview(self):
        self.preview_table.setRowCount(0)
        preview = self.state.preview
        if preview is None:
            self.preview_summary.setText("현재 매핑으로 Preview를 생성해야 합니다.")
            return
        ready = (
            "Import 준비 검토 가능" if preview.ready_for_import_preparation else "차단 행 확인 필요"
        )
        self.preview_summary.setText(
            f"전체 {preview.total}행 검증 · 준비 가능 {preview.ready}행 · "
            f"차단 {preview.blocked}행 · 제외 {preview.excluded}행 · "
            f"화면에는 최대 {len(preview.displayed)}행만 표시 · {ready} · "
            f"원본 단위 확인 필요 항목 {preview.unit_review_count}개"
        )
        self.preview_table.setRowCount(len(preview.displayed))
        for row, item in enumerate(preview.displayed):
            for column, value in enumerate(
                (
                    str(item.source_row),
                    item.stream_code,
                    item.identity_status,
                    item.preparation_status,
                    "; ".join(item.issues) if item.issues else "—",
                )
            ):
                self.preview_table.setItem(row, column, QTableWidgetItem(value))

    def _controls(self, busy=False):
        row = self.mapping_table.currentRow()
        selected = self.state is not None and 0 <= row < len(self.state.rows)
        selectable = selected and not self.state.rows[row].sensitive
        self.target.setEnabled(bool(selectable and not busy))
        self.map_button.setEnabled(bool(selectable and self.target.count() and not busy))
        self.exclude_button.setEnabled(bool(selectable and not busy))
        self.clear_button.setEnabled(bool(selectable and not busy))
        self.auto_button.setEnabled(bool(self.state and not busy))
        self.scope.setEnabled(bool(self.state and not busy))
        self.scope_button.setEnabled(bool(self.state and not busy))
        self.preview_button.setEnabled(bool(self.state and not busy))
        self.back_button.setEnabled(not busy)

    def deactivate(self):
        self._generation += 1

    def closeEvent(self, event):
        self._closed = True
        self._generation += 1
        super().closeEvent(event)
