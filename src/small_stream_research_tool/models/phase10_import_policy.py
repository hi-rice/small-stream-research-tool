"""Import 화면의 deny-by-default 표시·저장 정책."""

from dataclasses import dataclass, field

from small_stream_research_tool.models.import_preparation import ImportFieldPolicy
from small_stream_research_tool.models.import_preview import PreviewFieldPolicy


@dataclass(frozen=True)
class Phase10ImportPolicies:
    preview: PreviewFieldPolicy = field(repr=False)
    import_fields: ImportFieldPolicy = field(repr=False)
    approved_internal_names: frozenset[str] = field(repr=False)


@dataclass(frozen=True)
class UnitConfirmation:
    """확정 단위의 명시적 사용자 판단. 단위 없는 항목은 NOT_APPLICABLE."""

    dictionary_id: int = field(repr=False)
    status: str
    source_unit: str | None = field(default=None, repr=False)


UNIT_CONFIRMED = "CONFIRMED"
UNIT_NEEDS_REVIEW = "NEEDS_REVIEW"
UNIT_NOT_APPLICABLE = "NOT_APPLICABLE"
