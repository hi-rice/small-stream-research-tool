"""Preview의 원본 매핑으로 저장 후보만 생성한다. DB 읽기는 사전 Service에 한정한다."""

from collections import Counter
from collections.abc import Iterable, Iterator

from small_stream_research_tool.models.import_preparation import (
    CORE_COORDINATE_LIMITS,
    CORE_TEXT_FIELDS,
    TYPED_FIELDS,
    ImportFieldPolicy,
    ImportPreparationIssue,
    ImportPreparationResult,
    ImportPreparationSummary,
    PreparationStatus,
    PreparedCharacteristicValue,
    PreparedImportRow,
    PreparedStreamData,
    RowAction,
)
from small_stream_research_tool.models.import_preparation_errors import (
    InvalidPreparationArgumentError,
    ValueNormalizationError,
)
from small_stream_research_tool.models.import_preview import ImportPreviewRow, PreviewStatus
from small_stream_research_tool.models.stream_code import CodeStatus, ComparisonStatus
from small_stream_research_tool.services.dictionary_service import DictionaryService
from small_stream_research_tool.services.stream_code_service import (
    COMPONENT_WIDTHS,
    validate_stream_code_cells,
)
from small_stream_research_tool.services.value_normalization_service import (
    normalize_cell,
    original_value_text,
)

_CODE_NAMES = frozenset((*COMPONENT_WIDTHS, "stream_code"))
_CORE_NAMES = _CODE_NAMES | {"stream_name"} | CORE_TEXT_FIELDS | CORE_COORDINATE_LIMITS.keys()
_SYSTEM_NAMES = frozenset(("created_at", "updated_at", "is_active"))


def preparation_summary(rows: Iterable[PreparedImportRow]) -> ImportPreparationSummary:
    """action/value 수는 READY 행만 집계한다. BLOCKED의 부분 후보는 제외한다."""
    rows = tuple(rows)
    states = Counter(row.status for row in rows)
    ready = tuple(row for row in rows if row.status == PreparationStatus.READY)
    actions = Counter(row.row_action for row in ready)
    return ImportPreparationSummary(
        len(rows),
        states[PreparationStatus.READY],
        states[PreparationStatus.BLOCKED],
        states[PreparationStatus.EXCLUDED],
        actions[RowAction.CREATE_STREAM],
        actions[RowAction.USE_EXISTING_STREAM],
        sum(len(row.prepared_values) for row in ready),
    )


