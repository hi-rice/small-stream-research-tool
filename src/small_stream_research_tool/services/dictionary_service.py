"""사전 등록·검증·정확한 별칭 lookup. 연구 의미와 단위는 추정하지 않는다."""

import math
import unicodedata
from dataclasses import asdict

from small_stream_research_tool.models.dictionary import (
    ColumnAlias,
    DataCategory,
    DataDictionaryItem,
    UnitDefinition,
)
from small_stream_research_tool.models.dictionary_errors import (
    DictionaryEntryNotFoundError,
    DictionaryItemInUseError,
    InvalidDictionaryDefinitionError,
    UnitConversionError,
)
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.utils.timestamps import utc_now_text


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        raise InvalidDictionaryDefinitionError(f"{label}은 비어 있지 않은 문자열이어야 합니다.")
    return value.strip()


def _optional_text(value, label):
    if value is not None and (not isinstance(value, str) or "\0" in value):
        raise InvalidDictionaryDefinitionError(f"{label} 형식이 올바르지 않습니다.")
    return value


def normalize_alias(raw_header: str) -> str:
    """NFC·whitespace 축약·ASCII 소문자화. 단위/구두점/단어 공백은 유지한다."""
    value = unicodedata.normalize("NFC", _text(raw_header, "별칭"))
    return " ".join(value.split()).translate(
        str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
    )


def _scope(value):
    # 명시적 scope는 trim만 적용한다. 대소문자/의미를 추정하지 않는다.
    return "GLOBAL" if value is None else _text(value, "source_scope")


def _bool(value, label):
    if not isinstance(value, bool):
        raise InvalidDictionaryDefinitionError(f"{label}은 bool이어야 합니다.")
    return value


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UnitConversionError("유한한 숫자가 필요합니다.")
    try:
        result = float(value)
    except OverflowError:
        raise UnitConversionError("유한한 숫자가 필요합니다.") from None
    if not math.isfinite(result):
        raise UnitConversionError("유한한 숫자가 필요합니다.")
    return result


