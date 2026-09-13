"""규칙 기반 QC 입력·판정·결과. 연구값과 규칙 원문은 repr에 노출하지 않는다."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class QualityRule:
    rule_id: int
    rule_code: str = field(repr=False)
    target_type: str = field(repr=False)
    dictionary_id: int | None
    rule_type: str = field(repr=False)
    default_severity: str
    parameters_json: str | None = field(repr=False)
    rule_version: str = field(repr=False)
    is_enabled: bool


@dataclass(frozen=True)
class RequiredImportTarget:
    stream_code: str = field(repr=False)
    dictionary_id: int
    import_id: int


@dataclass(frozen=True)
class QualityControlRequest:
    characteristic_value_ids: tuple[int, ...] = ()
    required_targets: tuple[RequiredImportTarget, ...] = ()


@dataclass(frozen=True)
class QCFinding:
    rule_id: int
    rule_code: str = field(repr=False)
    rule_version_snapshot: str = field(repr=False)
    rule_parameters_snapshot_json: str | None = field(repr=False)
    characteristic_value_id: int | None
    stream_code: str = field(repr=False)
    dictionary_id: int
    import_id: int | None
    import_sheet_id: int | None
    source_row: int | None
    source_column: int | None
    issue_type: str
    severity: str
    message: str


@dataclass(frozen=True)
class QualityIssue:
    """active 목록용 안전한 projection. 원본값·검토 메모·규칙 JSON은 반환하지 않는다."""

    issue_id: int
    rule_id: int | None
    characteristic_value_id: int | None
    stream_code: str | None = field(repr=False)
    dictionary_id: int | None
    import_id: int | None
    issue_type: str = field(repr=False)
    severity: str
    review_status: str
    is_active: bool


@dataclass(frozen=True)
class QualityControlResult:
    findings: tuple[QCFinding, ...]
    created_issue_ids: tuple[int, ...]
    existing_issue_ids: tuple[int, ...]


@dataclass(frozen=True)
class QCSeverityCounts:
    error: int = 0
    warning: int = 0
    info: int = 0

    @property
    def status(self):
        if self.error:
            return "ERROR"
        if self.warning or self.info:
            return "NEEDS_REVIEW"
        return "NORMAL"


@dataclass(frozen=True)
class QCCheckedScope:
    """성공적으로 평가한 rule/대상/출처. Finding이 없어도 재검사 책임 범위를 보존한다."""

    rule_id: int
    characteristic_value_id: int | None
    stream_code: str = field(repr=False)
    dictionary_id: int
    import_id: int | None
    import_sheet_id: int | None
    source_row: int | None
    source_column: int | None
    reference_value_id: int | None = None


@dataclass(frozen=True)
class QualityRecheckResult:
    checked_count: int
    finding_count: int
    kept_issue_ids: tuple[int, ...]
    created_issue_ids: tuple[int, ...]
    deactivated_issue_ids: tuple[int, ...]
    qc_status: str
    completed_at: str
