"""Phase 9B 앱 shell. 소하천 목록만 실제 메뉴에 연결한다."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from small_stream_research_tool.ui.stream_list import StreamListView

NAVIGATION = (
    "홈",
    "Excel 가져오기",
    "품질검사(QC)",
    "특성정보 보정 관리",
    "소하천 조회",
    "DB 관리",
    "기초통계",
    "그래프 분석",
    "결과 내보내기",
    "작업이력",
    "설정",
)


class MainWindow(QMainWindow):
    logout_requested = Signal()

    def __init__(self, db_path, session):
        super().__init__()
        self.session = session
        self.setWindowTitle("소하천 데이터 관리")
        self.resize(1440, 900)
        root = QWidget()
        self.setCentralWidget(root)
        vertical = QVBoxLayout(root)
        vertical.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.setContentsMargins(24, 12, 24, 12)
        title = QLabel("소하천 데이터 관리")
        title.setObjectName("pageTitle")
        top.addWidget(title)
        top.addStretch()
        identity = session.display_name
        if session.department:
            identity += " · " + session.department
        top.addWidget(QLabel(identity))
        logout = QPushButton("로그아웃")
        logout.clicked.connect(self.logout_requested)
        top.addWidget(logout)
        vertical.addLayout(top)
        body = QHBoxLayout()
        body.setSpacing(0)
        navigation = QWidget()
        navigation.setFixedWidth(215)
        nav_layout = QVBoxLayout(navigation)
        nav_layout.setContentsMargins(12, 12, 12, 12)
        nav_layout.setSpacing(5)
        self.nav_buttons = {}
        for name in NAVIGATION:
            button = QPushButton(name)
            button.setObjectName("navButton")
            button.clicked.connect(lambda _checked=False, target=name: self.navigate(target))
            nav_layout.addWidget(button)
            self.nav_buttons[name] = button
        nav_layout.addStretch()
        body.addWidget(navigation)
        self.stack = QStackedWidget()
        self.placeholder = QWidget()
        placeholder_layout = QVBoxLayout(self.placeholder)
        placeholder_layout.setContentsMargins(34, 34, 34, 34)
        self.placeholder_title = QLabel("")
        self.placeholder_title.setObjectName("pageTitle")
        placeholder_layout.addWidget(self.placeholder_title)
        placeholder_layout.addWidget(QLabel("아직 구현되지 않은 기능입니다."))
        placeholder_layout.addStretch()
        self.stack.addWidget(self.placeholder)
        self.stream_list = StreamListView(db_path)
        self.stack.addWidget(self.stream_list)
        body.addWidget(self.stack, 1)
        vertical.addLayout(body, 1)
        self.navigate("소하천 조회")

    def navigate(self, name):
        for key, button in self.nav_buttons.items():
            button.setObjectName("navSelected" if key == name else "navButton")
            button.style().unpolish(button)
            button.style().polish(button)
        if name == "소하천 조회":
            self.stack.setCurrentWidget(self.stream_list)
        else:
            self.placeholder_title.setText(name)
            self.stack.setCurrentWidget(self.placeholder)

    def closeEvent(self, event):
        self.stream_list._closed = True
        super().closeEvent(event)
