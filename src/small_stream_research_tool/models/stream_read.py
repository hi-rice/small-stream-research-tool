"""Phase 9A 조회 입력과 제한된 불변 표시 모델."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StreamListRequest:
    page: int = 1
    page_size: int = 50
    search: str = ""
    province_code: str | None = None
    city_county_code: str | None = None
    town_code: str | None = None
    sort_field: str = "stream_code"
    sort_direction: str = "ASC"
    active_only: bool = True


@dataclass(frozen=True)
class CharacteristicDisplayPolicy:
    """운영 allowlist는 호출자가 연구 근거에 따라 명시한다. 기본은 전부 비표시다."""

    allowed_dictionary_ids: frozenset[int] = frozenset()
    show_source_file_name: bool = False
    show_sheet_name: bool = False


@dataclass(frozen=True)
class StreamListRow:
    stream_code: str
    stream_name: str
    province: str | None
    city_county: str | None
    town: str | None
    is_active: bool
    qc_display_state: str


@dataclass(frozen=True)
class StreamListPage:
    total_count: int
    page: int
    page_size: int
    total_pages: int
    rows: tuple[StreamListRow, ...]


@dataclass(frozen=True)
class StreamBasicDetail:
    stream_code: str
    stream_name: str
    province: str | None
    city_county: str | None
    town: str | None
    river_system: str | None
    source_address: str | None = field(repr=False)
    end_address: str | None = field(repr=False)
    source_latitude: float | None = None
    source_longitude: float | None = None
    end_latitude: float | None = None
    end_longitude: float | None = None
    is_active: bool = True
    qc_display_state: str = "ACTIVE_ISSUES_NONE"


@dataclass(frozen=True)
class ProvenanceSummary:
    classification: str
    file_name: str | None = field(default=None, repr=False)
    sheet_name: str | None = field(default=None, repr=False)
    source_row: int | None = None
    source_column: int | None = None
    parent_value_id: int | None = None


@dataclass(frozen=True)
class CharacteristicSummary:
    dictionary_id: int
    standard_name: str
    data_type: str
    current_use_status: str
    current_value: int | float | str | None = field(repr=False)
    unit_display: str | None = None
    qc_display_state: str | None = None
    provenance: ProvenanceSummary | None = field(default=None, repr=False)


@dataclass(frozen=True)
class QCDisplayItem:
    issue_type: str
    severity: str
    review_status: str
    description: str
    is_active: bool


@dataclass(frozen=True)
class ValueHistoryDisplayRow:
    value: int | float | str
    unit_display: str | None
    source_classification: str
    is_active: bool
    is_current_use: bool
    created_at: str
    provenance_summary: str


@dataclass(frozen=True)
class CharacteristicDetailRow:
    dictionary_id: int = field(repr=False)
    internal_name: str
    standard_name: str
    category_key: str
    category_name: str
    current_use_status: str
    current_value: int | float | str | None = field(repr=False)
    unit_display: str | None = None
    qc_display_state: str | None = None
    provenance: ProvenanceSummary | None = field(default=None, repr=False)
    representative_six: bool = False
    focus_nine: bool = False
    qc_items: tuple[QCDisplayItem, ...] = ()
    value_history: tuple[ValueHistoryDisplayRow, ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class StreamResearchDetail:
    basic: StreamBasicDetail
    dictionary_state: str
    characteristics: tuple[CharacteristicDetailRow, ...]


@dataclass(frozen=True)
class StreamReadDetail:
    basic: StreamBasicDetail
    characteristics: tuple[CharacteristicSummary, ...]


@dataclass(frozen=True)
class RegionOption:
    code: str
    name: str
