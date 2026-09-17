"""Figma visual language를 적용한 로컬 최초 사용자 등록과 로그인 창."""

from importlib.metadata import version

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from small_stream_research_tool.config.settings import APP_ID
from small_stream_research_tool.models.errors import UserError


class LoginWindow(QWidget):
    authenticated = Signal(object)
    registered = Signal()

    def __init__(self, auth_service, initial_setup=False):
        super().__init__()
        self.auth_service = auth_service
        self.initial_setup = initial_setup
        self.setWindowTitle(
            "소하천 데이터 관리 · " + ("최초 사용자 등록" if initial_setup else "로그인")
        )
        self.resize(1000, 720)
        self.setMinimumSize(720, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 20)
        layout.setSpacing(0)
        accent = QFrame()
        accent.setFixedHeight(6)
        accent.setStyleSheet("background: #16324F; border: 0;")
        layout.addWidget(accent)
        layout.addStretch(2)
        agency = QLabel("국립재난안전연구원")
        agency.setAlignment(Qt.AlignmentFlag.AlignCenter)
        agency.setStyleSheet("color: #16324F; font-weight: 600; font-size: 15px;")
        title = QLabel("소하천 데이터 관리")
        title.setObjectName("pageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("연구 데이터 구축·검증·분석을 위한 로컬 데스크톱 도구")
        subtitle.setObjectName("pageSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(agency)
        layout.addSpacing(13)
        layout.addWidget(title)
        layout.addSpacing(7)
        layout.addWidget(subtitle)
        layout.addSpacing(32)
        card_row = QHBoxLayout()
        card_row.addStretch()
        card = QFrame()
        card.setObjectName("card")
        card.setFixedWidth(440)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(12)
        form_title = QLabel("최초 사용자 등록" if initial_setup else "로그인")
        form_title.setObjectName("sectionTitle")
        card_layout.addWidget(form_title)
        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.login_id = QLineEdit()
        self.login_id.setPlaceholderText("영문·숫자·._- 조합 4~50자")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("공백 외 문자를 포함해 15자 이상")
        form.addRow("사용자 ID", self.login_id)
        form.addRow("비밀번호", self.password)
        if initial_setup:
            self.display_name = QLineEdit()
            self.display_name.setPlaceholderText("화면에 표시할 이름")
            self.department = QLineEdit()
            self.department.setPlaceholderText("선택 입력")
            form.addRow("표시명", self.display_name)
            form.addRow("부서 (선택)", self.department)
        card_layout.addLayout(form)
        self.error = QLabel("")
        self.error.setObjectName("errorText")
        self.error.setWordWrap(True)
        card_layout.addWidget(self.error)
        self.submit = QPushButton("최초 사용자 등록" if initial_setup else "로그인")
        self.submit.setObjectName("primaryButton")
        self.submit.clicked.connect(self._submit)
        self.password.returnPressed.connect(self._submit)
        card_layout.addWidget(self.submit)
        card_row.addWidget(card)
        card_row.addStretch()
        layout.addLayout(card_row)
        layout.addStretch(3)
        footer = QLabel("Version " + version(APP_ID))
        footer.setObjectName("secondaryText")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer)
        self.login_id.setFocus()

    def _submit(self):
        self.error.clear()
        try:
            if self.initial_setup:
                if not self.auth_service.needs_initial_user_setup():
                    self.error.setText("이미 사용자가 등록되어 있습니다.")
                    return
                self.auth_service.create_user(
                    self.login_id.text(),
                    self.password.text(),
                    self.display_name.text(),
                    self.department.text().strip() or None,
                )
                self.password.clear()
                self.registered.emit()
            else:
                user = self.auth_service.authenticate(self.login_id.text(), self.password.text())
                self.password.clear()
                self.authenticated.emit(user)
        except UserError as error:
            self.password.clear()
            self.error.setText(
                str(error) if self.initial_setup else "아이디 또는 비밀번호를 확인해주세요."
            )
        except Exception:
            self.password.clear()
            self.error.setText(
                "등록을 처리하지 못했습니다. 입력 정보를 확인해주세요."
                if self.initial_setup
                else "아이디 또는 비밀번호를 확인해주세요."
            )
