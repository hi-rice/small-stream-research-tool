"""09 소하천 조회의 read-only 상세·특성·QC·출처 화면."""

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabBar,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from small_stream_research_tool.ui.components import StatusBadge, StatusBadgeDelegate
from small_stream_research_tool.ui.presentation import (
    CURRENT_TEXT,
    REVIEW_TEXT,
    SEVERITY_TEXT,
    SOURCE_TEXT,
    STATUS_TEXT,
    display_timestamp,
    display_value,
)
from small_stream_research_tool.ui.table_model import CharacteristicTableModel
from small_stream_research_tool.ui.theme import (
    CHARACTERISTIC_COLUMN_WIDTHS,
    COMPACT_DETAIL_BREAKPOINT,
    HISTORY_COLUMN_WIDTHS,
    QC_COLUMN_WIDTHS,
)
from small_stream_research_tool.ui.workers import QueryTask

CATEGORY_ORDER = (
    "basic_characteristic",
    "basin_stream_characteristic",
    "soil_characteristic",
    "land_use",
    "planning_design",
)
CATEGORY_LABELS = {
    "basic_characteristic": "기본 특성",
    "basin_stream_characteristic": "유역·하천",
    "soil_characteristic": "토양",
    "land_use": "토지이용",
    "planning_design": "계획정보",
}


