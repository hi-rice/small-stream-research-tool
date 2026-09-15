"""09 소하천 조회의 목록·검색·지역 필터·정렬·페이지 화면."""

from PySide6.QtCore import QThreadPool, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from small_stream_research_tool.models.stream_read import StreamListRequest
from small_stream_research_tool.ui.presentation import SORT_FIELDS
from small_stream_research_tool.ui.table_model import StreamListTableModel
from small_stream_research_tool.ui.workers import QueryTask

PAGE_SIZE = 50


class StreamListView(QWidget):
    selected_stream = Signal(str)

    def __init__(self, db_path, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.pool = QThreadPool.globalInstance()
        self._tasks = {}
        self._generation = 0
        self._region_generation = {"province": 0, "city_county": 0, "town": 0}
        self._closed = False
        self.page = 1
        self.total_pages = 0
        self.sort_field = "stream_code"
        self.sort_direction = "ASC"
        self.selected_code = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(14)
        title = QLabel("소하천 조회")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("관리코드 또는 소하천명")
        self.search.returnPressed.connect(self.apply_search)
        controls.addWidget(self.search, 3)
        self.search_button = QPushButton("검색")
        self.search_button.setObjectName("primaryButton")
        self.search_button.clicked.connect(self.apply_search)
        controls.addWidget(self.search_button)
        self.regions = {}
        for level, label in (
            ("province", "시·도"),
            ("city_county", "시·군·구"),
            ("town", "읍·면·동"),
        ):
            combo = QComboBox()
            combo.addItem(label + " 전체", None)
            combo.setEnabled(level == "province")
            combo.currentIndexChanged.connect(lambda _index, key=level: self.region_changed(key))
            controls.addWidget(combo, 2)
            self.regions[level] = combo
        layout.addLayout(controls)
        self.status = QLabel("조회 중")
        layout.addWidget(self.status)
        self.model = StreamListTableModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.sectionClicked.connect(self.sort_by_column)
        self.table.selectionModel().currentRowChanged.connect(self.row_selected)
        layout.addWidget(self.table, 1)
        footer = QHBoxLayout()
        self.previous = QPushButton("이전")
        self.next = QPushButton("다음")
        self.previous.clicked.connect(self.previous_page)
        self.next.clicked.connect(self.next_page)
        self.page_label = QLabel("1 / 0 페이지 · 0건")
        footer.addStretch()
        footer.addWidget(self.previous)
        footer.addWidget(self.page_label)
        footer.addWidget(self.next)
        layout.addLayout(footer)
        self._buttons()
        self.load_regions("province")
        self.refresh()

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
        province = self.regions["province"].currentData()
        city = self.regions["city_county"].currentData()
        args = (level,)
        kwargs = {"province_code": province, "city_county_code": city}
        self._start(
            "region_options",
            (args, kwargs),
            token,
            lambda t, result, error: self._region_result(level, t, result, error),
        )

    def _region_result(self, level, token, result, error):
        if token != self._region_generation[level]:
            return
        combo = self.regions[level]
        combo.blockSignals(True)
        combo.clear()
        labels = {"province": "시·도", "city_county": "시·군·구", "town": "읍·면·동"}
        combo.addItem(labels[level] + " 전체", None)
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
        self.status.setText("조회 중")
        self.previous.setEnabled(False)
        self.next.setEnabled(False)
        request = StreamListRequest(
            page=self.page,
            page_size=PAGE_SIZE,
            search=self.search.text().strip(),
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
            self.status.setText("조회 중 오류가 발생했습니다.")
            self.total_pages = 0
            self.page_label.setText("조회 불가")
        else:
            self.model.set_rows(result.rows)
            self.total_pages = result.total_pages
            self.status.setText(
                f"전체 {result.total_count:,}건"
                if result.rows
                else "조건에 맞는 소하천이 없습니다."
            )
            self.page_label.setText(
                f"{result.page} / {result.total_pages} 페이지 · {result.total_count:,}건"
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
        if current.isValid():
            self.selected_code = self.model.stream_code(current.row())
            self.selected_stream.emit(self.selected_code)

    def closeEvent(self, event):
        self._closed = True
        super().closeEvent(event)
