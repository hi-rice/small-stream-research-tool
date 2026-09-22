"""Figma shell에 맞춘 앱 창과 구현된 read-only 화면 navigation."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from small_stream_research_tool.ui.home import HomeView
from small_stream_research_tool.ui.import_workspace import ImportWorkspaceView
from small_stream_research_tool.ui.my_page import MyPageView
from small_stream_research_tool.ui.stream_detail import StreamDetailView
from small_stream_research_tool.ui.stream_list import StreamListView
from small_stream_research_tool.ui.work_history import WorkHistoryView

NAVIGATION_SECTIONS = (
    (None, ("홈",)),
    ("데이터 관리", ("Excel 가져오기", "품질검사(QC)", "특성정보 보정", "소하천 조회", "DB 관리")),
    ("분석", ("기초통계", "그래프 분석")),
    (None, ("결과 내보내기", "작업이력")),
)
NAVIGATION = tuple(name for _section, names in NAVIGATION_SECTIONS for name in names) + ("설정",)


class MainWindow(QMainWindow):
    logout_requested = Signal()

    def __init__(self, db_path, session, workspace_dir=None):
        super().__init__()
        self.session = session
        self.setWindowTitle("소하천 데이터 관리")
        self.resize(1440, 900)
        self.setMinimumSize(900, 600)
        root = QWidget()
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        shell.addWidget(self._sidebar())
        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)
        workspace_layout.addWidget(self._topbar())
        self.stack = QStackedWidget()
        self.placeholder = QWidget()
        placeholder_layout = QVBoxLayout(self.placeholder)
        placeholder_layout.setContentsMargins(40, 32, 40, 32)
        self.placeholder_title = QLabel("")
        self.placeholder_title.setObjectName("pageTitle")
        placeholder_layout.addWidget(self.placeholder_title)
        placeholder_layout.addWidget(QLabel("아직 구현되지 않은 기능입니다."))
        placeholder_layout.addStretch()
        self.stack.addWidget(self.placeholder)
        self.home = HomeView(db_path)
        self.stack.addWidget(self.home)
        self.import_workspace = ImportWorkspaceView(db_path, session.user_id, workspace_dir)
        self.stack.addWidget(self.import_workspace)
        self.stream_list = StreamListView(db_path)
        self.stack.addWidget(self.stream_list)
        self.stream_detail = StreamDetailView(db_path)
        self.stack.addWidget(self.stream_detail)
        self.work_history = WorkHistoryView(db_path)
        self.stack.addWidget(self.work_history)
        self.my_page = MyPageView(db_path, session.user_id)
        self.stack.addWidget(self.my_page)
        self.stream_list.detail_requested.connect(self.show_stream_detail)
        self.stream_detail.back_requested.connect(lambda: self.navigate("소하천 조회"))
        self.home.stream_list_requested.connect(lambda: self.navigate("소하천 조회"))
        self.home.work_history_requested.connect(lambda: self.navigate("작업이력"))
        self.my_page.work_history_requested.connect(self.show_user_work_history)
        workspace_layout.addWidget(self.stack, 1)
        shell.addWidget(workspace, 1)
        self.navigate("홈")

    def _sidebar(self):
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(228)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 17, 12, 12)
        layout.setSpacing(1)
        agency = QLabel("NDMI")
        agency.setObjectName("brandAgency")
        title = QLabel("소하천 데이터 관리")
        title.setObjectName("brandTitle")
        layout.addWidget(agency)
        layout.addWidget(title)
        layout.addSpacing(14)
        self.nav_buttons = {}
        for section, names in NAVIGATION_SECTIONS:
            if section:
                heading = QLabel(section)
                heading.setObjectName("navSection")
                layout.addWidget(heading)
            for name in names:
                self._add_nav(layout, name)
            layout.addSpacing(4)
        layout.addStretch()
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #38506A; background: #38506A;")
        layout.addWidget(divider)
        self._add_nav(layout, "설정")
        return sidebar

    def _add_nav(self, layout, name):
        button = QPushButton(name)
        button.setObjectName("navButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _checked=False, target=name: self.navigate(target))
        layout.addWidget(button)
        self.nav_buttons[name] = button

    def _topbar(self):
        topbar = QWidget()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(58)
        layout = QHBoxLayout(topbar)
        layout.setContentsMargins(32, 7, 22, 7)
        dot = QLabel("●")
        dot.setObjectName("databaseDot")
        dot.setToolTip("현재 로컬 SQLite 데이터베이스를 사용합니다.")
        database = QLabel("로컬 데이터베이스")
        database.setObjectName("databaseState")
        layout.addWidget(dot)
        layout.addWidget(database)
        layout.addStretch()
        self.user_button = QPushButton()
        self.user_button.setObjectName("topbarUserButton")
        self.user_button.setCursor(Qt.CursorShape.PointingHandCursor)
        identity = QVBoxLayout(self.user_button)
        identity.setContentsMargins(9, 2, 9, 2)
        identity.setSpacing(0)
        self.user_name = QLabel(self.session.display_name)
        self.user_name.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.user_department = QLabel(self.session.department or "부서 미등록")
        self.user_department.setObjectName("secondaryText")
        self.user_department.setAlignment(Qt.AlignmentFlag.AlignRight)
        identity.addWidget(self.user_name)
        identity.addWidget(self.user_department)
        identity_margins = identity.contentsMargins()
        identity_width = (
            max(self.user_name.sizeHint().width(), self.user_department.sizeHint().width())
            + identity_margins.left()
            + identity_margins.right()
        )
        self.user_button.setMinimumWidth(identity_width)
        self.user_button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.user_button.clicked.connect(lambda: self.navigate("마이페이지"))
        layout.addWidget(self.user_button)
        self.logout_button = QPushButton("로그아웃")
        self.logout_button.setObjectName("compactButton")
        self.logout_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.logout_button.clicked.connect(self.logout_requested)
        layout.addWidget(self.logout_button)
        return topbar

    def navigate(self, name):
        if self.stack.currentWidget() is self.import_workspace and name != "Excel 가져오기":
            self.import_workspace.deactivate()
        for key, button in self.nav_buttons.items():
            button.setObjectName("navSelected" if key == name else "navButton")
            button.style().unpolish(button)
            button.style().polish(button)
        if name == "홈":
            self.stack.setCurrentWidget(self.home)
            self.home.refresh()
        elif name == "Excel 가져오기":
            self.stack.setCurrentWidget(self.import_workspace)
            self.import_workspace.activate()
        elif name == "소하천 조회":
            self.stack.setCurrentWidget(self.stream_list)
        elif name == "작업이력":
            self.stack.setCurrentWidget(self.work_history)
            self.work_history.activate()
        elif name == "마이페이지":
            self.stack.setCurrentWidget(self.my_page)
            self.my_page.refresh()
        else:
            self.placeholder_title.setText(name)
            self.stack.setCurrentWidget(self.placeholder)

    def show_stream_detail(self, stream_code):
        self.stack.setCurrentWidget(self.stream_detail)
        self.stream_detail.load_stream(stream_code)

    def show_user_work_history(self, user_id):
        self.stack.setCurrentWidget(self.work_history)
        for button in self.nav_buttons.values():
            button.setObjectName("navButton")
            button.style().unpolish(button)
            button.style().polish(button)
        self.nav_buttons["작업이력"].setObjectName("navSelected")
        self.nav_buttons["작업이력"].style().unpolish(self.nav_buttons["작업이력"])
        self.nav_buttons["작업이력"].style().polish(self.nav_buttons["작업이력"])
        self.work_history.activate(user_id)

    def closeEvent(self, event):
        self.home._closed = True
        self.home._generation += 1
        self.stream_list._closed = True
        self.stream_detail._closed = True
        self.work_history._closed = True
        self.work_history._generation += 1
        self.work_history._actor_generation += 1
        self.my_page._closed = True
        self.my_page._generation += 1
        self.import_workspace._closed = True
        self.import_workspace._generation += 1
        super().closeEvent(event)
