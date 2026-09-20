"""Phase 9D 홈의 제한된 읽기 전용 요약 화면."""

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from small_stream_research_tool.models.app_read import HomeSummary
from small_stream_research_tool.ui.presentation import (
    DICTIONARY_STATE_TEXT,
    HISTORY_EVENT_TEXT,
    display_history_target,
    display_timestamp,
)
from small_stream_research_tool.ui.workers import AppQueryTask

HOME_CARD_REFLOW_BREAKPOINT = 900


class HomeView(QWidget):
    stream_list_requested = Signal()

    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path
        self.pool = QThreadPool.globalInstance()
        self._generation = 0
        self._closed = False
        self._tasks = set()
        self._card_mode = None
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("homeScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.content.setObjectName("homeContent")
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(32, 26, 32, 32)
        layout.setSpacing(18)

        title = QLabel("홈")
        title.setObjectName("pageTitle")
        subtitle = QLabel("소하천 데이터 현황과 최근 작업을 확인합니다.")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.card_layout = QGridLayout()
        self.card_layout.setContentsMargins(0, 2, 0, 0)
        self.card_layout.setHorizontalSpacing(12)
        self.card_layout.setVerticalSpacing(12)
        self.stream_count = QLabel("—")
        self.error_count = QLabel("—")
        self.review_count = QLabel("—")
        self.dictionary_state = QLabel("—")
        self.cards = (
            self._metric_card("등록 소하천", self.stream_count, "조회 가능한 활성 소하천"),
            self._metric_card("오류 소하천", self.error_count, "활성 ERROR 소하천"),
            self._metric_card("확인 필요", self.review_count, "활성 WARNING/INFO 소하천"),
            self._metric_card("연구 사전", self.dictionary_state, "표시 승인 항목 기준"),
        )
        layout.addLayout(self.card_layout)

        quick = QFrame()
        quick.setObjectName("card")
        quick_layout = QHBoxLayout(quick)
        quick_layout.setContentsMargins(18, 14, 18, 14)
        quick_text = QVBoxLayout()
        quick_title = QLabel("빠른 작업")
        quick_title.setObjectName("sectionTitle")
        quick_hint = QLabel("구축된 소하천과 특성정보를 조회합니다.")
        quick_hint.setObjectName("secondaryText")
        quick_text.addWidget(quick_title)
        quick_text.addWidget(quick_hint)
        quick_layout.addLayout(quick_text)
        quick_layout.addStretch()
        self.stream_list_button = QPushButton("소하천 조회")
        self.stream_list_button.setObjectName("primaryButton")
        self.stream_list_button.clicked.connect(self.stream_list_requested)
        quick_layout.addWidget(self.stream_list_button)
        layout.addWidget(quick)

        history_header = QHBoxLayout()
        history_title = QLabel("최근 작업")
        history_title.setObjectName("sectionTitle")
        history_header.addWidget(history_title)
        history_header.addStretch()
        layout.addLayout(history_header)
        self.status = QLabel("홈 정보를 불러오려면 홈을 선택하세요.")
        self.status.setObjectName("secondaryText")
        layout.addWidget(self.status)
        self.history = QTableWidget(0, 4)
        self.history.setHorizontalHeaderLabels(("시각", "작업", "대상", "작업자"))
        self.history.setAlternatingRowColors(True)
        self.history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.history.verticalHeader().setVisible(False)
        self.history.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.history.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.history.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.history.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.history.setMinimumHeight(230)
        layout.addWidget(self.history)
        self.empty_history = QLabel("표시할 최근 작업이 없습니다.")
        self.empty_history.setObjectName("emptyState")
        self.empty_history.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_history.hide()
        layout.addWidget(self.empty_history)
        layout.addStretch()

        self.scroll_area.setWidget(self.content)
        outer.addWidget(self.scroll_area)
        self._arrange_cards("wide")

    @staticmethod
    def _metric_card(label, value, hint):
        card = QFrame()
        card.setObjectName("card")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card.setMinimumHeight(118)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        title = QLabel(label)
        title.setObjectName("homeMetricLabel")
        value.setObjectName("homeMetricValue")
        value.setWordWrap(True)
        description = QLabel(hint)
        description.setObjectName("secondaryText")
        card_layout.addWidget(title)
        card_layout.addWidget(value)
        card_layout.addStretch()
        card_layout.addWidget(description)
        return card

    def refresh(self):
        if self._closed:
            return
        self._generation += 1
        generation = self._generation
        self.status.setText("홈 정보를 불러오는 중입니다.")
        task = AppQueryTask(self.db_path, generation, "get_home_summary")
        self._tasks.add(task)
        task.signals.finished.connect(
            lambda token, result, error, current=task: self._summary_result(
                current, token, result, error
            )
        )
        self.pool.start(task)

    def _summary_result(self, task, generation, result, error):
        self._tasks.discard(task)
        if self._closed or generation != self._generation:
            return
        if error or not isinstance(result, HomeSummary):
            self.status.setText("홈 정보를 불러오지 못했습니다.")
            return
        self.stream_count.setText(f"{result.active_stream_count:,}건")
        self.error_count.setText(f"{result.error_stream_count:,}건")
        self.review_count.setText(f"{result.needs_review_stream_count:,}건")
        self.dictionary_state.setText(
            DICTIONARY_STATE_TEXT.get(result.dictionary_state, "연구 사전 상태 확인 필요")
        )
        self.history.setRowCount(len(result.recent_history))
        for row, item in enumerate(result.recent_history):
            values = (
                display_timestamp(item.changed_at),
                HISTORY_EVENT_TEXT.get(item.change_type, "작업 유형 확인 필요"),
                display_history_target(item),
                item.actor_display_name if item.actor_state == "KNOWN" else "작업자 정보 없음",
            )
            for column, value in enumerate(values):
                self.history.setItem(row, column, QTableWidgetItem(value))
        empty = not result.recent_history
        self.history.setVisible(not empty)
        self.empty_history.setVisible(empty)
        self.status.setText("최근 작업을 포함한 현재 DB 요약입니다.")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange_cards("compact" if self.width() < HOME_CARD_REFLOW_BREAKPOINT else "wide")

    def _arrange_cards(self, mode):
        if mode == self._card_mode:
            return
        for card in self.cards:
            self.card_layout.removeWidget(card)
        columns = 2 if mode == "compact" else 4
        for index, card in enumerate(self.cards):
            self.card_layout.addWidget(card, index // columns, index % columns)
        for column in range(4):
            self.card_layout.setColumnStretch(column, 1 if column < columns else 0)
        self._card_mode = mode

    def closeEvent(self, event):
        self._closed = True
        self._generation += 1
        super().closeEvent(event)
