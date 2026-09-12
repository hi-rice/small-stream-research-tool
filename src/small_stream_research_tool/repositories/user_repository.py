"""사용자 저장소. 인증/정규화 정책과 commit은 Service가 결정한다."""

import sqlite3
from contextlib import AbstractContextManager

from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.models.errors import DuplicateLoginIdError, UserNotFoundError
from small_stream_research_tool.models.user import UserRecord

_COLUMNS = (
    "user_id, login_id, password_hash, display_name, department, role, "
    "is_active, created_at, updated_at, last_login_at"
)


class UserRepository:
    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection

    def transaction(self) -> AbstractContextManager[None]:
        return transaction(self._connection)

    def _require_transaction(self) -> None:
        if not self._connection.in_transaction:
            raise RuntimeError("User writes require an explicit transaction")

    @staticmethod
    def _to_model(row) -> UserRecord | None:
        if row is None:
            return None
        return UserRecord(
            user_id=row[0],
            login_id=row[1],
            password_hash=row[2],
            display_name=row[3],
            department=row[4],
            role=row[5],
            is_active=bool(row[6]),
            created_at=row[7],
            updated_at=row[8],
            last_login_at=row[9],
        )

    def find_by_login_id(self, login_id: str) -> UserRecord | None:
        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM app_user WHERE login_id=?", (login_id,)
        ).fetchone()
        return self._to_model(row)

    def find_by_user_id(self, user_id: int) -> UserRecord | None:
        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM app_user WHERE user_id=?", (user_id,)
        ).fetchone()
        return self._to_model(row)

    def count_users(self) -> int:
        return self._connection.execute("SELECT COUNT(*) FROM app_user").fetchone()[0]

    def create_user(
        self,
        *,
        login_id: str,
        password_hash: str,
        display_name: str,
        department: str | None,
        role: str | None,
        timestamp: str,
    ) -> UserRecord:
        self._require_transaction()
        try:
            cursor = self._connection.execute(
                "INSERT INTO app_user "
                "(login_id,password_hash,display_name,department,role,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (login_id, password_hash, display_name, department, role, timestamp, timestamp),
            )
        except sqlite3.IntegrityError as error:
            if error.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_UNIQUE:
                raise DuplicateLoginIdError("이미 등록된 로그인 ID입니다.") from None
            raise
        return self._get_required(cursor.lastrowid)

    def _get_required(self, user_id: int) -> UserRecord:
        user = self.find_by_user_id(user_id)
        if user is None:
            raise UserNotFoundError("사용자를 찾을 수 없습니다.")
        return user

    def update_password_hash(self, user_id: int, password_hash: str, timestamp: str) -> None:
        self._require_transaction()
        cursor = self._connection.execute(
            "UPDATE app_user SET password_hash=?, updated_at=? WHERE user_id=?",
            (password_hash, timestamp, user_id),
        )
        if cursor.rowcount != 1:
            raise UserNotFoundError("사용자를 찾을 수 없습니다.")

    def update_last_login_at(self, user_id: int, timestamp: str) -> None:
        self._require_transaction()
        cursor = self._connection.execute(
            "UPDATE app_user SET last_login_at=?, updated_at=? WHERE user_id=?",
            (timestamp, timestamp, user_id),
        )
        if cursor.rowcount != 1:
            raise UserNotFoundError("사용자를 찾을 수 없습니다.")

    def set_active(self, user_id: int, is_active: bool, timestamp: str) -> None:
        self._require_transaction()
        if not isinstance(is_active, bool):
            raise ValueError("is_active must be a bool")
        cursor = self._connection.execute(
            "UPDATE app_user SET is_active=?, updated_at=? WHERE user_id=?",
            (int(is_active), timestamp, user_id),
        )
        if cursor.rowcount != 1:
            raise UserNotFoundError("사용자를 찾을 수 없습니다.")
