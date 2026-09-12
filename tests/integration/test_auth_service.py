"""임시 DB·synthetic 계정만 사용하는 인증 통합 테스트."""

import logging
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timedelta

import pytest

from small_stream_research_tool.database import connect_database, initialize_database
from small_stream_research_tool.models.errors import (
    AuthenticationError,
    DuplicateLoginIdError,
    InactiveUserError,
    InvalidLoginIdError,
    InvalidPasswordError,
    InvalidUserProfileError,
    UserNotFoundError,
)
from small_stream_research_tool.repositories.user_repository import UserRepository
from small_stream_research_tool.security.passwords import hash_password, verify_password
from small_stream_research_tool.services.auth_service import AuthService

PASSWORD = "synthetic original passphrase"
NEW_PASSWORD = "synthetic replacement passphrase"
STAMP = "2026-01-01T00:00:00Z"


@pytest.fixture
def context(tmp_path, monkeypatch):
    # 기본 경로도 임시 위치로 격리한다. 제품 코드에는 초기화 부작용이 없다.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "unused-appdata"))
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as connection:
        repository = UserRepository(connection)
        yield connection, repository, AuthService(repository), path
    assert not (tmp_path / "unused-appdata").exists()


def create(service):
    return service.create_user("  Researcher_01  ", PASSWORD, "가상 연구자", "가상 부서")


def test_setup_creation_lookup_and_public_model(context):
    connection, repository, service, path = context
    assert service.needs_initial_user_setup()
    assert repository.count_users() == 0
    assert repository.find_by_user_id(9999) is None
    assert repository.find_by_login_id("missing") is None
    user = create(service)
    assert not service.needs_initial_user_setup()
    assert repository.count_users() == 1
    assert user.login_id == "researcher_01"
    assert user.display_name == "가상 연구자" and user.department == "가상 부서"
    assert user.role is None and user.last_login_at is None and user.is_active
    record = repository.find_by_user_id(user.user_id)
    assert record == repository.find_by_login_id("researcher_01")
    assert verify_password(PASSWORD, record.password_hash)
    assert record.password_hash not in repr(record)
    assert "password_hash" not in asdict(user)
    assert not hasattr(user, "password_hash")
    for stamp in (user.created_at, user.updated_at):
        assert stamp.endswith("Z")
        assert datetime.fromisoformat(stamp).utcoffset() == timedelta(0)
    assert user.created_at == user.updated_at
    assert PASSWORD not in "\n".join(connection.iterdump())
    assert PASSWORD.encode() not in path.read_bytes()
    assert connection.execute("SELECT COUNT(*) FROM schema_version").fetchone() == (1,)


def test_duplicate_case_normalization(context):
    _, repository, service, _ = context
    create(service)
    with pytest.raises(DuplicateLoginIdError):
        service.create_user("RESEARCHER_01", PASSWORD, "중복 가상 연구자")
    assert repository.count_users() == 1


def test_repository_unique_error_translation(context):
    _, repository, service, _ = context
    user = create(service)
    encoded = repository.find_by_user_id(user.user_id).password_hash
    with pytest.raises(DuplicateLoginIdError):
        with repository.transaction():
            repository.create_user(
                login_id=user.login_id,
                password_hash=encoded,
                display_name="가상",
                department=None,
                role=None,
                timestamp=STAMP,
            )
    assert repository.count_users() == 1


@pytest.mark.parametrize("name", ["", " \t", None])
def test_required_display_name(context, name):
    _, repository, service, _ = context
    with pytest.raises(InvalidUserProfileError):
        service.create_user("test.user", PASSWORD, name)
    assert repository.count_users() == 0


def test_nullable_profile_and_role_has_no_invented_semantics(context):
    _, _, service, _ = context
    user = service.create_user("test.user", PASSWORD, "가상", role="임의 메타데이터")
    assert user.department is None and user.role == "임의 메타데이터"


@pytest.mark.parametrize(
    "login,password,error",
    [
        ("bad id", PASSWORD, InvalidLoginIdError),
        ("missing.user", PASSWORD, UserNotFoundError),
        ("researcher_01", "wrong synthetic password", AuthenticationError),
    ],
)
def test_failed_login_preserves_timestamps(context, login, password, error):
    connection, repository, service, _ = context
    user = create(service)
    connection.execute("UPDATE app_user SET last_login_at=?,updated_at=?", (STAMP, STAMP))
    before = repository.find_by_user_id(user.user_id)
    with pytest.raises(error):
        service.authenticate(login, password)
    assert repository.find_by_user_id(user.user_id) == before


def test_successful_login_records_utc(context, monkeypatch):
    _, repository, service, _ = context
    user = create(service)
    monkeypatch.setattr(
        "small_stream_research_tool.services.auth_service.utc_now_text", lambda: STAMP
    )
    result = service.authenticate(" RESEARCHER_01 ", PASSWORD)
    assert result.user_id == user.user_id
    assert result.last_login_at == STAMP and result.updated_at == STAMP
    assert repository.find_by_user_id(user.user_id).last_login_at == STAMP
    assert not hasattr(result, "password_hash")