class DictionaryService:
    def __init__(self, repository: DictionaryRepository):
        self._repository = repository

    @staticmethod
    def _required(entry):
        if entry is None:
            raise DictionaryEntryNotFoundError("사전 항목을 찾을 수 없습니다.")
        return entry

    def _active(self, entry):
        entry = self._required(entry)
        if not entry.is_active:
            raise InvalidDictionaryDefinitionError(
                "비활성 사전 항목은 새 등록에 사용할 수 없습니다."
            )
        return entry

    def create_category(
        self, category_key, category_name, *, parent_category_id=None, sort_order=0
    ):
        key, name = _text(category_key, "분류 키"), _text(category_name, "분류명")
        if isinstance(sort_order, bool) or not isinstance(sort_order, int):
            raise InvalidDictionaryDefinitionError("정렬 순서는 정수여야 합니다.")
        with self._repository.transaction():
            if parent_category_id is not None:
                self._active(self._repository.get_category(parent_category_id))
            timestamp = utc_now_text()
            return self._repository.create_category(
                category_key=key,
                category_name=name,
                parent_category_id=parent_category_id,
                sort_order=sort_order,
                created_at=timestamp,
                updated_at=timestamp,
            )

    def get_category(self, category_id):
        return self._repository.get_category(category_id)

    def list_categories(self, *, active_only=True):
        return self._repository.list_categories(active_only)

    def create_version(self, version, *, description=None, make_current=False):
        name = _text(version, "사전 버전")
        _optional_text(description, "설명")
        _bool(make_current, "현재 버전 여부")
        with self._repository.transaction():
            result = self._repository.create_version(
                version=name, description=description, created_at=utc_now_text()
            )
            if make_current:
                self._repository.set_current_version(result.version_id)
            return self._repository.get_version(result.version_id)

    def set_current_version(self, version_id):
        with self._repository.transaction():
            self._repository.set_current_version(version_id)

    def get_version(self, version_id):
        return self._repository.get_version(version_id)

    def get_current_version(self):
        return self._repository.get_current_version()

    def list_versions(self):
        return self._repository.list_versions()

    def create_unit(self, unit_name, unit_symbol, *, dimension=None):
        name, symbol = _text(unit_name, "단위명"), _text(unit_symbol, "단위 기호")
        _optional_text(dimension, "차원")
        with self._repository.transaction():
            timestamp = utc_now_text()
            return self._repository.create_unit(
                unit_name=name,
                unit_symbol=symbol,
                dimension=dimension,
                created_at=timestamp,
                updated_at=timestamp,
            )

    def get_unit(self, unit_id):
        return self._repository.get_unit(unit_id)

    def list_units(self, *, active_only=True):
        return self._repository.list_units(active_only)

    def register_conversion(
        self, from_unit_id, to_unit_id, factor, *, offset=0, formula_type="LINEAR", approved=False
    ):
        # 스키마에 approval 필드를 추가하지 않는다. 명시적 승인 후 등록만 허용한다.
        if approved is not True or formula_type != "LINEAR":
            raise UnitConversionError("명시적으로 승인된 LINEAR 변환만 등록할 수 있습니다.")
        factor, offset = _number(factor), _number(offset)
        with self._repository.transaction():
            self._active(self._repository.get_unit(from_unit_id))
            self._active(self._repository.get_unit(to_unit_id))
            timestamp = utc_now_text()
            return self._repository.create_conversion(
                from_unit_id=from_unit_id,
                to_unit_id=to_unit_id,
                factor=factor,
                offset=offset,
                formula_type=formula_type,
                created_at=timestamp,
                updated_at=timestamp,
            )

    def get_conversion(self, from_unit_id, to_unit_id):
        return self._repository.get_conversion(from_unit_id, to_unit_id)

    def convert_value(self, value, from_unit_id, to_unit_id):
        value = _number(value)
        conversion = self.get_conversion(from_unit_id, to_unit_id)
        units = [self.get_unit(from_unit_id), self.get_unit(to_unit_id)]
        if (
            conversion is None
            or not conversion.is_active
            or any(unit is None or not unit.is_active for unit in units)
        ):
            raise UnitConversionError("활성 단위와 등록된 활성 변환 규칙이 필요합니다.")
        return _number(value * conversion.factor + conversion.offset)

    def _validate_definition(self, values):
        values = dict(values)
        for key in ("standard_name", "internal_name"):
            values[key] = _text(values[key], key)
        if values["data_type"] not in ("REAL", "INTEGER", "TEXT", "DATE", "DATETIME"):
            raise InvalidDictionaryDefinitionError("지원하지 않는 자료형입니다.")
        if values["storage_type"] not in ("CORE", "FLEX"):
            raise InvalidDictionaryDefinitionError("지원하지 않는 저장 분류입니다.")
        _optional_text(values["description"], "설명")
        self._active(self._repository.get_category(values["category_id"]))
        if values["unit_id"] is not None:
            self._active(self._repository.get_unit(values["unit_id"]))
        return values

    def create_item(
        self,
        standard_name,
        internal_name,
        category_id,
        data_type,
        created_version_id,
        *,
        unit_id=None,
        description=None,
        storage_type="FLEX",
        analyzable=True,
        required=False,
        nullable=True,
    ):
        with self._repository.transaction():
            values = self._validate_definition(
                dict(
                    standard_name=standard_name,
                    internal_name=internal_name,
                    category_id=category_id,
                    data_type=data_type,
                    unit_id=unit_id,
                    description=description,
                    storage_type=storage_type,
                )
            )
            self._required(self._repository.get_version(created_version_id))
            for key, value in (
                ("analyzable", analyzable),
                ("required", required),
                ("nullable", nullable),
            ):
                values[key] = _bool(value, key)
            timestamp = utc_now_text()
            return self._repository.create_item(
                **values,
                created_version_id=created_version_id,
                created_at=timestamp,
                updated_at=timestamp,
            )

    def get_item(self, dictionary_id):
        return self._repository.get_item(dictionary_id)

    def get_item_by_internal_name(self, internal_name):
        return self._repository.get_item_by_internal_name(_text(internal_name, "내부명"))

    def list_items(
        self, *, category_id=None, standard_name=None, active_only=True, analyzable_only=False
    ):
        if standard_name is not None:
            standard_name = _text(standard_name, "표준명")
        return self._repository.list_items(
            category_id=category_id,
            standard_name=standard_name,
            active_only=active_only,
            analyzable_only=analyzable_only,
        )

    def update_item_definition(self, dictionary_id, **changes):
        allowed = {
            "standard_name",
            "internal_name",
            "category_id",
            "data_type",
            "unit_id",
            "description",
            "storage_type",
        }
        if not changes or not changes.keys() <= allowed:
            raise InvalidDictionaryDefinitionError("변경 가능한 정의 필드를 지정해야 합니다.")
        with self._repository.transaction():
            item = self._active(self.get_item(dictionary_id))
            if item.deprecated_version_id is not None:
                raise InvalidDictionaryDefinitionError("폐기된 항목의 의미는 변경할 수 없습니다.")
            proposed = self._validate_definition(asdict(item) | changes)
            changed = {key: proposed[key] for key in changes if proposed[key] != getattr(item, key)}
            if changed and self._repository.item_in_use(dictionary_id):
                raise DictionaryItemInUseError(
                    "사용된 항목의 의미는 변경할 수 없습니다. 새 항목을 등록하세요."
                )
            if changed:
                self._repository.update_item_definition(dictionary_id, changed, utc_now_text())
            return self.get_item(dictionary_id)

    def deprecate_item(self, dictionary_id, version_id):
        with self._repository.transaction():
            item = self._required(self.get_item(dictionary_id))
            self._required(self.get_version(version_id))
            if item.deprecated_version_id is not None:
                if item.deprecated_version_id == version_id:
                    return item
                raise InvalidDictionaryDefinitionError("기존 폐기 버전은 덮어쓸 수 없습니다.")
            self._repository.deprecate_item(dictionary_id, version_id, utc_now_text())
            return self.get_item(dictionary_id)

    def register_alias(self, dictionary_id, alias_name, *, source_scope=None):
        normalized, scope = normalize_alias(alias_name), _scope(source_scope)
        with self._repository.transaction():
            item = self._required(self.get_item(dictionary_id))
            if not self._usable(item):
                raise InvalidDictionaryDefinitionError(
                    "활성 사전 정의에만 별칭을 등록할 수 있습니다."
                )
            timestamp = utc_now_text()
            return self._repository.create_alias(
                dictionary_id=dictionary_id,
                alias_name=alias_name,
                normalized_alias=normalized,
                source_scope=scope,
                created_at=timestamp,
                updated_at=timestamp,
            )

    def get_alias(self, alias_id):
        return self._repository.get_alias(alias_id)

    def _usable(self, item):
        if item is None or not item.is_active or item.deprecated_version_id is not None:
            return False
        category = self.get_category(item.category_id)
        unit = self.get_unit(item.unit_id) if item.unit_id is not None else None
        return (
            category is not None
            and category.is_active
            and (item.unit_id is None or (unit is not None and unit.is_active))
        )

    def find_dictionary_by_header(self, raw_header, source_scope=None):
        normalized, scope = normalize_alias(raw_header), _scope(source_scope)
        alias = self._repository.find_alias(normalized, scope)
        if alias is None and scope != "GLOBAL":
            alias = self._repository.find_alias(normalized, "GLOBAL")
        # 등록된 자료별 의미가 비활성화되어도 다른 GLOBAL 의미로 바꾸지 않는다.
        if alias is None or not alias.is_active:
            return None
        item = self.get_item(alias.dictionary_id)
        return item if self._usable(item) else None

    def _deactivate(self, model, entry_id):
        with self._repository.transaction():
            self._repository.deactivate(model, entry_id, utc_now_text())

    def deactivate_category(self, category_id):
        self._deactivate(DataCategory, category_id)

    def deactivate_unit(self, unit_id):
        self._deactivate(UnitDefinition, unit_id)

    def deactivate_item(self, dictionary_id):
        self._deactivate(DataDictionaryItem, dictionary_id)

    def deactivate_alias(self, alias_id):
        self._deactivate(ColumnAlias, alias_id)
