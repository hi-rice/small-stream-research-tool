"""소하천 관리코드의 원본·후보·검증 상태를 분리한 불변 결과 모델."""

from dataclasses import dataclass
from enum import StrEnum


class CodeStatus(StrEnum):
    VALID = "VALID"
    MISSING = "MISSING"
    INVALID_FORMAT = "INVALID_FORMAT"
    INVALID_LENGTH = "INVALID_LENGTH"
    AMBIGUOUS = "AMBIGUOUS"


class ComparisonStatus(StrEnum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    NOT_COMPARABLE = "NOT_COMPARABLE"


@dataclass(frozen=True)
class StreamCodeComponentResult:
    name: str
    raw_value: object
    number_format: str | None
    normalized_value: str | None
    expected_width: int
    status: CodeStatus
    code: str
    message: str
    normalization_steps: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return self.status == CodeStatus.VALID


@dataclass(frozen=True)
class StreamCodeIssue:
    field: str
    code: str
    message: str


@dataclass(frozen=True)
class StreamCodeValidationResult:
    source: StreamCodeComponentResult
    components: tuple[StreamCodeComponentResult, ...]
    generated_code: str | None
    comparison_status: ComparisonStatus
    issues: tuple[StreamCodeIssue, ...]

    @property
    def source_code(self) -> object:
        return self.source.raw_value

    @property
    def normalized_source_code(self) -> str | None:
        return self.source.normalized_value

    @property
    def source_valid(self) -> bool:
        return self.source.valid

    @property
    def generated_valid(self) -> bool:
        return self.generated_code is not None
