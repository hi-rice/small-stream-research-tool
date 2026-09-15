"""유지관리 결과는 값 ID와 파생 캐시 변경만 노출한다."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ValueLifecycleResult:
    changed: bool
    value_id: int
    stream_code: str = field(repr=False)
    dictionary_id: int
    current_use_released: bool
    history_id: int | None
    completed_at: str


@dataclass(frozen=True)
class CacheRebuildResult:
    changed_pairs: tuple[tuple[str, int], ...] = field(repr=False)
    history_ids: tuple[int, ...] = ()
    completed_at: str = ""
