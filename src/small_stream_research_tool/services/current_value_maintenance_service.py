"""특성값 lifecycle과 현재값 참조 캐시를 명시적 transaction에서 유지한다."""

import json

from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.models.current_value_maintenance import (
    CacheRebuildResult,
    ValueLifecycleResult,
)
from small_stream_research_tool.models.current_value_maintenance_errors import (
    CurrentUseLossConfirmationRequiredError,
    CurrentValueMaintenanceError,
    MaintenanceInvariantError,
    MaintenancePersistenceError,
    MaintenanceValidationError,
)
from small_stream_research_tool.repositories.current_value_maintenance_repository import (
    CurrentValueMaintenanceRepository,
)
from small_stream_research_tool.repositories.import_persistence_repository import (
    CharacteristicValueRepository,
)
from small_stream_research_tool.repositories.user_repository import UserRepository
from small_stream_research_tool.services.current_value_service import SELECTION_REASONS
from small_stream_research_tool.utils.timestamps import utc_now_text


def _id(value):
    return type(value) is int and 0 < value < 2**63


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class CurrentValueMaintenanceService:
    def __init__(self, connection):
        self._connection = connection
        self._repository = CurrentValueMaintenanceRepository(connection)
        self._values = CharacteristicValueRepository(connection)
        self._users = UserRepository(connection)

    def _actor(self, actor_user_id):
        if not _id(actor_user_id):
            raise MaintenanceValidationError()
        actor = self._users.find_by_user_id(actor_user_id)
        if actor is None or not actor.is_active:
            raise MaintenanceValidationError()

    def _reason(self, reason_code):
        if type(reason_code) is not str or reason_code not in SELECTION_REASONS:
            raise MaintenanceValidationError()

    def _value(self, value_id):
        if not _id(value_id):
            raise MaintenanceValidationError()
        value = self._values.get_by_id(value_id)
        if value is None:
            raise MaintenanceValidationError()
        return value

    def _normal_current(self, value):
        reps = self._repository.representatives(value.stream_code, value.dictionary_id)
        cache = self._repository.cache_id(value.stream_code, value.dictionary_id)
        if not reps and cache is None:
            return None
        if len(reps) != 1 or reps[0] != cache:
            raise MaintenanceInvariantError()
        representative = self._values.get_by_id(cache)
        if (
            representative is None
            or not representative.is_active
            or not representative.is_representative
            or representative.stream_code != value.stream_code
            or representative.dictionary_id != value.dictionary_id
        ):
            raise MaintenanceInvariantError()
        return cache

    def deactivate_value(
        self, value_id, actor_user_id, *, confirm_current_use_loss=False, reason_code
    ):
        try:
            if type(confirm_current_use_loss) is not bool:
                raise MaintenanceValidationError()
            self._reason(reason_code)
            with transaction(self._connection):
                self._actor(actor_user_id)
                value = self._value(value_id)
                current = self._normal_current(value)
                timestamp = utc_now_text()
                history_id = None
                released = False
                if value.is_active:
                    if value.is_representative:
                        if current != value_id:
                            raise MaintenanceInvariantError()
                        if not confirm_current_use_loss:
                            raise CurrentUseLossConfirmationRequiredError()
                        self._repository.release_representative(value_id)
                        self._repository.delete_cache(value.stream_code, value.dictionary_id)
                        released = True
                    self._repository.set_active(value_id, True, False)
                    history_id = self._repository.insert_history(
                        _json({"characteristic_value_id": value_id}),
                        _json({"is_active": True, "is_representative": value.is_representative}),
                        _json({"is_active": False, "is_representative": False}),
                        "DEACTIVATE",
                        actor_user_id,
                        reason_code,
                        timestamp,
                        "is_active",
                    )
                    after = self._values.get_by_id(value_id)
                    if after.is_active or after.is_representative != (
                        value.is_representative and not released
                    ):
                        raise MaintenanceInvariantError()
                    if self._normal_current(value) != (None if released else current):
                        raise MaintenanceInvariantError()
                result = ValueLifecycleResult(
                    bool(history_id),
                    value_id,
                    value.stream_code,
                    value.dictionary_id,
                    released,
                    history_id,
                    timestamp,
                )
            return result
        except CurrentValueMaintenanceError:
            raise
        except Exception:
            raise MaintenancePersistenceError() from None

    def restore_value(self, value_id, actor_user_id, *, reason_code):
        try:
            self._reason(reason_code)
            with transaction(self._connection):
                self._actor(actor_user_id)
                value = self._value(value_id)
                self._normal_current(value)
                if not value.is_active and value.is_representative:
                    raise MaintenanceInvariantError()
                timestamp = utc_now_text()
                history_id = None
                if not value.is_active:
                    self._repository.set_active(value_id, False, True)
                    history_id = self._repository.insert_history(
                        _json({"characteristic_value_id": value_id}),
                        _json({"is_active": False}),
                        _json({"is_active": True, "is_representative": False}),
                        "RESTORE",
                        actor_user_id,
                        reason_code,
                        timestamp,
                        "is_active",
                    )
                    after = self._values.get_by_id(value_id)
                    if not after.is_active or after.is_representative:
                        raise MaintenanceInvariantError()
                    self._normal_current(value)
                result = ValueLifecycleResult(
                    bool(history_id),
                    value_id,
                    value.stream_code,
                    value.dictionary_id,
                    False,
                    history_id,
                    timestamp,
                )
            return result
        except CurrentValueMaintenanceError:
            raise
        except Exception:
            raise MaintenancePersistenceError() from None

    def rebuild_current_value_cache(self, actor_user_id, *, stream_code=None, dictionary_id=None):
        try:
            if (stream_code is None) != (dictionary_id is None):
                raise MaintenanceValidationError()
            if stream_code is not None and (
                type(stream_code) is not str
                or len(stream_code) != 11
                or not stream_code.isascii()
                or not stream_code.isdigit()
                or not _id(dictionary_id)
            ):
                raise MaintenanceValidationError()
            with transaction(self._connection):
                self._actor(actor_user_id)
                timestamp = utc_now_text()
                changed, histories = [], []
                pairs = self._repository.pairs(stream_code, dictionary_id)
                if stream_code is not None and not pairs:
                    pairs = ((stream_code, dictionary_id),)
                for code, item_id in pairs:
                    reps = self._repository.representatives(code, item_id)
                    if len(reps) > 1:
                        raise MaintenanceInvariantError()
                    desired = reps[0] if reps else None
                    if desired is not None:
                        value = self._values.get_by_id(desired)
                        if (
                            value is None
                            or not value.is_active
                            or not value.is_representative
                            or value.stream_code != code
                            or value.dictionary_id != item_id
                        ):
                            raise MaintenanceInvariantError()
                    old = self._repository.cache_id(code, item_id)
                    if old == desired:
                        continue
                    if desired is None:
                        self._repository.delete_cache(code, item_id)
                    else:
                        self._repository.upsert_cache(code, item_id, desired, timestamp)
                    if self._repository.cache_id(code, item_id) != desired:
                        raise MaintenanceInvariantError()
                    histories.append(
                        self._repository.insert_history(
                            _json({"stream_code": code, "dictionary_id": item_id}),
                            _json({"characteristic_value_id": old}),
                            _json({"characteristic_value_id": desired}),
                            "CACHE_REBUILD",
                            actor_user_id,
                            None,
                            timestamp,
                            "characteristic_value_id",
                        )
                    )
                    changed.append((code, item_id))
                result = CacheRebuildResult(tuple(changed), tuple(histories), timestamp)
            return result
        except CurrentValueMaintenanceError:
            raise
        except Exception:
            raise MaintenancePersistenceError() from None
