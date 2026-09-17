"""Figma 09 소하천 조회의 검색·목록·선택 요약 화면."""

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from small_stream_research_tool.models.stream_read import StreamListRequest
from small_stream_research_tool.ui.components import StatusBadge, StatusBadgeDelegate
from small_stream_research_tool.ui.presentation import SORT_FIELDS, STATUS_TEXT, display_timestamp
from small_stream_research_tool.ui.table_model import StreamListTableModel
from small_stream_research_tool.ui.theme import (
    RESULT_WORKSPACE_MIN_WIDTH,
    SEARCH_NARROW_BREAKPOINT,
    SEARCH_REFLOW_BREAKPOINT,
)
from small_stream_research_tool.ui.workers import QueryTask

PAGE_SIZE = 50


class StreamListView(QWidget):
    selected_stream = Signal(str)
    detail_requested = Signal(str)

    def __init__(self, db_path, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.pool = QThreadPool.globalInstance()
        self._tasks = {}
        self._generation = 0
        self._summary_generation = 0
        self._region_generation = {"province": 0, "city_county": 0, "town": 0}
        self._closed = False
        self.page = 1
        self.total_pages = 0
        self.sort_field = "stream_code"
        self.sort_direction = "ASC"
        self.selected_code = None
        self._layout_mode = None
        self._build()
        self.load_regions("province")
        self.refresh()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("listScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.content.setObjectName("listContent")
        self.scroll_area.setWidget(self.content)
        outer.addWidget(self.scroll_area)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(8)
        title = QLabel("소하천 조회")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "구축된 소하천과 특성정보를 검색하고 현재 사용값, 데이터 출처, "
            "QC 및 보정 이력을 확인합니다."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(12)
        self.filter_layout = QGridLayout()
        self.filter_layout.setSpacing(10)
        self.regions = {}
        for level, label, width in (("province", "시·도", 150), ("city_county", "시·군·구", 170)):
            combo = QComboBox()
            combo.addItem(label + ": 전체", None)
            combo.setMinimumWidth(width)
            combo.setEnabled(level == "province")
            combo.currentIndexChanged.connect(lambda _index, key=level: self.region_changed(key))
            self.regions[level] = combo
        self.name_search = QLineEdit()
        self.name_search.setPlaceholderText("소하천명 검색")
        self.name_search.setMinimumWidth(170)
        self.code_search = QLineEdit()
        self.code_search.setPlaceholderText("11자리 관리코드 검색")
        self.code_search.setMaxLength(11)
        self.code_search.setMinimumWidth(190)
        self.search = self.name_search  # Phase 9B public widget contract
        self.name_search.textEdited.connect(lambda _text: self.code_search.clear())
        self.code_search.textEdited.connect(lambda _text: self.name_search.clear())
        self.name_search.returnPressed.connect(self.apply_search)
        self.code_search.returnPressed.connect(self.apply_search)
        self.search_button = QPushButton("조회")
        self.search_button.setObjectName("primaryButton")
        self.search_button.clicked.connect(self.apply_search)
        layout.addLayout(self.filter_layout)
        self.advanced_toggle = QPushButton("고급 필터 펼치기")
        self.advanced_toggle.setObjectName("compactButton")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        layout.addWidget(self.advanced_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.advanced_panel = QFrame()
        self.advanced_panel.setObjectName("advancedPanel")
        advanced = QHBoxLayout(self.advanced_panel)
        advanced.setContentsMargins(12, 8, 12, 8)
        advanced.addWidget(QLabel("읍·면·동"))
        town = QComboBox()
        town.addItem("전체", None)
        town.setEnabled(False)
        town.setMaximumWidth(190)
        town.currentIndexChanged.connect(lambda _index: self.region_changed("town"))
        self.regions["town"] = town
        advanced.addWidget(town)
        advanced.addStretch()
        self.advanced_panel.hide()
        layout.addWidget(self.advanced_panel)

        result_header = QHBoxLayout()
        self.result_count = QLabel("조회 결과 0건")
        self.result_count.setObjectName("sectionTitle")
        result_header.addWidget(self.result_count)
        result_header.addStretch()
        layout.addLayout(result_header)
        self.result_workspace = QWidget()
        self.result_workspace.setObjectName("resultWorkspace")
        self.result_workspace.setMinimumWidth(RESULT_WORKSPACE_MIN_WIDTH)
        self.result_layout = QGridLayout(self.result_workspace)
        self.result_layout.setContentsMargins(0, 0, 0, 0)
        self.result_layout.setSpacing(20)
        table_column = QVBoxLayout()
        self.model = StreamListTableModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.setShowGrid(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 146)
        self.table.setItemDelegateForColumn(5, StatusBadgeDelegate(self.table))
        header.sectionClicked.connect(self.sort_by_column)
        self.table.selectionModel().currentRowChanged.connect(self.row_selected)
        self.table.doubleClicked.connect(self.open_detail)
        table_column.addWidget(self.table, 1)
        self.empty_state = QLabel("조건에 맞는 소하천이 없습니다.")
        self.empty_state.setObjectName("emptyState")
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.setFixedHeight(96)
        self.empty_state.hide()
        table_column.addWidget(self.empty_state)
        footer = QHBoxLayout()
        self.status = QLabel("조회 중")
        self.status.setObjectName("secondaryText")
        footer.addWidget(self.status)
        footer.addStretch()
        self.previous = QPushButton("이전")
        self.next = QPushButton("다음")
        self.previous.clicked.connect(self.previous_page)
        self.next.clicked.connect(self.next_page)
        self.page_label = QLabel("0 / 0 페이지 · 0건")
        footer.addWidget(self.previous)
        footer.addWidget(self.page_label)
        footer.addWidget(self.next)
        table_column.addLayout(footer)
        self.table_container = QWidget()
        self.table_container.setLayout(table_column)
        self.table_container.setMinimumHeight(360)
        self.table_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.summary_panel = self._summary_panel()
        self.summary_panel.setFixedWidth(310)
        self.result_layout.addWidget(self.table_container, 0, 0)
        self.result_layout.addWidget(self.summary_panel, 0, 1)
        self.result_layout.setColumnStretch(0, 1)
        self.result_layout.setRowStretch(0, 1)
        self.workspace_scroll = QScrollArea()
        self.workspace_scroll.setObjectName("resultWorkspaceScroll")
        self.workspace_scroll.setWidgetResizable(True)
        self.workspace_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.workspace_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.workspace_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.workspace_scroll.setWidget(self.result_workspace)
        self.workspace_scroll.setMinimumHeight(
            max(420, self.summary_panel.minimumSizeHint().height() + 24)
        )
        layout.addWidget(self.workspace_scroll, 1)
        self._set_layout_mode(self.width())
        self._buttons()

    def _summary_panel(self):
        wrapper = QWidget()
        wrapper.setMinimumWidth(280)
        wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        outer = QVBoxLayout(wrapper)
        outer.setContentsMargins(0, 0, 0, 0)
        heading = QLabel("소하천 상세")
        heading.setObjectName("sectionTitle")
        outer.addWidget(heading)
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 18)
        card_layout.setSpacing(8)
        self.summary_name = QLabel("소하천을 선택하세요")
        self.summary_name.setObjectName("sectionTitle")
        self.summary_code = QLabel("목록에서 한 행을 선택하면 요약정보를 표시합니다.")
        self.summary_code.setObjectName("secondaryText")
        self.summary_code.setWordWrap(True)
        card_layout.addWidget(self.summary_name)
        card_layout.addWidget(self.summary_code)
        self.summary_labels = {}
        for section, rows in (
            ("기본정보", (("region", "지역"), ("area", "유역면적"), ("length", "하천연장"))),
            ("데이터 상태", (("import", "최근 Import"), ("qc", "QC"), ("correction", "보정 이력"))),
            ("특성정보", (("features", "대표 현재 사용값"),)),
        ):
            card_layout.addSpacing(9)
            label = QLabel(section)
            label.setObjectName("sectionTitle")
            card_layout.addWidget(label)
            for key, caption in rows:
                caption_label = QLabel(caption)
                caption_label.setObjectName("fieldLabel")
                value = QLabel("—")
                value.setObjectName("fieldValue")
                value.setWordWrap(True)
                card_layout.addWidget(caption_label)
                card_layout.addWidget(value)
                self.summary_labels[key] = value
        self.summary_qc_badge = StatusBadge("—")
        self.summary_labels["qc"].hide()
        card_layout.insertWidget(
            card_layout.indexOf(self.summary_labels["correction"]), self.summary_qc_badge
        )
        card_layout.addStretch()
        self.detail_button = QPushButton("상세 보기")
        self.detail_button.setObjectName("primaryButton")
        self.detail_button.setEnabled(False)
        self.detail_button.clicked.connect(self.open_detail)
        card_layout.addWidget(self.detail_button)
        outer.addWidget(card, 1)
        return wrapper

    def _set_layout_mode(self, content_width):
        if content_width >= SEARCH_REFLOW_BREAKPOINT:
            mode = "wide"
        elif content_width >= SEARCH_NARROW_BREAKPOINT:
            mode = "compact"
        else:
            mode = "narrow"
        if mode == self._layout_mode:
            return
        self._layout_mode = mode
        for widget in (
            self.regions["province"],
            self.regions["city_county"],
            self.name_search,
            self.code_search,
            self.search_button,
        ):
            self.filter_layout.removeWidget(widget)
        if mode == "wide":
            self.filter_layout.addWidget(self.regions["province"], 0, 0)
            self.filter_layout.addWidget(self.regions["city_county"], 0, 1)
            self.filter_layout.addWidget(self.name_search, 0, 2)
            self.filter_layout.addWidget(self.code_search, 0, 3)
            self.filter_layout.addWidget(self.search_button, 0, 4)
            self.filter_layout.setColumnStretch(2, 1)
            self.filter_layout.setColumnStretch(3, 1)
        elif mode == "compact":
            self.filter_layout.addWidget(self.regions["province"], 0, 0)
            self.filter_layout.addWidget(self.regions["city_county"], 0, 1)
            self.filter_layout.addWidget(self.name_search, 1, 0, 1, 2)
            self.filter_layout.addWidget(self.code_search, 1, 2)
            self.filter_layout.addWidget(self.search_button, 1, 3)
            self.filter_layout.setColumnStretch(0, 1)
            self.filter_layout.setColumnStretch(1, 1)
            self.filter_layout.setColumnStretch(2, 1)
        else:
            self.filter_layout.addWidget(self.regions["province"], 0, 0)
            self.filter_layout.addWidget(self.regions["city_county"], 0, 1)
            self.filter_layout.addWidget(self.name_search, 1, 0, 1, 2)
            self.filter_layout.addWidget(self.code_search, 2, 0)
            self.filter_layout.addWidget(self.search_button, 2, 1)
            self.filter_layout.setColumnStretch(0, 1)
            self.filter_layout.setColumnStretch(1, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._set_layout_mode(event.size().width())

    def _toggle_advanced(self, checked):
        self.advanced_panel.setVisible(checked)
        self.advanced_toggle.setText("고급 필터 접기" if checked else "고급 필터 펼치기")

    def _start(self, operation, args, generation, callback):
        task = QueryTask(self.db_path, generation, operation, args)
        key = id(task)
        self._tasks[key] = task

        def deliver(token, result, error):
            self._tasks.pop(key, None)
            if not self._closed:
                callback(token, result, error)

        task.signals.finished.connect(deliver)
        self.pool.start(task)

    def load_regions(self, level):
        self._region_generation[level] += 1
        token = self._region_generation[level]
        args = (level,)
        kwargs = {
            "province_code": self.regions["province"].currentData(),
            "city_county_code": self.regions["city_county"].currentData(),
        }
        self._start(
            "region_options",
            (args, kwargs),
            token,
            lambda t, value, error: self._region_result(level, t, value, error),
        )

    def _region_result(self, level, token, result, error):
        if token != self._region_generation[level]:
            return
        combo = self.regions[level]
        combo.blockSignals(True)
        combo.clear()
        labels = {"province": "시·도", "city_county": "시·군·구", "town": "읍·면·동"}
        combo.addItem(labels[level] + ": 전체", None)
        if not error:
            for option in result:
                combo.addItem(option.name, option.code)
        combo.blockSignals(False)
        combo.setEnabled(not error and (level == "province" or bool(result)))

    def _clear_region(self, level):
        self._region_generation[level] += 1
        combo = self.regions[level]
        combo.blockSignals(True)
        combo.setCurrentIndex(0)
        combo.setEnabled(False)
        combo.blockSignals(False)

    def region_changed(self, level):
        if level == "province":
            self._clear_region("city_county")
            self._clear_region("town")
            if self.regions["province"].currentData():
                self.load_regions("city_county")
        elif level == "city_county":
            self._clear_region("town")
            if self.regions["city_county"].currentData():
                self.load_regions("town")
        self.page = 1
        self.refresh()

    def apply_search(self):
        self.page = 1
        self.refresh()

    def sort_by_column(self, column):
        field = SORT_FIELDS[column]
        if field is None:
            return
        self.sort_direction = (
            "DESC" if field == self.sort_field and self.sort_direction == "ASC" else "ASC"
        )
        self.sort_field = field
        self.page = 1
        self.refresh()

    def _buttons(self):
        self.previous.setEnabled(self.page > 1)
        self.next.setEnabled(self.total_pages > 0 and self.page < self.total_pages)

    def refresh(self):
        self._generation += 1
        token = self._generation
        self.selected_code = None
        self.detail_button.setEnabled(False)
        self.status.setText("조회 중")
        self.empty_state.hide()
        self.previous.setEnabled(False)
        self.next.setEnabled(False)
        search = self.code_search.text().strip() or self.name_search.text().strip()
        request = StreamListRequest(
            page=self.page,
            page_size=PAGE_SIZE,
            search=search,
            province_code=self.regions["province"].currentData(),
            city_county_code=self.regions["city_county"].currentData(),
            town_code=self.regions["town"].currentData(),
            sort_field=self.sort_field,
            sort_direction=self.sort_direction,
        )
        self._start("list_streams", ((request,), {}), token, self._list_result)

    def _list_result(self, token, result, error):
        if token != self._generation:
            return
        if error:
            self.model.set_rows(())
            self.table.hide()
            self.empty_state.hide()
            self.status.setText("조회 중 오류가 발생했습니다.")
            self.result_count.setText("조회 결과")
            self.total_pages = 0
            self.page_label.setText("조회 불가")
        else:
            self.model.set_rows(result.rows)
            self.table.setVisible(bool(result.rows))
            self.total_pages = result.total_pages
            self.result_count.setText(f"조회 결과 {result.total_count:,}건")
            self.status.setText(
                f"전체 {result.total_count:,}건"
                if result.rows
                else "조건에 맞는 소하천이 없습니다."
            )
            self.empty_state.setVisible(not result.rows)
            current_page = result.page if result.total_pages else 0
            self.page_label.setText(
                f"{current_page} / {result.total_pages} 페이지 · {result.total_count:,}건"
            )
        self._buttons()

    def previous_page(self):
        if self.page > 1:
            self.page -= 1
            self.refresh()

    def next_page(self):
        if self.total_pages and self.page < self.total_pages:
            self.page += 1
            self.refresh()

    def row_selected(self, current, _previous):
        if not current.isValid():
            return
        self.selected_code = self.model.stream_code(current.row())
        self.detail_button.setEnabled(False)
        self.selected_stream.emit(self.selected_code)
        self._summary_generation += 1
        token = self._summary_generation
        self.summary_name.setText("요약정보 조회 중")
        self._start(
            "get_research_stream_detail", ((self.selected_code,), {}), token, self._summary_result
        )

    def _summary_result(self, token, detail, error):
        if token != self._summary_generation:
            return
        if error or detail is None:
            self.summary_name.setText("요약정보를 불러올 수 없습니다")
            self.summary_code.setText("안전하게 다시 조회해주세요.")
            return
        basic = detail.basic
        self.summary_name.setText(basic.stream_name)
        self.summary_code.setText("관리코드  " + basic.stream_code)
        region = " ".join(filter(None, (basic.province, basic.city_county, basic.town))) or "미등록"
        self.summary_labels["region"].setText(region)
        by_name = {row.internal_name: row for row in detail.characteristics}
        self._set_measure("area", "유역면적", by_name.get("basin_area"))
        self._set_measure("length", "하천연장", by_name.get("stream_length_total"))
        imported = [
            value
            for row in detail.characteristics
            for value in row.value_history
            if value.source_classification == "IMPORT"
        ]
        latest_import = max((value.created_at for value in imported), default=None)
        self.summary_labels["import"].setText(display_timestamp(latest_import))
        self.summary_qc_badge.set_status(STATUS_TEXT.get(basic.qc_display_state, "상태 확인 필요"))
        corrections = sum(
            value.source_classification == "RESEARCHER_CORRECTION"
            for row in detail.characteristics
            for value in row.value_history
        )
        self.summary_labels["correction"].setText(f"{corrections}건")
        features = [
            row
            for row in detail.characteristics
            if row.representative_six and row.current_use_status == "VALID_CURRENT"
        ][:3]
        feature_text = (
            "\n".join(
                f"{row.standard_name}  {row.current_value} {row.unit_display or ''}".rstrip()
                for row in features
            )
            or "현재 사용값 미지정"
        )
        self.summary_labels["features"].setText(feature_text)
        self.detail_button.setEnabled(True)

    def _set_measure(self, key, caption, row):
        value = "미등록"
        if row is not None and row.current_use_status == "VALID_CURRENT":
            value = f"{row.current_value} {row.unit_display or ''}".rstrip()
        self.summary_labels[key].setText(value)

    def open_detail(self, _index=None):
        if self.selected_code:
            self.detail_requested.emit(self.selected_code)

    def closeEvent(self, event):
        self._closed = True
        super().closeEvent(event)
