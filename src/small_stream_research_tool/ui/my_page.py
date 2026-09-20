"""현재 로그인한 로컬 작업자의 공개 정보를 표시하는 read-only 화면."""

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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from small_stream_research_tool.models.app_read import UserPublicProfile
from small_stream_research_tool.ui.presentation import (
    HISTORY_EVENT_TEXT,
    display_history_target,
    display_timestamp,
)
from small_stream_research_tool.ui.workers import MyPageQueryTask


class MyPageView(QWidget):
    work_history_requested = Signal(int)

    def __init__(self, db_path, user_id):
        super().__init__()
        self.db_path = db_path
        self.user_id = user_id
        self.pool = QThreadPool.globalInstance()
        self._generation = 0
        self._closed = False
        self._tasks = set()
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("myPageScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("myPageContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 26, 32, 32)
        layout.setSpacing(16)
        title = QLabel("마이페이지")
        title.setObjectName("pageTitle")
        subtitle = QLabel("현재 로그인한 작업자 정보를 확인합니다.")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        self.status = QLabel("사용자 정보를 불러오려면 마이페이지를 선택하세요.")
        self.status.setObjectName("secondaryText")
        layout.addWidget(self.status)

        account = QFrame()
        account.setObjectName("card")
        account_layout = QVBoxLayout(account)
        account_layout.setContentsMargins(20, 18, 20, 20)
        account_title = QLabel("계정 정보")
        account_title.setObjectName("sectionTitle")
        account_layout.addWidget(account_title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(11)
        self.profile_values = {}
        fields = (
            ("login_id", "로그인 ID"),
            ("display_name", "표시 이름"),
            ("department", "부서"),
            ("role", "역할"),
            ("status", "계정 상태"),
            ("created_at", "등록일"),
            ("last_login_at", "최근 로그인"),
        )
        for row, (key, caption) in enumerate(fields):
            label = QLabel(caption)
            label.setObjectName("fieldLabel")
            value = QLabel("—")
            value.setObjectName("fieldValue")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(label, row, 0)
            grid.addWidget(value, row, 1)
            self.profile_values[key] = value
        grid.setColumnStretch(1, 1)
        account_layout.addLayout(grid)
        layout.addWidget(account)

        recent_header = QHBoxLayout()
        recent_title = QLabel("최근 내 작업")
        recent_title.setObjectName("sectionTitle")
        recent_header.addWidget(recent_title)
        recent_header.addStretch()
        self.history_button = QPushButton("내 작업이력 보기")
        self.history_button.setObjectName("primaryButton")
        self.history_button.clicked.connect(lambda: self.work_history_requested.emit(self.user_id))
        recent_header.addWidget(self.history_button)
        layout.addLayout(recent_header)
        self.recent = QTableWidget(0, 3)
        self.recent.setHorizontalHeaderLabels(("변경 시각", "작업", "대상"))
        self.recent.setAlternatingRowColors(True)
        self.recent.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.recent.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.recent.verticalHeader().setVisible(False)
        header = self.recent.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.recent.setMinimumHeight(230)
        layout.addWidget(self.recent)
        self.empty_recent = QLabel("최근 작업이 없습니다.")
        self.empty_recent.setObjectName("emptyState")
        self.empty_recent.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_recent.hide()
        layout.addWidget(self.empty_recent)
        layout.addStretch()
        self.scroll_area.setWidget(content)
        outer.addWidget(self.scroll_area)

    def refresh(self):
        if self._closed:
            return
        self._generation += 1
        generation = self._generation
        self.status.setText("사용자 정보를 불러오는 중입니다.")
        task = MyPageQueryTask(self.db_path, generation, self.user_id)
        self._tasks.add(task)
        task.signals.finished.connect(
            lambda token, result, error, current=task: self._result(current, token, result, error)
        )
        self.pool.start(task)

    def _result(self, task, generation, result, error):
        self._tasks.discard(task)
        if self._closed or generation != self._generation:
            return
        if error or not isinstance(result, tuple) or len(result) != 2:
            self._show_error()
            return
        profile, recent = result
        if not isinstance(profile, UserPublicProfile):
            self._show_error()
            return
        self.profile_values["login_id"].setText(profile.login_id)
        self.profile_values["display_name"].setText(profile.display_name)
        self.profile_values["department"].setText(profile.department or "미등록")
        self.profile_values["role"].setText(profile.role or "미지정")
        self.profile_values["status"].setText("사용 중" if profile.is_active else "비활성")
        self.profile_values["created_at"].setText(display_timestamp(profile.created_at))
        self.profile_values["last_login_at"].setText(
            display_timestamp(profile.last_login_at)
            if profile.last_login_at
            else "로그인 기록 없음"
        )
        self.recent.setRowCount(len(recent))
        for row, item in enumerate(recent):
            values = (
                display_timestamp(item.changed_at),
                HISTORY_EVENT_TEXT.get(item.change_type, "작업 유형 확인 필요"),
                display_history_target(item),
            )
            for column, value in enumerate(values):
                self.recent.setItem(row, column, QTableWidgetItem(value))
        empty = not recent
        self.recent.setVisible(not empty)
        self.empty_recent.setVisible(empty)
        self.status.setText("현재 사용자 공개 정보입니다.")

    def _show_error(self):
        for value in self.profile_values.values():
            value.setText("—")
        self.recent.setRowCount(0)
        self.recent.hide()
        self.empty_recent.hide()
        self.status.setText("현재 사용자 정보를 확인할 수 없습니다. 다시 로그인해주세요.")

    def closeEvent(self, event):
        self._closed = True
        self._generation += 1
        super().closeEvent(event)