class StreamDetailView(QWidget):
    back_requested = Signal()

    def __init__(self, db_path, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.pool = QThreadPool.globalInstance()
        self._tasks = {}
        self._generation = 0
        self._closed = False
        self._detail = None
        self._basic_mode = None
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("detailScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.detail_content = QWidget()
        self.detail_content.setObjectName("detailContent")
        self.detail_content.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.scroll_area.setWidget(self.detail_content)
        outer.addWidget(self.scroll_area)

        layout = QVBoxLayout(self.detail_content)
        layout.setContentsMargins(32, 20, 32, 22)
        layout.setSpacing(10)
        self.back = QPushButton("← 소하천 목록")
        self.back.setObjectName("compactButton")
        self.back.clicked.connect(self.back_requested)
        layout.addWidget(self.back, 0, Qt.AlignmentFlag.AlignLeft)
        heading = QHBoxLayout()
        heading_text = QVBoxLayout()
        heading_text.setSpacing(2)
        self.title = QLabel("소하천 상세")
        self.title.setObjectName("pageTitle")
        self.location = QLabel("소하천을 선택하세요.")
        self.location.setObjectName("pageSubtitle")
        self.location.setWordWrap(True)
        heading_text.addWidget(self.title)
        heading_text.addWidget(self.location)
        heading.addLayout(heading_text)
        heading.addStretch()
        self.stream_qc_badge = StatusBadge("—")
        heading.addWidget(self.stream_qc_badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(heading)
        self.status = QLabel("소하천을 선택하세요.")
        self.status.setObjectName("secondaryText")
        layout.addWidget(self.status)
        layout.addWidget(self._basic_card())
        self.summary = QLabel("연구 활용 분류를 확인할 수 있습니다.")
        self.summary.setObjectName("secondaryText")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.category = QTabBar()
        self.category.setObjectName("categoryTabs")
        self.category.setExpanding(False)
        self.category.setUsesScrollButtons(True)
        self.category.setElideMode(Qt.TextElideMode.ElideNone)
        self.category.setMinimumHeight(40)
        self.category.currentChanged.connect(self._filter_category)
        layout.addWidget(self.category)

        self.model = CharacteristicTableModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setHorizontalScrollMode(QTableView.ScrollMode.ScrollPerPixel)
        self.table.setMinimumHeight(260)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate(CHARACTERISTIC_COLUMN_WIDTHS):
            self.table.setColumnWidth(column, width)
        self.table.setItemDelegateForColumn(3, StatusBadgeDelegate(self.table))
        self.table.selectionModel().currentRowChanged.connect(self._selected)
        layout.addWidget(self.table, 2)
        self._add_selected_header(layout)
        self.detail_tabs = QTabWidget()
        self.detail_tabs.setMinimumHeight(240)
        self.detail_tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.detail_tabs.addTab(self._value_detail_tab(), "값 상세")
        self.detail_tabs.addTab(self._qc_tab(), "QC · 검토")
        self.detail_tabs.addTab(self._history_tab(), "값 이력")
        layout.addWidget(self.detail_tabs, 2)

    def _basic_card(self):
        card = QFrame()
        card.setObjectName("card")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)
        title = QLabel("기본정보")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)
        self.basic_grid = QGridLayout()
        self.basic_grid.setHorizontalSpacing(18)
        self.basic_grid.setVerticalSpacing(7)
        self.basic_labels = {}
        self.basic_fields = []
        fields = (
            ("stream_code", "관리코드"),
            ("stream_name", "소하천명"),
            ("province", "시·도"),
            ("city_county", "시·군·구"),
            ("town", "읍·면·동"),
            ("river_system", "수계"),
            ("source_address", "시점 주소"),
            ("source_coordinates", "시점 좌표"),
            ("end_address", "종점 주소"),
            ("end_coordinates", "종점 좌표"),
        )
        for key, caption in fields:
            label = QLabel(caption)
            label.setObjectName("fieldLabel")
            value = QLabel("—")
            value.setObjectName("fieldValue")
            value.setWordWrap(True)
            self.basic_labels[key] = value
            self.basic_fields.append((label, value))
        outer.addLayout(self.basic_grid)
        self._set_basic_mode(self.width() >= COMPACT_DETAIL_BREAKPOINT)
        return card

    def _set_basic_mode(self, wide):
        mode = "wide" if wide else "compact"
        if mode == self._basic_mode or not hasattr(self, "basic_fields"):
            return
        self._basic_mode = mode
        for label, value in self.basic_fields:
            self.basic_grid.removeWidget(label)
            self.basic_grid.removeWidget(value)
        if wide:
            for index, (label, value) in enumerate(self.basic_fields):
                row, group = divmod(index, 2)
                self.basic_grid.addWidget(label, row, group * 2)
                self.basic_grid.addWidget(value, row, group * 2 + 1)
            self.basic_grid.setColumnStretch(1, 1)
            self.basic_grid.setColumnStretch(3, 1)
        else:
            for row, (label, value) in enumerate(self.basic_fields):
                self.basic_grid.addWidget(label, row, 0)
                self.basic_grid.addWidget(value, row, 1)
            self.basic_grid.setColumnStretch(1, 1)

    def _add_selected_header(self, layout):
        row = QHBoxLayout()
        copy = QVBoxLayout()
        copy.setSpacing(2)
        self.selection_title = QLabel("특성항목을 선택하세요")
        self.selection_title.setObjectName("sectionTitle")
        self.selection_value = QLabel("현재 사용값과 QC·이력을 확인할 항목을 선택하세요.")
        self.selection_value.setObjectName("secondaryText")
        copy.addWidget(self.selection_title)
        copy.addWidget(self.selection_value)
        row.addLayout(copy)
        row.addStretch()
        self.selection_badge = StatusBadge("—")
        row.addWidget(self.selection_badge)
        layout.addLayout(row)

    def _value_detail_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(20, 16, 20, 16)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(8)
        self.detail_labels = {}
        for key, label in (
            ("name", "항목"),
            ("value", "현재 사용값"),
            ("unit", "단위"),
            ("category", "분류"),
            ("current", "현재값 상태"),
            ("qc", "자동 데이터 상태"),
            ("source", "출처 유형"),
        ):
            value = QLabel("—")
            value.setObjectName("fieldValue")
            value.setWordWrap(True)
            self.detail_labels[key] = value
            form.addRow(label, value)
        return tab

    def _qc_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        self.qc_empty = QLabel("현재 사용값에 활성 QC 문제가 없습니다.")
        self.qc_empty.setObjectName("secondaryText")
        self.qc_table = self._table(("문제 유형", "심각도", "연구자 검토", "설명"))
        header = self.qc_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate(QC_COLUMN_WIDTHS):
            self.qc_table.setColumnWidth(column, width)
        layout.addWidget(self.qc_empty)
        layout.addWidget(self.qc_table, 1)
        return tab

    def _history_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        self.history_empty = QLabel("등록된 값 이력이 없습니다.")
        self.history_empty.setObjectName("secondaryText")
        self.history_table = self._table(
            ("값", "단위", "출처", "활성", "현재 사용", "등록 시각", "출처 요약")
        )
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate(HISTORY_COLUMN_WIDTHS):
            self.history_table.setColumnWidth(column, width)
        layout.addWidget(self.history_empty)
        layout.addWidget(self.history_table, 1)
        return tab

    @staticmethod
    def _table(headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setShowGrid(False)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(38)
        return table

    def load_stream(self, stream_code):
        self._generation += 1
        token = self._generation
        self._detail = None
        self.model.set_rows(())
        while self.category.count():
            self.category.removeTab(0)
        self.status.setText("상세정보를 조회하고 있습니다.")
        task = QueryTask(self.db_path, token, "get_research_stream_detail", ((stream_code,), {}))
        key = id(task)
        self._tasks[key] = task

        def deliver(generation, result, error):
            self._tasks.pop(key, None)
            if not self._closed:
                self._result(generation, result, error)

        task.signals.finished.connect(deliver)
        self.pool.start(task)

    def _result(self, token, result, error):
        if token != self._generation:
            return
        if error:
            self.status.setText("상세정보 조회 중 오류가 발생했습니다.")
            return
        if result is None:
            self.status.setText("선택한 소하천을 찾을 수 없습니다.")
            return
        self._detail = result
        self._show_basic(result.basic)
        if result.dictionary_state == "UNINITIALIZED":
            self.status.setText("연구 사전이 초기화되지 않았습니다.")
            return
        self.status.setText("읽기 전용 상세정보")
        categories = {row.category_key for row in result.characteristics}
        for key in CATEGORY_ORDER:
            if key in categories:
                index = self.category.addTab(CATEGORY_LABELS[key])
                self.category.setTabData(index, key)
        representative = sum(row.representative_six for row in result.characteristics)
        focus = sum(row.focus_nine for row in result.characteristics)
        self.summary.setText(
            f"연구 활용 분류 · 대표 연구항목 {representative}개 · "
            f"전국 분석 중점항목 {focus}개 (그룹 항목은 합산하지 않음)"
        )
        self._filter_category()

    def _show_basic(self, basic):
        self.title.setText(basic.stream_name)
        location = " > ".join(filter(None, (basic.province, basic.city_county, basic.town)))
        self.location.setText(f"{basic.stream_code} · {location or '행정구역 미등록'}")
        self.stream_qc_badge.set_status(STATUS_TEXT.get(basic.qc_display_state, "상태 확인 필요"))
        for key in (
            "stream_code",
            "stream_name",
            "province",
            "city_county",
            "town",
            "river_system",
            "source_address",
            "end_address",
        ):
            self.basic_labels[key].setText(str(getattr(basic, key) or "미등록"))
        self.basic_labels["source_coordinates"].setText(
            self._coordinates(basic.source_latitude, basic.source_longitude)
        )
        self.basic_labels["end_coordinates"].setText(
            self._coordinates(basic.end_latitude, basic.end_longitude)
        )

    @staticmethod
    def _coordinates(latitude, longitude):
        if latitude is None or longitude is None:
            return "미등록"
        return f"{latitude}, {longitude}"

    def _filter_category(self, _index=None):
        if self._detail is None:
            return
        key = self.category.tabData(self.category.currentIndex())
        rows = tuple(row for row in self._detail.characteristics if row.category_key == key)
        self.model.set_rows(rows)
        if rows:
            self.table.selectRow(0)

    def _selected(self, current, _previous):
        if not current.isValid():
            return
        row = self.model.row(current.row())
        provenance = row.provenance
        current_text = CURRENT_TEXT.get(row.current_use_status, "상태 확인 필요")
        qc_text = STATUS_TEXT.get(row.qc_display_state, "해당 현재 사용값 없음")
        self.selection_title.setText(row.standard_name)
        value = display_value(row.current_value)
        self.selection_value.setText(f"현재 사용값 {value} {row.unit_display or ''}".rstrip())
        self.selection_badge.set_status(current_text)
        self.detail_labels["name"].setText(row.standard_name)
        self.detail_labels["value"].setText(value)
        self.detail_labels["unit"].setText(row.unit_display or "—")
        self.detail_labels["category"].setText(row.category_name)
        self.detail_labels["current"].setText(current_text)
        self.detail_labels["qc"].setText(qc_text)
        self.detail_labels["source"].setText(
            SOURCE_TEXT.get(provenance.classification, "—") if provenance else "—"
        )
        self._fill_qc(row.qc_items)
        self._fill_history(row.value_history)

    def _fill_qc(self, rows):
        self.qc_table.setRowCount(len(rows))
        self.qc_empty.setVisible(not rows)
        self.qc_table.setVisible(bool(rows))
        for index, row in enumerate(rows):
            values = (
                row.issue_type,
                SEVERITY_TEXT.get(row.severity, "상태 확인 필요"),
                REVIEW_TEXT.get(row.review_status, "상태 확인 필요"),
                row.description,
            )
            for column, value in enumerate(values):
                self.qc_table.setItem(index, column, QTableWidgetItem(value))

    def _fill_history(self, rows):
        self.history_table.setRowCount(len(rows))
        self.history_empty.setVisible(not rows)
        self.history_table.setVisible(bool(rows))
        for index, row in enumerate(rows):
            values = (
                str(row.value),
                row.unit_display or "—",
                SOURCE_TEXT.get(row.source_classification, "기타 등록 자료"),
                "활성" if row.is_active else "비활성",
                "예" if row.is_current_use else "아니요",
                display_timestamp(row.created_at),
                row.provenance_summary,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if row.is_current_use:
                    item.setBackground(QColor("#EDF3FF"))
                self.history_table.setItem(index, column, item)

    def closeEvent(self, event):
        self._closed = True
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._set_basic_mode(event.size().width() >= COMPACT_DETAIL_BREAKPOINT)
