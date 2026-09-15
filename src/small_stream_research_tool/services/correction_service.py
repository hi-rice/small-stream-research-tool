"""새 보정값과 ID 기반 이력만 원자적으로 생성한다. QC/현재값 선택은 별도 작업이다."""

import json

from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.models.correction import (
    CorrectionCreationResult,
    CorrectionRequest,
    UnitInheritance,
)
from small_stream_research_tool.models.correction_errors import (
    CorrectionError,
    CorrectionPersistenceError,
    CorrectionValidationError,
)
from small_stream_research_tool.models.excel import ExcelCell
from small_stream_research_tool.models.import_persistence import CharacteristicValueRecord
from small_stream_research_tool.models.import_preparation_errors import ValueNormalizationError
from small_stream_research_tool.repositories.correction_repository import CorrectionRepository
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.repositories.import_persistence_repository import (
    CharacteristicValueRepository,
    SmallStreamRepository,
)
from small_stream_research_tool.repositories.user_repository import UserRepository
from small_stream_research_tool.services.current_value_service import SELECTION_REASONS
from small_stream_research_tool.services.value_normalization_service import normalize_cell
from small_stream_research_tool.utils.timestamps import utc_now_text

_FIELDS = {
    "INTEGER": "value_integer",
    "REAL": "value_number",
    "TEXT": "value_text",
    "DATE": "value_date",
    "DATETIME": "value_date",
}


def _require(condition):
    if not condition:
        raise CorrectionValidationError()


def _id(value):
    return type(value) is int and 0 < value < 2**63


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _typed(value, data_type):
    _require(data_type in _FIELDS)
    try:
        if data_type == "TEXT":
            _require(type(value) is str)
            value.encode("utf-8")
            # Excel 정규화의 trim/빈칸→결측은 명시적 TEXT 보정에는 적용하지 않는다.
            result = value
        else:
            if data_type == "INTEGER":
                _require(type(value) is int)
            # 위치는 변환기의 입력 adapter일 뿐이며 provenance로 저장하지 않는다.
            result = normalize_cell(ExcelCell(1, 1, "A", value, "n", False, "General"), data_type)
            _require(result is not None)
        return {
            name: result if name == _FIELDS[data_type] else None for name in set(_FIELDS.values())
        }
    except (ValueNormalizationError, UnicodeError):
        raise CorrectionValidationError() from None


class CorrectionService:
    def __init__(self, connection):
        self._connection = connection
        self._values = CharacteristicValueRepository(connection)
        self._streams = SmallStreamRepository(connection)
        self._dictionary = DictionaryRepository(connection)
        self._users = UserRepository(connection)
        self._repository = CorrectionRepository(connection)

    def _unit(self, requested, source, item):
        if requested is UnitInheritance.SOURCE:
            unit_id = source.unit_id
        else:
            _require(requested is None or _id(requested))
            _require(requested == item.unit_id)
            unit_id = requested
        if unit_id is not None:
            unit = self._dictionary.get_unit(unit_id)
            _require(unit is not None and unit.is_active)
        return unit_id

    def _verify(self, source, expected, history_id, history):
        if (
            self._values.get_by_id(source.characteristic_value_id) != source
            or self._values.get_by_id(expected.characteristic_value_id) != expected
            or self._repository.get_history(history_id) != history
        ):
            raise CorrectionPersistenceError()

    def create_correction(self, request: CorrectionRequest) -> CorrectionCreationResult:
        try:
            _require(type(request) is CorrectionRequest)
            _require(_id(request.source_value_id) and _id(request.actor_user_id))
            _require(type(request.reason_code) is str and request.reason_code in SELECTION_REASONS)
            with transaction(self._connection):
                source = self._values.get_by_id(request.source_value_id)
                _require(source is not None and source.is_active)
                actor = self._users.find_by_user_id(request.actor_user_id)
                _require(actor is not None and actor.is_active)
                stream = self._streams.get_by_stream_code(source.stream_code)
                _require(stream is not None and stream.is_active)
                item = self._dictionary.get_item(source.dictionary_id)
                _require(
                    item is not None
                    and item.is_active
                    and item.deprecated_version_id is None
                    and item.storage_type == "FLEX"
                )
                category = self._dictionary.get_category(item.category_id)
                _require(category is not None and category.is_active)
                typed = _typed(request.corrected_value, item.data_type)
                unit_id = self._unit(request.corrected_unit_id, source, item)
                timestamp = utc_now_text()
                data = dict(
                    **typed,
                    stream_code=source.stream_code,
                    dictionary_id=source.dictionary_id,
                    unit_id=unit_id,
                    original_value=None,
                    original_unit=None,
                    import_id=None,
                    import_sheet_id=None,
                    source_row=None,
                    mapping_id=None,
                    source_type="USER_CORRECTION",
                    source_reference=None,
                    reference_year=source.reference_year,
                    is_representative=False,
                    quality_status="UNREVIEWED",
                    is_active=True,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                correction = self._values.create(**data)
                expected = CharacteristicValueRecord(correction.characteristic_value_id, **data)
                key = _json(
                    {"stream_code": source.stream_code, "dictionary_id": source.dictionary_id}
                )
                old = _json({"source_value_id": source.characteristic_value_id})
                new = _json(
                    {
                        "correction_value_id": correction.characteristic_value_id,
                        "event": "USER_CORRECTION_CREATE",
                    }
                )
                history_id = self._repository.insert_history(
                    record_key=key,
                    old_value=old,
                    new_value=new,
                    actor_user_id=request.actor_user_id,
                    reason=request.reason_code,
                    timestamp=timestamp,
                )
                self._verify(
                    source,
                    expected,
                    history_id,
                    (
                        "characteristic_value",
                        key,
                        old,
                        new,
                        "CORRECTION",
                        request.reason_code,
                        request.actor_user_id,
                        timestamp,
                        None,
                        None,
                        None,
                        None,
                    ),
                )
                result = CorrectionCreationResult(
                    correction.characteristic_value_id,
                    request.source_value_id,
                    source.stream_code,
                    source.dictionary_id,
                    request.actor_user_id,
                    history_id,
                    timestamp,
                )
            return result
        except CorrectionError:
            raise
        except Exception:
            raise CorrectionPersistenceError() from None
