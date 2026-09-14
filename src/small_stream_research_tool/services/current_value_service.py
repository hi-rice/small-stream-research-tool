"""사용자가 명시적으로 선택한 현재값만 변경한다. QC 확인·캐시·이력은 하나의 transaction이다."""

import json

from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.models.current_value import CurrentValueSelectionResult
from small_stream_research_tool.models.current_value_errors import (
    CurrentValueBlockedByQualityError,
    CurrentValueConfirmationRequiredError,
    CurrentValueInvariantError,
    CurrentValuePersistenceError,
    CurrentValueSelectionError,
)
from small_stream_research_tool.repositories.current_value_repository import CurrentValueRepository
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.repositories.import_persistence_repository import (
    CharacteristicValueRepository,
    SmallStreamRepository,
)
from small_stream_research_tool.repositories.quality_control_repository import (
    QualityControlRepository,
)
from small_stream_research_tool.repositories.user_repository import UserRepository
from small_stream_research_tool.utils.timestamps import utc_now_text

SELECTION_REASONS = frozenset({"RESEARCHER_SELECTION", "SOURCE_REVIEW", "QC_REVIEW_CONFIRMED"})


def _require(condition):
    if not condition:
        raise CurrentValueSelectionError()


def _id(value):
    return type(value) is int and 0 < value < 2**63


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class CurrentValueService:
    def __init__(self, connection):
        self._connection = connection
        self._repository = CurrentValueRepository(connection)
        self._values = CharacteristicValueRepository(connection)
        self._streams = SmallStreamRepository(connection)
        self._dictionary = DictionaryRepository(connection)
        self._users = UserRepository(connection)
        self._quality = QualityControlRepository(connection)

    def _current(self, stream_code, dictionary_id):
        representatives = self._repository.active_representative_ids(stream_code, dictionary_id)
        cached_id = self._repository.cache_value_id(stream_code, dictionary_id)
        if not representatives and cached_id is None:
            return None
        if len(representatives) != 1 or representatives[0] != cached_id:
            raise CurrentValueInvariantError()
        value = self._values.get_by_id(cached_id)
        if (
            value is None
            or not value.is_active
            or not value.is_representative
            or value.stream_code != stream_code
            or value.dictionary_id != dictionary_id
        ):
            raise CurrentValueInvariantError()
        return cached_id

    def select_current_value(
        self, characteristic_value_id, actor_user_id, *, confirm_review_required=False, reason=None
    ):
        try:
            _require(_id(characteristic_value_id) and _id(actor_user_id))
            _require(type(confirm_review_required) is bool)
            _require(reason is None or (type(reason) is str and reason in SELECTION_REASONS))
            with transaction(self._connection):
                actor = self._users.find_by_user_id(actor_user_id)
                _require(actor is not None and actor.is_active)
                target = self._values.get_by_id(characteristic_value_id)
                _require(target is not None and target.is_active)
                stream = self._streams.get_by_stream_code(target.stream_code)
                item = self._dictionary.get_item(target.dictionary_id)
                _require(stream is not None and stream.is_active)
                _require(
                    item is not None
                    and item.is_active
                    and item.deprecated_version_id is None
                    and item.storage_type == "FLEX"
                )
                category = self._dictionary.get_category(item.category_id)
                _require(category is not None and category.is_active)
                counts = self._quality.active_severity_counts_for_value(characteristic_value_id)
                if counts.error:
                    raise CurrentValueBlockedByQualityError()
                confirmation_required = bool(counts.warning or counts.info)
                if confirmation_required and not confirm_review_required:
                    raise CurrentValueConfirmationRequiredError()
                previous = self._current(target.stream_code, target.dictionary_id)
                changed = previous != characteristic_value_id
                timestamp = utc_now_text()
                history_id = None
                used = confirmation_required and confirm_review_required
                if changed:
                    if previous is not None:
                        self._repository.set_representative(
                            previous, target.stream_code, target.dictionary_id, selected=False
                        )
                    self._repository.set_representative(
                        characteristic_value_id,
                        target.stream_code,
                        target.dictionary_id,
                        selected=True,
                    )
                    self._repository.set_cache(
                        target.stream_code, target.dictionary_id, characteristic_value_id, timestamp
                    )
                    history_id = self._repository.insert_history(
                        record_key=_json(
                            {
                                "stream_code": target.stream_code,
                                "dictionary_id": target.dictionary_id,
                            }
                        ),
                        old_value=_json({"characteristic_value_id": previous}),
                        new_value=_json(
                            {
                                "characteristic_value_id": characteristic_value_id,
                                "qc_status": counts.status,
                                "confirmation_required": confirmation_required,
                                "confirmation_used": used,
                            }
                        ),
                        actor_user_id=actor_user_id,
                        reason=reason,
                        timestamp=timestamp,
                    )
                    if (
                        self._current(target.stream_code, target.dictionary_id)
                        != characteristic_value_id
                    ):
                        raise CurrentValueInvariantError()
                result = CurrentValueSelectionResult(
                    changed,
                    target.stream_code,
                    target.dictionary_id,
                    previous,
                    characteristic_value_id,
                    counts.status,
                    confirmation_required,
                    used,
                    history_id,
                    timestamp,
                )
            return result
        except CurrentValueSelectionError:
            raise
        except Exception:
            raise CurrentValuePersistenceError() from None
