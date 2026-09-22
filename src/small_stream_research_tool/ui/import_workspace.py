"""Phase 10B 파일·sheet·header 확인과 단일 Workspace 저장 화면."""

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from small_stream_research_tool.models.import_workflow import ImportWorkflowState
from small_stream_research_tool.ui.workers import ImportInspectionTask


class ImportWorkspaceView(QWidget):
    mapping_requested = Signal(object)

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
        subtitle = QLabel(
            "소하천 특성정보 Excel 파일의 구조를 확인하고 가져오기 작업을 준비합니다."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        file_card = QFrame()
        file_card.setObjectName("card")
        file_layout = QVBoxLayout(file_card)
        file_layout.setContentsMargins(18, 16, 18, 16)
        file_layout.setSpacing(10)
        file_title = QLabel("원본 파일")
        file_title.setObjectName("sectionTitle")
        file_layout.addWidget(file_title)
        file_actions = QHBoxLayout()
        self.file_name = QLabel("선택된 파일이 없습니다.")
        self.file_name.setObjectName("secondaryText")
        self.file_name.setWordWrap(True)
        file_actions.addWidget(self.file_name, 1)
        self.choose_button = QPushButton(".xlsx 파일 선택")
        self.choose_button.setObjectName("primaryButton")
        self.choose_button.clicked.connect(self.choose_file)
        file_actions.addWidget(self.choose_button)
        self.resume_button = QPushButton("저장된 작업 재개")
        self.resume_button.clicked.connect(self.resume_workspace)
        file_actions.addWidget(self.resume_button)
        file_layout.addLayout(file_actions)
        self.file_info = QLabel("")
        self.file_info.setObjectName("secondaryText")
        file_layout.addWidget(self.file_info)
        self.status = QLabel(".xlsx 파일을 선택하거나 저장된 작업을 재개하세요.")
        self.status.setObjectName("secondaryText")
        self.status.setWordWrap(True)
        file_layout.addWidget(self.status)
        self.duplicate_warning = QLabel("")
        self.duplicate_warning.setObjectName("warningText")
        self.duplicate_warning.setWordWrap(True)
        self.duplicate_warning.hide()
        file_layout.addWidget(self.duplicate_warning)
        layout.addWidget(file_card)

        sheet_card = QFrame()
        sheet_card.setObjectName("card")
        sheet_layout = QVBoxLayout(sheet_card)
        sheet_layout.setContentsMargins(18, 16, 18, 16)
        sheet_title = QLabel("Sheet 선택")
        sheet_title.setObjectName("sectionTitle")
        sheet_layout.addWidget(sheet_title)
        sheet_note = QLabel(
            "한 번에 하나의 worksheet만 선택합니다. 숨김 worksheet도 선택할 수 있습니다."
        )
        sheet_note.setObjectName("secondaryText")
        sheet_note.setWordWrap(True)
        sheet_layout.addWidget(sheet_note)
        self.sheets = QTableWidget(0, 5)
        self.sheets.setHorizontalHeaderLabels(("Sheet", "행", "열", "표시 상태", "유형"))
        self.sheets.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sheets.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sheets.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.sheets.verticalHeader().setVisible(False)
        self.sheets.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for index in range(1, 5):
            self.sheets.horizontalHeader().setSectionResizeMode(
                index, QHeaderView.ResizeMode.ResizeToContents
            )
        self.sheets.setMinimumHeight(170)
        self.sheets.itemSelectionChanged.connect(self._sheet_selected)
        sheet_layout.addWidget(self.sheets)
        layout.addWidget(sheet_card)

        structure_card = QFrame()
        structure_card.setObjectName("card")
        structure_layout = QVBoxLayout(structure_card)
        structure_layout.setContentsMargins(18, 16, 18, 16)
        structure_layout.setSpacing(10)
        structure_title = QLabel("헤더 구조")
        structure_title.setObjectName("sectionTitle")
        structure_layout.addWidget(structure_title)
        fields = QHBoxLayout()
        self.header_start = self._row_input(fields, "Header 시작행", 1)
        self.header_end = self._row_input(fields, "Header 종료행", 1)
        self.data_start = self._row_input(fields, "Data 시작행", 2)
        for field in (self.header_start, self.header_end, self.data_start):
            field.valueChanged.connect(self._structure_inputs_changed)
        fields.addStretch()
        structure_layout.addLayout(fields)
        self.structure_button = QPushButton("구조 확인")
        self.structure_button.clicked.connect(self.check_structure)
        structure_layout.addWidget(self.structure_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.headers = QTableWidget(0, 3)
        self.headers.setHorizontalHeaderLabels(("원본 열", "열 문자", "조합된 헤더"))
        self.headers.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.headers.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.headers.verticalHeader().setVisible(False)
        self.headers.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.headers.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.headers.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.headers.setColumnWidth(0, 90)
        self.headers.setColumnWidth(1, 90)
        self.headers.setColumnWidth(2, 520)
        self.headers.setMinimumHeight(190)
        structure_layout.addWidget(self.headers)
        layout.addWidget(structure_card)

        actions = QHBoxLayout()
        self.save_button = QPushButton("작업 저장")
        self.save_button.clicked.connect(self.save_workspace)
        actions.addWidget(self.save_button)
        actions.addStretch()
        self.next_button = QPushButton("다음: 컬럼 매핑")
        self.next_button.setObjectName("primaryButton")
        self.next_button.setEnabled(False)
        self.next_button.clicked.connect(self._next)
        actions.addWidget(self.next_button)
        layout.addLayout(actions)
        layout.addStretch()
        self.scroll_area.setWidget(content)
        outer.addWidget(self.scroll_area)
        self._set_controls(False)

    @staticmethod
    def _row_input(layout, title, initial):
        group = QVBoxLayout()
        label = QLabel(title)
        label.setObjectName("fieldLabel")
        field = QSpinBox()
        field.setRange(1, 1_048_577)
        field.setValue(initial)
        field.setMinimumWidth(105)
        group.addWidget(label)
        group.addWidget(field)
        layout.addLayout(group)
        return field

    def choose_file(self):
        path, _filter = QFileDialog.getOpenFileName(
            self, "Excel 파일 선택", "", "Excel Workbook (*.xlsx)"
        )
        if path:
            self.select_file(path)

    def select_file(self, path):
        """Dialog와 offscreen test가 공유하는 선택 경계."""
        self.state = None
        self.file_name.setText("파일 확인 중입니다.")
        self.file_info.clear()
        self.sheets.setRowCount(0)
        self.headers.setRowCount(0)
        self.duplicate_warning.hide()
        self._set_controls(False)
        self._submit("inspect", (path,), "파일과 workbook 구조를 확인하는 중입니다.")

    def resume_workspace(self):
        self.state = None
        self.file_name.setText("저장된 작업 확인 중입니다.")
        self.file_info.clear()
        self.sheets.setRowCount(0)
        self.headers.setRowCount(0)
        self.duplicate_warning.hide()
        self._set_controls(False)
        self._submit("resume", (self.user_id,), "저장된 작업과 원본 파일을 확인하는 중입니다.")

    def check_structure(self):
        if self.state is None or self.sheets.currentRow() < 0:
            self.status.setText("먼저 worksheet를 선택해 주세요.")
            return
        sheet = self.state.sheets[self.sheets.currentRow()]
        if not sheet.selectable:
            self.status.setText("해당 Sheet는 가져오기 대상이 아닙니다.")
            return
        self._invalidate_structure()
        self._set_controls(False)
        self._submit(
            "structure",
            (
                self.state,
                sheet.name,
                self.header_start.value(),
                self.header_end.value(),
                self.data_start.value(),
            ),
            "헤더 구조를 확인하는 중입니다.",
        )

    def save_workspace(self):
        if self.state is None or not self.state.columns:
            return
        self._set_controls(False)
        self._submit("save", (self.state, self.user_id), "작업을 저장하는 중입니다.")

    def _submit(self, operation, args, message):
        self._generation += 1
        token = self._generation
        self.status.setText(message)
        task = ImportInspectionTask(self.db_path, self.workspace_dir, token, operation, args)
        self._tasks.add(task)
        task.signals.finished.connect(
            lambda generation, result, error, current=task: self._result(
                current, operation, generation, result, error
            )
        )
        self.pool.start(task)

    def _result(self, task, operation, generation, result, error):
        self._tasks.discard(task)
        if self._closed or generation != self._generation:
            return
        if error or not isinstance(result, ImportWorkflowState):
            self.status.setText(error or "작업을 완료하지 못했습니다.")
            self._set_controls(bool(self.state))
            return
        self.state = result
        if operation in ("inspect", "resume"):
            self._show_workbook(result)
        if operation in ("structure", "resume"):
            self._show_headers(result)
        self._set_controls(True)
        if operation == "save":
            self.status.setText(
                "작업을 저장했습니다. 다음 단계에서 컬럼 매핑을 진행할 수 있습니다."
            )
        elif operation == "structure":
            self.status.setText("헤더 구조를 확인했습니다. 작업을 저장할 수 있습니다.")
        elif operation == "resume":
            self.status.setText("저장된 작업을 재개했습니다.")
        elif not any(sheet.selectable for sheet in result.sheets):
            self.status.setText("가져올 수 있는 worksheet가 없습니다.")
        else:
            self.status.setText("파일 확인 완료. Sheet와 헤더·데이터 행을 선택해 주세요.")

    def _show_workbook(self, state):
        self.file_name.setText(state.file_name)
        self.file_info.setText(
            f"파일 크기 {state.file_size:,} byte · SHA-256 확인 완료 · Sheet {len(state.sheets)}개"
        )
        self.sheets.blockSignals(True)
        self.sheets.setRowCount(len(state.sheets))
        for row, sheet in enumerate(state.sheets):
            values = (
                sheet.name,
                str(sheet.row_count or "—"),
                str(sheet.column_count or "—"),
                "숨김" if sheet.state != "visible" else "표시",
                "Worksheet" if sheet.kind == "worksheet" else "선택 불가 (Chart)",
            )
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if not sheet.selectable:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                self.sheets.setItem(row, column, item)
        self.sheets.clearSelection()
        if state.selected_sheet is None:
            for field in (self.header_start, self.header_end, self.data_start):
                field.blockSignals(True)
            self.header_start.setValue(1)
            self.header_end.setValue(1)
            self.data_start.setValue(2)
            for field in (self.header_start, self.header_end, self.data_start):
                field.blockSignals(False)
        if state.selected_sheet:
            row = next(
                (i for i, sheet in enumerate(state.sheets) if sheet.name == state.selected_sheet),
                -1,
            )
            if row >= 0:
                self.sheets.selectRow(row)
                for field in (self.header_start, self.header_end, self.data_start):
                    field.blockSignals(True)
                self.header_start.setValue(state.header_start_row)
                self.header_end.setValue(state.header_end_row)
                self.data_start.setValue(state.data_start_row)
                for field in (self.header_start, self.header_end, self.data_start):
                    field.blockSignals(False)
        self.sheets.blockSignals(False)
        successful = next((item for item in state.duplicates if item.status == "SUCCESS"), None)
        if successful:
            self.duplicate_warning.setText(
                "동일한 내용의 파일을 이전에 가져온 기록이 있습니다. "
                f"기존 파일: {successful.file_name}. 실제 재가져오기 전 다시 확인해야 합니다."
            )
            self.duplicate_warning.show()
        else:
            self.duplicate_warning.hide()

    def _show_headers(self, state):
        self.headers.setRowCount(len(state.columns))
        for row, column in enumerate(state.columns):
            for index, text in enumerate((str(column.index), column.letter, column.text)):
                self.headers.setItem(row, index, QTableWidgetItem(text))

    def _sheet_selected(self):
        self._invalidate_structure()

    def _structure_inputs_changed(self):
        self._invalidate_structure()

    def _invalidate_structure(self):
        self._generation += 1
        self.headers.setRowCount(0)
        if self.state is not None and self.state.columns:
            from dataclasses import replace

            self.state = replace(
                self.state,
                selected_sheet=None,
                header_start_row=None,
                header_end_row=None,
                data_start_row=None,
                columns=(),
                workspace_saved_at=None,
            )
        self._set_controls(bool(self.state))

    def _set_controls(self, available):
        self.sheets.setEnabled(available)
        selected = available and self.sheets.currentRow() >= 0
        if selected and self.state is not None:
            selected = self.state.sheets[self.sheets.currentRow()].selectable
        for field in (self.header_start, self.header_end, self.data_start):
            field.setEnabled(bool(selected))
        self.structure_button.setEnabled(bool(selected))
        self.save_button.setEnabled(bool(available and self.state and self.state.columns))
        self.next_button.setEnabled(
            bool(available and self.state and self.state.columns and self.state.workspace_saved_at)
        )

    def _next(self):
        if self.next_button.isEnabled() and self.state is not None:
            self.mapping_requested.emit(self.state)

    def activate(self):
        if self.state is None:
            self.status.setText(".xlsx 파일을 선택하거나 저장된 작업을 재개하세요.")

    def deactivate(self):
        self._generation += 1
        if self.state is None:
            self.status.setText(
                "확인 중이던 결과는 적용하지 않았습니다. 파일을 다시 선택해 주세요."
            )

    def closeEvent(self, event):
        self._closed = True
        self._generation += 1
        super().closeEvent(event)
