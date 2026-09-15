"""로컬 최초 사용자 등록과 로그인 창."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


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
        self.setMinimumSize(430, 400 if initial_setup else 310)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 38, 40, 38)
        layout.setSpacing(18)
        title = QLabel("소하천 데이터 관리")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        layout.addWidget(QLabel("최초 사용자 등록" if initial_setup else "로컬 계정 로그인"))
        form = QFormLayout()
        self.login_id = QLineEdit()
        self.login_id.setPlaceholderText("아이디")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("비밀번호")
        form.addRow("아이디", self.login_id)
        form.addRow("비밀번호", self.password)
        if initial_setup:
            self.display_name = QLineEdit()
            self.department = QLineEdit()
            form.addRow("표시명", self.display_name)
            form.addRow("부서 (선택)", self.department)
        layout.addLayout(form)
        self.error = QLabel("")
        self.error.setObjectName("errorText")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        self.submit = QPushButton("최초 사용자 등록" if initial_setup else "로그인")
        self.submit.setObjectName("primaryButton")
        self.submit.clicked.connect(self._submit)
        self.password.returnPressed.connect(self._submit)
        layout.addWidget(self.submit)
        layout.addStretch()
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
        except Exception:
            self.password.clear()
            self.error.setText(
                "등록 정보를 확인해주세요."
                if self.initial_setup
                else "아이디 또는 비밀번호를 확인해주세요."
            )
