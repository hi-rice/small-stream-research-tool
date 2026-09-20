"""연구 데이터의 주요 변경 작업을 조회하는 read-only 화면."""

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from small_stream_research_tool.models.app_read import WorkHistoryPage, WorkHistoryRequest
from small_stream_research_tool.ui.presentation import (
    HISTORY_EVENT_TEXT,
    HISTORY_REASON_TEXT,
    display_timestamp,
)
from small_stream_research_tool.ui.workers import AppQueryTask

PAGE_SIZE = 50
FILTER_REFLOW_BREAKPOINT = 850
EVENT_FILTERS = (
    ("전체", None),
    ("특성정보 보정", "CORRECTION"),
    ("현재 사용값 변경", "CURRENT_VALUE_CHANGE"),
    ("특성값 비활성화", "DEACTIVATE"),
    ("특성값 복원", "RESTORE"),
    ("현재값 캐시 재구축", "CACHE_REBUILD"),
)


class WorkHistoryView(QWidget):
    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path
        self.pool = QThreadPool.globalInstance()
        self.page = 1
        self.total_pages = 0
        self._generation = 0
        self._actor_generation = 0
        self._actors_loaded = False
        self._closed = False
        self._tasks = set()
        self._filter_mode = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 26, 32, 28)
        layout.setSpacing(14)
        title = QLabel("작업이력")
        title.setObjectName("pageTitle")
        subtitle = QLabel("연구 데이터에 영향을 준 주요 변경 이력을 조회합니다.")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.filter_layout = QGridLayout()
        self.filter_layout.setSpacing(10)
        self.change_type = QComboBox()
        for label, value in EVENT_FILTERS:
            self.change_type.addItem(label, value)
        self.change_type.setMinimumWidth(170)
        self.actor = QComboBox()
        self.actor.addItem("작업자: 전체", None)
        self.actor.setMinimumWidth(170)
        self.stream_code = QLineEdit()
        self.stream_code.setPlaceholderText("11자리 관리코드 입력")
        self.stream_code.setMaxLength(11)
        self.stream_code.setMinimumWidth(190)
        self.stream_code.returnPressed.connect(self.apply_filters)
        self.search_button = QPushButton("조회")
        self.search_button.setObjectName("primaryButton")
        self.search_button.clicked.connect(self.apply_filters)
        layout.addLayout(self.filter_layout)

        self.status = QLabel("조회 중")
        self.status.setObjectName("secondaryText")
        layout.addWidget(self.status)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ("변경 시각", "작업", "소하천", "특성항목", "작업자", "사유")
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate((170, 170, 260, 210, 150, 180)):
            self.table.setColumnWidth(column, width)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.table, 1)
        self.empty_state = QLabel("조건에 맞는 작업이력이 없습니다.")
        self.empty_state.setObjectName("emptyState")
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.hide()
        layout.addWidget(self.empty_state)

        footer = QHBoxLayout()
        footer.addWidget(QLabel("50건씩 표시"))
        footer.addStretch()
        self.previous = QPushButton("이전")
        self.previous.clicked.connect(self.previous_page)
        self.page_label = QLabel("0 / 0 페이지 · 0건")
        self.next = QPushButton("다음")
        self.next.clicked.connect(self.next_page)
        footer.addWidget(self.previous)
        footer.addWidget(self.page_label)
        footer.addWidget(self.next)
        layout.addLayout(footer)
        self._arrange_filters("wide")
        self._buttons()

    def activate(self):
        if not self._actors_loaded:
            self._load_actors()
        self.refresh()

    def _start(self, operation, args, generation, callback):
        task = AppQueryTask(self.db_path, generation, operation, args)
        self._tasks.add(task)

        def deliver(token, result, error, current=task):
            self._tasks.discard(current)
            if not self._closed:
                callback(token, result, error)

        task.signals.finished.connect(deliver)
        self.pool.start(task)

    def _load_actors(self):
        self._actor_generation += 1
        token = self._actor_generation
        self._start("list_history_actor_options", ((), {}), token, self._actor_result)

    def _actor_result(self, token, options, error):
        if token != self._actor_generation or error:
            return
        selected = self.actor.currentData()
        self.actor.blockSignals(True)
        self.actor.clear()
        self.actor.addItem("작업자: 전체", None)
        for option in options:
            self.actor.addItem(option.display_name, option.user_id)
        index = self.actor.findData(selected)
        self.actor.setCurrentIndex(max(index, 0))
        self.actor.blockSignals(False)
        self._actors_loaded = True

    def apply_filters(self):
        code = self.stream_code.text().strip()
        if code and not (len(code) == 11 and code.isascii() and code.isdigit()):
            self.status.setText("관리코드는 숫자로 된 11자리여야 합니다.")
            return
        self.page = 1
        self.refresh()

    def refresh(self):
        code = self.stream_code.text().strip() or None
        if code is not None and not (len(code) == 11 and code.isascii() and code.isdigit()):
            self.status.setText("관리코드는 숫자로 된 11자리여야 합니다.")
            return
        self._generation += 1
        token = self._generation
        self.status.setText("조회 중")
        self.previous.setEnabled(False)
        self.next.setEnabled(False)
        request = WorkHistoryRequest(
            page=self.page,
            page_size=PAGE_SIZE,
            change_type=self.change_type.currentData(),
            actor_user_id=self.actor.currentData(),
            stream_code=code,
        )
        self._start("list_work_history", ((request,), {}), token, self._history_result)

    def _history_result(self, token, result, error):
        if token != self._generation:
            return
        if error or not isinstance(result, WorkHistoryPage):
            self.table.setRowCount(0)
            self.table.hide()
            self.empty_state.hide()
            self.status.setText("작업이력을 불러오지 못했습니다.")
            self.page_label.setText("조회 불가")
            self.total_pages = 0
            self._buttons()
            return
        self.table.setRowCount(len(result.items))
        for row, item in enumerate(result.items):
            resolved = item.target_state == "RESOLVED"
            stream = (
                f"{item.stream_name} · {item.stream_code}" if resolved else "대상 정보 확인 필요"
            )
            characteristic = item.dictionary_standard_name if resolved else "대상 정보 확인 필요"
            values = (
                display_timestamp(item.changed_at),
                HISTORY_EVENT_TEXT.get(item.change_type, "작업 유형 확인 필요"),
                stream,
                characteristic,
                item.actor_display_name if item.actor_state == "KNOWN" else "작업자 미상",
                HISTORY_REASON_TEXT.get(item.reason_code, "-"),
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.total_pages = result.total_pages
        current = result.page if result.total_pages else 0
        self.page_label.setText(
            f"{current} / {result.total_pages} 페이지 · 총 {result.total_count:,}건"
            if result.total_count
            else "0 / 0 페이지 · 0건"
        )
        empty = not result.items
        self.table.setVisible(not empty)
        self.empty_state.setVisible(empty)
        self.status.setText(
            f"전체 {result.total_count:,}건" if result.items else "조건에 맞는 작업이력이 없습니다."
        )
        self._buttons()

    def _buttons(self):
        self.previous.setEnabled(self.page > 1)
        self.next.setEnabled(self.total_pages > 0 and self.page < self.total_pages)

    def previous_page(self):
        if self.page > 1:
            self.page -= 1
            self.refresh()

    def next_page(self):
        if self.total_pages and self.page < self.total_pages:
            self.page += 1
            self.refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange_filters(
            "compact" if event.size().width() < FILTER_REFLOW_BREAKPOINT else "wide"
        )

    def _arrange_filters(self, mode):
        if mode == self._filter_mode:
            return
        for widget in (self.change_type, self.actor, self.stream_code, self.search_button):
            self.filter_layout.removeWidget(widget)
        if mode == "wide":
            positions = (
                (self.change_type, 0, 0),
                (self.actor, 0, 1),
                (self.stream_code, 0, 2),
                (self.search_button, 0, 3),
            )
            for widget, row, column in positions:
                self.filter_layout.addWidget(widget, row, column)
            self.filter_layout.setColumnStretch(2, 1)
        else:
            self.filter_layout.addWidget(self.change_type, 0, 0)
            self.filter_layout.addWidget(self.actor, 0, 1)
            self.filter_layout.addWidget(self.stream_code, 1, 0)
            self.filter_layout.addWidget(self.search_button, 1, 1)
            self.filter_layout.setColumnStretch(0, 1)
            self.filter_layout.setColumnStretch(1, 1)
        self._filter_mode = mode

    def closeEvent(self, event):
        self._closed = True
        self._generation += 1
        self._actor_generation += 1
        super().closeEvent(event)
