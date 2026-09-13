"""실제 001 schema의 불변 조회 모델. 연구값·자유 텍스트는 repr에 표시하지 않는다."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceFileRecord:
    source_file_id: int
    file_name: str = field(repr=False)
    original_path: str = field(repr=False)
    file_extension: str | None = field(repr=False)
    file_size: int | None
    file_hash: str | None = field(repr=False)
    file_modified_at: str | None = field(repr=False)
    source_description: str | None = field(repr=False)
    is_active: bool
    registered_at: str


@dataclass(frozen=True)
class ImportHistoryRecord:
    import_id: int
    source_file_id: int
    created_by_user_id: int | None
    batch_code: str = field(repr=False)
    import_type: str = field(repr=False)
    status: str
    started_at: str
    finished_at: str | None
    total_rows: int | None
    accepted_rows: int | None
    warning_rows: int | None
    rejected_rows: int | None
    dictionary_version_id: int | None
    schema_version_id: int | None
    settings_json: str | None = field(repr=False)
    error_code: str | None = field(repr=False)
    error_message: str | None = field(repr=False)
    created_at: str


@dataclass(frozen=True)
class ImportSheetRecord:
    import_sheet_id: int
    import_id: int
    sheet_name: str = field(repr=False)
    sheet_index: int | None
    header_start_row: int | None
    header_end_row: int | None
    data_start_row: int | None
    total_rows: int | None
    accepted_rows: int | None
    warning_rows: int | None
    rejected_rows: int | None
    status: str
    created_at: str


@dataclass(frozen=True)
class ImportColumnMappingRecord:
    mapping_id: int
    import_sheet_id: int
    source_column_index: int
    source_header: str | None = field(repr=False)
    normalized_header: str | None = field(repr=False)
    dictionary_id: int | None
    mapping_status: str = field(repr=False)
    mapping_method: str = field(repr=False)
    source_unit: str | None = field(repr=False)
    target_unit_id: int | None
    transform_rule: str | None = field(repr=False)
    user_confirmed: bool
    created_at: str


@dataclass(frozen=True)
class SmallStreamRecord:
    stream_code: str = field(repr=False)
    province_code: str = field(repr=False)
    city_county_code: str = field(repr=False)
    town_code: str = field(repr=False)
    stream_serial_no: str = field(repr=False)
    stream_name: str = field(repr=False)
    province_name: str | None = field(repr=False)
    city_county_name: str | None = field(repr=False)
    town_name: str | None = field(repr=False)
    river_system: str | None = field(repr=False)
    source_address: str | None = field(repr=False)
    source_latitude: float | None = field(repr=False)
    source_longitude: float | None = field(repr=False)
    end_address: str | None = field(repr=False)
    end_latitude: float | None = field(repr=False)
    end_longitude: float | None = field(repr=False)
    is_active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class CharacteristicValueRecord:
    characteristic_value_id: int
    stream_code: str = field(repr=False)
    dictionary_id: int
    value_number: float | None = field(repr=False)
    value_integer: int | None = field(repr=False)
    value_text: str | None = field(repr=False)
    value_date: str | None = field(repr=False)
    unit_id: int | None
    original_value: str | None = field(repr=False)
    original_unit: str | None = field(repr=False)
    import_id: int | None
    import_sheet_id: int | None
    source_row: int | None
    mapping_id: int | None
    source_type: str = field(repr=False)
    source_reference: str | None = field(repr=False)
    reference_year: int | None
    is_representative: bool
    quality_status: str = field(repr=False)
    is_active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class CharacteristicProvenance:
    """명시적으로 저장된 FK만 조회한다. 교차 소속 판단·NULL 참조 추정은 하지 않는다."""

    value: CharacteristicValueRecord
    mapping: ImportColumnMappingRecord | None
    sheet: ImportSheetRecord | None
    history: ImportHistoryRecord | None
    source_file: SourceFileRecord | None
