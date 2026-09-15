"""보정 생성 요청/결과. 연구값은 repr에서 제외한다."""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class UnitInheritance(Enum):
    SOURCE = "SOURCE"


@dataclass(frozen=True)
class CorrectionRequest:
    source_value_id: int
    actor_user_id: int
    corrected_value: int | float | str | date | datetime = field(repr=False)
    reason_code: str
    corrected_unit_id: int | None | UnitInheritance = UnitInheritance.SOURCE


@dataclass(frozen=True)
class CorrectionCreationResult:
    correction_value_id: int
    source_value_id: int
    stream_code: str = field(repr=False)
    dictionary_id: int
    actor_user_id: int
    history_id: int
    created_at: str
