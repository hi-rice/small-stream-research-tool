"""사전 관련 6개 테이블의 명시적 데이터 모델."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DataCategory:
    category_id: int
    category_key: str
    category_name: str
    parent_category_id: int | None
    sort_order: int
    is_active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class DictionaryVersion:
    version_id: int
    version: str
    description: str | None
    is_current: bool
    created_at: str


@dataclass(frozen=True)
class UnitDefinition:
    unit_id: int
    unit_name: str
    unit_symbol: str
    dimension: str | None
    is_active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class UnitConversion:
    conversion_id: int
    from_unit_id: int
    to_unit_id: int
    factor: float
    offset: float
    formula_type: str
    is_active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class DataDictionaryItem:
    dictionary_id: int
    standard_name: str
    internal_name: str
    category_id: int
    data_type: str
    unit_id: int | None
    description: str | None
    storage_type: str
    analyzable: bool
    required: bool
    nullable: bool
    created_version_id: int
    deprecated_version_id: int | None
    is_active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ColumnAlias:
    alias_id: int
    dictionary_id: int
    alias_name: str
    normalized_alias: str
    source_scope: str
    is_active: bool
    created_at: str
    updated_at: str