def test_deactivate_and_activate_preserve_user_and_references(context):
    connection, repository, service, _ = context
    user = create(service)
    connection.execute(
        "INSERT INTO source_file(file_name,original_path,registered_at) "
        "VALUES ('synthetic','synthetic',?)",
        (STAMP,),
    )
    connection.execute(
        "INSERT INTO import_history(source_file_id,created_by_user_id,batch_code,"
        "import_type,status,started_at,created_at) VALUES (1,?,'test','test','SUCCESS',?,?)",
        (user.user_id, STAMP, STAMP),
    )
    connection.execute(
        "INSERT INTO data_quality_issue(issue_type,severity,message,reviewed_by_user_id,"
        "created_at) VALUES ('test','INFO','synthetic',?,?)",
        (user.user_id, STAMP),
    )
    connection.execute(
        "INSERT INTO record_history(table_name,record_key,change_type,actor_user_id,"
        "changed_at) VALUES ('app_user','1','test',?,?)",
        (user.user_id, STAMP),
    )
    service.set_active(user.user_id, False)
    inactive = repository.find_by_user_id(user.user_id)
    assert not inactive.is_active
    assert not service.needs_initial_user_setup()
    assert repository.count_users() == 1
    assert not hasattr(repository, "delete_user")
    assert not hasattr(repository, "delete")
    with pytest.raises(InactiveUserError):
        service.authenticate(user.login_id, PASSWORD)
    with pytest.raises(InactiveUserError):
        service.change_password(user.user_id, PASSWORD, NEW_PASSWORD)
    assert repository.find_by_user_id(user.user_id) == inactive
    for table, column in [
        ("import_history", "created_by_user_id"),
        ("data_quality_issue", "reviewed_by_user_id"),
        ("record_history", "actor_user_id"),
    ]:
        assert connection.execute(f"SELECT {column} FROM {table}").fetchone() == (user.user_id,)
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    service.set_active(user.user_id, True)
    assert service.authenticate(user.login_id, PASSWORD).is_active


def test_password_change(context, monkeypatch):
    _, repository, service, _ = context
    user = create(service)
    before = repository.find_by_user_id(user.user_id)
    monkeypatch.setattr(
        "small_stream_research_tool.services.auth_service.utc_now_text", lambda: STAMP
    )
    service.change_password(user.user_id, PASSWORD, NEW_PASSWORD)
    after = repository.find_by_user_id(user.user_id)
    assert after.password_hash != before.password_hash
    assert after.updated_at == STAMP
    assert after.created_at == before.created_at and after.last_login_at is None
    with pytest.raises(AuthenticationError):
        service.authenticate(user.login_id, PASSWORD)
    assert service.authenticate(user.login_id, NEW_PASSWORD).user_id == user.user_id


@pytest.mark.parametrize(
    "current,new,error",
    [
        ("wrong", NEW_PASSWORD, AuthenticationError),
        (PASSWORD, "short", InvalidPasswordError),
        (PASSWORD, " " * 20, InvalidPasswordError),
    ],
)
def test_failed_password_change_preserves_hash(context, current, new, error):
    _, repository, service, _ = context
    user = create(service)
    before = repository.find_by_user_id(user.user_id)
    with pytest.raises(error):
        service.change_password(user.user_id, current, new)
    assert repository.find_by_user_id(user.user_id) == before


@pytest.mark.parametrize(
    "method", ["create_user", "update_password_hash", "update_last_login_at", "set_active"]
)
def test_write_failure_rolls_back_entire_operation(context, monkeypatch, method):
    connection, repository, service, _ = context
    user = None if method == "create_user" else create(service)
    before = list(connection.iterdump())
    original = getattr(repository, method)

    def fail_after_write(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic write failure")

    monkeypatch.setattr(repository, method, fail_after_write)
    with pytest.raises(RuntimeError, match="synthetic write failure"):
        if method == "create_user":
            create(service)
        elif method == "update_password_hash":
            service.change_password(user.user_id, PASSWORD, NEW_PASSWORD)
        elif method == "update_last_login_at":
            service.authenticate(user.login_id, PASSWORD)
        else:
            service.set_active(user.user_id, False)
    assert not connection.in_transaction
    assert list(connection.iterdump()) == before


def test_repository_requires_transaction_and_reports_missing_user(context):
    _, repository, _, _ = context
    with pytest.raises(RuntimeError, match="explicit transaction"):
        repository.update_last_login_at(999, STAMP)
    with repository.transaction():
        for operation in (
            lambda: repository.update_last_login_at(999, STAMP),
            lambda: repository.update_password_hash(999, "synthetic-hash", STAMP),
            lambda: repository.set_active(999, False, STAMP),
        ):
            with pytest.raises(UserNotFoundError):
                operation()


def test_password_and_hash_never_logged(context, caplog):
    connection, repository, service, path = context
    with caplog.at_level(logging.DEBUG):
        user = create(service)
        old_hash = repository.find_by_user_id(user.user_id).password_hash
        service.authenticate(user.login_id, PASSWORD)
        with pytest.raises(AuthenticationError) as failure:
            service.change_password(user.user_id, "synthetic invalid secret", NEW_PASSWORD)
        service.change_password(user.user_id, PASSWORD, NEW_PASSWORD)
        new_hash = repository.find_by_user_id(user.user_id).password_hash
    for secret in (PASSWORD, NEW_PASSWORD, "synthetic invalid secret", old_hash, new_hash):
        assert secret not in caplog.text
        assert secret not in str(failure.value)
        assert secret not in repr(user)
    dump = "\n".join(connection.iterdump())
    for password in (PASSWORD, NEW_PASSWORD):
        assert password not in dump
        assert password.encode() not in path.read_bytes()


def test_database_check_rejects_repository_raw_login_id(context):
    _, repository, _, _ = context
    with pytest.raises(sqlite3.IntegrityError):
        with repository.transaction():
            repository.create_user(
                login_id="UPPERCASE",
                password_hash=hash_password(PASSWORD),
                display_name="synthetic",
                department=None,
                role=None,
                timestamp=STAMP,
            )
    assert repository.count_users() == 0
