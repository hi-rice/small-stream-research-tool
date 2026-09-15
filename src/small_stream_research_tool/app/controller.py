"""GUI workflow 조립. Widget에는 DB 연결이나 Repository를 전달하지 않는다."""

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from small_stream_research_tool.database import connect_database, initialize_database
from small_stream_research_tool.repositories.user_repository import UserRepository
from small_stream_research_tool.services.auth_service import AuthService
from small_stream_research_tool.ui.login import LoginWindow
from small_stream_research_tool.ui.main_window import MainWindow


@dataclass(frozen=True)
class GuiSession:
    user_id: int
    display_name: str
    department: str | None
    role: str | None


class ApplicationController:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        initialize_database(db_path)
        self.connection = connect_database(db_path)
        self.auth_service = AuthService(UserRepository(self.connection))
        self.session = None
        self.login_window = None
        self.main_window = None

    def start(self):
        self._show_login()

    def _show_login(self):
        initial = self.auth_service.needs_initial_user_setup()
        self.login_window = LoginWindow(self.auth_service, initial_setup=initial)
        self.login_window.registered.connect(self._registered)
        self.login_window.authenticated.connect(self._authenticated)
        self.login_window.show()

    def _registered(self):
        self.login_window.close()
        self.login_window.deleteLater()
        self._show_login()

    def _authenticated(self, user):
        self.session = GuiSession(user.user_id, user.display_name, user.department, user.role)
        self.main_window = MainWindow(self.db_path, self.session)
        self.main_window.logout_requested.connect(self.logout)
        self.main_window.show()
        self.login_window.close()
        self.login_window.deleteLater()
        self.login_window = None

    def logout(self):
        self.session = None
        self.main_window.close()
        self.main_window.deleteLater()
        self.main_window = None
        self._show_login()

    def close(self):
        if self.main_window:
            self.main_window.close()
        if self.login_window:
            self.login_window.close()
        with closing(self.connection):
            pass