class ImportPreparationService:
    def __init__(self, dictionary_service: DictionaryService):
        self._dictionary = dictionary_service

    def prepare_row(
        self, row: ImportPreviewRow, *, field_policy: ImportFieldPolicy | None = None
    ) -> PreparedImportRow:
        policy = ImportFieldPolicy() if field_policy is None else field_policy
        if type(policy) is not ImportFieldPolicy:
            raise InvalidPreparationArgumentError("ImportFieldPolicy가 필요합니다.")
        if (
            type(row) is not ImportPreviewRow
            or type(row.source_row) is not int
            or not 1 <= row.source_row <= 1048576
            or type(row.status) is not PreviewStatus
        ):
            raise InvalidPreparationArgumentError("1-based 출처의 Preview 행이 필요합니다.")
        issues = []

        def issue(code, message, mapped=None, *, blocking=True):
            issues.append(
                ImportPreparationIssue(
                    code,
                    message,
                    blocking,
                    row.source_row,
                    mapped.source_column_index if mapped else None,
                    mapped.dictionary_id if mapped else None,
                )
            )

        def stopped(status):
            return PreparedImportRow(
                row.source_row, None, None, None, status, (), tuple(issues), row.status
            )

        if row.status == PreviewStatus.EXCLUDED or row.excluded:
            return stopped(PreparationStatus.EXCLUDED)
        if row.status == PreviewStatus.NEEDS_REVIEW or any(i.blocking for i in row.issues):
            issue("PREVIEW_BLOCKED", "Preview의 검토 필요 또는 차단 사유를 먼저 해결해야 합니다.")
            return stopped(PreparationStatus.BLOCKED)
        if (
            policy.excluded_internal_names
            & _CODE_NAMES
            & {mapped.internal_name for mapped in row.mapped_values}
        ):
            issue("IDENTITY_EXCLUDED", "필수 식별코드가 Import 정책에서 제외되었습니다.")
            return stopped(PreparationStatus.BLOCKED)

        selected = []
        for mapped in row.mapped_values:
            # 정책을 먼저 적용하여 제외 원본은 변환·original_value 생성 경로에 들어가지 않는다.
            if mapped.internal_name in policy.excluded_internal_names:
                issue(
                    "FIELD_EXCLUDED",
                    "Import 정책에 따라 항목을 제외했습니다.",
                    mapped,
                    blocking=False,
                )
                continue
            if (
                type(mapped.source_column_index) is not int
                or not 1 <= mapped.source_column_index <= 16384
                or mapped.cell.column_index != mapped.source_column_index
                or mapped.cell.row_index != row.source_row
            ):
                issue("SOURCE_MISMATCH", "원본 행/열 위치가 일치하지 않습니다.", mapped)
                continue
            item = self._dictionary.get_item(mapped.dictionary_id)
            if item is not None and item.internal_name in policy.excluded_internal_names:
                issue(
                    "FIELD_EXCLUDED",
                    "Import 정책에 따라 항목을 제외했습니다.",
                    mapped,
                    blocking=False,
                )
                continue
            if not self._usable(item) or item.internal_name != mapped.internal_name:
                issue("DICTIONARY_UNAVAILABLE", "사전 또는 매핑을 다시 확인해야 합니다.", mapped)
                continue
            selected.append((mapped, item))
        names = Counter(item.internal_name for _, item in selected)
        columns = Counter(mapped.source_column_index for mapped, _ in selected)
        if any(count > 1 for count in (*names.values(), *columns.values())):
            issue("DUPLICATE_MAPPING", "중복된 항목 또는 원본 열을 자동 선택할 수 없습니다.")
            return stopped(PreparationStatus.BLOCKED)

        code_cells = {
            item.internal_name: mapped.cell
            for mapped, item in selected
            if item.internal_name in _CODE_NAMES
        }
        validation = validate_stream_code_cells(code_cells)
        invalid = any(
            part.status not in (CodeStatus.VALID, CodeStatus.MISSING)
            for part in (validation.source, *validation.components)
        )
        effective_code = validation.normalized_source_code or validation.generated_code
        if (
            invalid
            or not effective_code
            or effective_code != row.stream_code
            or validation.comparison_status == ComparisonStatus.MISMATCH
        ):
            issue("IDENTITY_NOT_READY", "관리코드 또는 Preview와의 일치를 확인해야 합니다.")
        new = row.status == PreviewStatus.NEW_STREAM
        if row.existing_stream_found is not (not new):
            issue("PREVIEW_LOOKUP_MISMATCH", "Preview의 하천 존재 여부를 다시 확인해야 합니다.")
        values, core_fields = [], {}
        for mapped, item in selected:
            name = item.internal_name
            if name in _CODE_NAMES:
                if item.data_type != "TEXT":
                    issue("CORE_TYPE_MISMATCH", "관리코드의 사전 자료형은 TEXT여야 합니다.", mapped)
                continue
            if name in _SYSTEM_NAMES:
                issue(
                    "SYSTEM_FIELD_NOT_IMPORTABLE",
                    "시스템 필드는 연구자료에서 가져올 수 없습니다.",
                    mapped,
                )
                continue
            if name in _CORE_NAMES and not new:
                continue  # 기존 core data는 수정 후보도 만들지 않는다.
            expected = "REAL" if name in CORE_COORDINATE_LIMITS else "TEXT"
            if name in _CORE_NAMES and item.data_type != expected:
                issue("CORE_TYPE_MISMATCH", "core 필드와 사전 자료형이 일치하지 않습니다.", mapped)
                continue
            try:
                normalized = normalize_cell(mapped.cell, item.data_type)
                if normalized is None:
                    if item.required or not item.nullable:
                        issue(
                            "MISSING_VALUE",
                            "필수 또는 결측 불허 항목에 값이 없습니다.",
                            mapped,
                            blocking=False,
                        )
                    continue
                if name in _CORE_NAMES:
                    if (
                        name in CORE_COORDINATE_LIMITS
                        and abs(normalized) > CORE_COORDINATE_LIMITS[name]
                    ):
                        issue(
                            "CORE_COORDINATE_RANGE", "좌표가 DB의 형식 범위를 벗어납니다.", mapped
                        )
                    else:
                        core_fields[name] = normalized
                else:
                    values.append(
                        PreparedCharacteristicValue(
                            item.dictionary_id,
                            item.data_type,
                            mapped.source_column_index,
                            row.source_row,
                            **{TYPED_FIELDS[item.data_type]: normalized},
                            original_value=original_value_text(mapped.cell),
                            unit_id=item.unit_id,
                        )
                    )
            except ValueNormalizationError as error:
                issue(error.code, str(error), mapped)

        core_data = None
        if new:
            if not core_fields.get("stream_name"):
                issue("STREAM_NAME_REQUIRED", "신규 하천에는 원본 하천명이 필요합니다.")
            if not validation.generated_valid or validation.generated_code != effective_code:
                issue("COMPONENTS_REQUIRED", "신규 하천에는 일치하는 네 구성코드가 필요합니다.")
            if not any(i.blocking for i in issues):
                core_data = PreparedStreamData(
                    effective_code,
                    *(part.normalized_value for part in validation.components),
                    core_fields["stream_name"],
                    tuple(
                        (name, value)
                        for name, value in core_fields.items()
                        if name != "stream_name"
                    ),
                )
        elif not values:
            issue("NO_CHARACTERISTIC_VALUES", "기존 하천에 새로 저장할 특성값이 없습니다.")
        blocked = any(i.blocking for i in issues)
        return PreparedImportRow(
            row.source_row,
            effective_code,
            core_fields.get("stream_name"),
            None
            if blocked
            else (RowAction.CREATE_STREAM if new else RowAction.USE_EXISTING_STREAM),
            PreparationStatus.BLOCKED if blocked else PreparationStatus.READY,
            tuple(values),
            tuple(issues),
            row.status,
            core_data,
        )

    def _usable(self, item):
        if item is None or not item.is_active or item.deprecated_version_id is not None:
            return False
        category = self._dictionary.get_category(item.category_id)
        unit = self._dictionary.get_unit(item.unit_id) if item.unit_id is not None else None
        return (
            item.data_type in TYPED_FIELDS
            and category is not None
            and category.is_active
            and (item.unit_id is None or (unit is not None and unit.is_active))
        )

    def iter_prepared_rows(self, rows, *, field_policy=None) -> Iterator[PreparedImportRow]:
        seen = set()
        for row in rows:
            prepared = self.prepare_row(row, field_policy=field_policy)
            if prepared.source_row in seen:
                raise InvalidPreparationArgumentError("원본 행 번호가 중복됩니다.")
            seen.add(prepared.source_row)
            yield prepared

    def prepare(self, rows, *, field_policy=None) -> ImportPreparationResult:
        prepared = tuple(self.iter_prepared_rows(rows, field_policy=field_policy))
        return ImportPreparationResult(prepared, preparation_summary(prepared))
