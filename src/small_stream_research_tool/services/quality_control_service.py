"""명시적 값/Import 필수항목 QC. 평가와 issue 저장을 분리하고 자료 자체는 수정하지 않는다."""

import math

from small_stream_research_tool.database.connection import read_transaction, transaction
from small_stream_research_tool.models.import_preparation import ImportFieldPolicy
from small_stream_research_tool.models.quality_control import (
    QCCheckedScope,
    QCFinding,
    QCSeverityCounts,
    QualityControlRequest,
    QualityControlResult,
    QualityRecheckResult,
    RequiredImportTarget,
)
from small_stream_research_tool.models.quality_control_errors import (
    QualityControlError,
    QualityControlPersistenceError,
    QualityRuleConfigurationError,
)
from small_stream_research_tool.models.reference_comparison import comparison_snapshot
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.repositories.import_persistence_repository import (
    CharacteristicValueRepository,
    ImportColumnMappingRepository,
    ImportHistoryRepository,
    ImportSheetRepository,
    SmallStreamRepository,
)
from small_stream_research_tool.repositories.quality_control_repository import (
    QualityControlRepository,
)
from small_stream_research_tool.services.dictionary_service import DictionaryService
from small_stream_research_tool.services.quality_rule_evaluator import compile_rule
from small_stream_research_tool.services.reference_comparison_evaluator import (
    compile_reference_rule,
)
from small_stream_research_tool.utils.timestamps import utc_now_text

_MESSAGES = {
    "REQUIRED": ("REQUIRED_VALUE_MISSING", "Required value is missing."),
    "NON_NEGATIVE": ("NEGATIVE_VALUE", "Value must not be negative."),
    "RANGE": ("VALUE_OUT_OF_RANGE", "Value is outside the configured range."),
}


def _require(condition):
    if not condition:
        raise QualityControlError()


def _id(value):
    return type(value) is int and 1 <= value < 2**63


class QualityControlService:
    def __init__(self, connection):
        self._connection = connection
        self._repository = QualityControlRepository(connection)
        self._dictionary = DictionaryService(DictionaryRepository(connection))
        self._values = CharacteristicValueRepository(connection)
        self._streams = SmallStreamRepository(connection)
        self._histories = ImportHistoryRepository(connection)
        self._sheets = ImportSheetRepository(connection)
        self._mappings = ImportColumnMappingRepository(connection)

    def evaluate(
        self, request: QualityControlRequest, *, field_policy=None
    ) -> tuple[QCFinding, ...]:
        try:
            with read_transaction(self._connection):
                return self._evaluate(request, field_policy)
        except QualityControlError:
            raise
        except Exception:
            raise QualityControlError() from None

    def run(self, request: QualityControlRequest, *, field_policy=None) -> QualityControlResult:
        try:
            with transaction(self._connection):
                findings = self._evaluate(request, field_policy)
                created, existing = [], []
                timestamp = utc_now_text()
                for finding in findings:
                    issue_id = self._repository.find_active_identical(finding)
                    if issue_id is not None:
                        existing.append(issue_id)
                    else:
                        created.append(self._repository.create_issue(finding, timestamp=timestamp))
                result = QualityControlResult(findings, tuple(created), tuple(existing))
            return result
        except QualityControlError:
            raise
        except Exception:
            raise QualityControlPersistenceError() from None

    def _item(self, dictionary_id):
        _require(_id(dictionary_id))
        item = self._dictionary.get_item(dictionary_id)
        _require(item is not None and item.is_active and item.deprecated_version_id is None)
        return item

    def _evaluate(self, request, policy, *, checked_scopes=None, rule_ids=None):
        _require(type(request) is QualityControlRequest and type(policy) is ImportFieldPolicy)
        _require(
            type(request.characteristic_value_ids) is tuple
            and type(request.required_targets) is tuple
        )
        _require(bool(request.characteristic_value_ids or request.required_targets))
        _require(all(_id(i) for i in request.characteristic_value_ids))
        _require(
            len(set(request.characteristic_value_ids)) == len(request.characteristic_value_ids)
        )
        _require(all(type(t) is RequiredImportTarget for t in request.required_targets))
        _require(len(set(request.required_targets)) == len(request.required_targets))
        rules = {}
        # 활성 규칙 정의의 오류는 자료 오류 issue로 바꾸지 않고 실행 자체를 거부한다.
        if rule_ids is None:
            selected_rules = self._repository.list_enabled_rules()
        else:
            _require(type(rule_ids) is tuple and bool(rule_ids))
            _require(all(_id(i) for i in rule_ids) and len(set(rule_ids)) == len(rule_ids))
            selected_rules = tuple(self._repository.get_rule(i) for i in rule_ids)
            _require(all(r is not None for r in selected_rules))
        for rule in selected_rules:
            if not rule.is_enabled:
                continue
            try:
                item = self._item(rule.dictionary_id)
            except QualityControlError:
                raise QualityRuleConfigurationError() from None
            if item.internal_name in policy.excluded_internal_names:
                continue
            compiled = compile_rule(rule, item)
            rules.setdefault(item.dictionary_id, []).append(compiled)
        findings = []
        for value_id in request.characteristic_value_ids:
            value = self._values.get_by_id(value_id)
            _require(value is not None and value.is_active)
            item = self._item(value.dictionary_id)
            if item.internal_name in policy.excluded_internal_names:
                continue
            applicable = [
                r for r in rules.get(item.dictionary_id, ()) if r.rule.rule_type != "REQUIRED"
            ]
            if not applicable:
                continue
            column = self._provenance(value)
            typed = (value.value_number, value.value_integer, value.value_text, value.value_date)
            _require(sum(v is not None for v in typed) == 1)
            number = value.value_number if item.data_type == "REAL" else value.value_integer
            _require(
                (item.data_type == "REAL" and type(number) is float and math.isfinite(number))
                or (
                    item.data_type == "INTEGER"
                    and type(number) is int
                    and -(2**63) <= number < 2**63
                )
            )
            for compiled in applicable:
                if checked_scopes is not None:
                    checked_scopes.append(
                        QCCheckedScope(
                            compiled.rule.rule_id,
                            value.characteristic_value_id,
                            value.stream_code,
                            item.dictionary_id,
                            value.import_id,
                            value.import_sheet_id,
                            value.source_row,
                            column,
                        )
                    )
                if compiled.violated(number=number):
                    findings.append(
                        self._finding(
                            compiled,
                            value.stream_code,
                            item.dictionary_id,
                            value.characteristic_value_id,
                            value.import_id,
                            value.import_sheet_id,
                            value.source_row,
                            column,
                        )
                    )
        for target in request.required_targets:
            _require(_id(target.import_id))
            stream = self._streams.get_by_stream_code(target.stream_code)
            _require(stream is not None and stream.is_active)
            history = self._histories.get_by_id(target.import_id)
            _require(history is not None and history.status == "SUCCESS")
            item = self._item(target.dictionary_id)
            if item.internal_name in policy.excluded_internal_names:
                continue
            present = self._repository.import_value_exists(
                target.stream_code, target.dictionary_id, target.import_id
            )
            for compiled in rules.get(item.dictionary_id, ()):
                if compiled.rule.rule_type == "REQUIRED" and checked_scopes is not None:
                    checked_scopes.append(
                        QCCheckedScope(
                            compiled.rule.rule_id,
                            None,
                            target.stream_code,
                            item.dictionary_id,
                            target.import_id,
                            None,
                            None,
                            None,
                        )
                    )
                if compiled.rule.rule_type == "REQUIRED" and compiled.violated(present=present):
                    findings.append(
                        self._finding(
                            compiled,
                            target.stream_code,
                            item.dictionary_id,
                            None,
                            target.import_id,
                            None,
                            None,
                            None,
                        )
                    )
        return tuple(findings)

    def recheck(
        self,
        request: QualityControlRequest,
        *,
        field_policy=None,
        rule_ids: tuple[int, ...] | None = None,
    ) -> QualityRecheckResult:
        """실제 평가한 scope/rule만 reconcile한다. run()의 생성 전용 계약은 유지한다."""
        try:
            with transaction(self._connection):
                scopes = []
                findings = self._evaluate(
                    request, field_policy, checked_scopes=scopes, rule_ids=rule_ids
                )
                # 요청한 stream들의 현재 active 집계: 미검사/disabled 규칙의 기존 issue도 포함한다.
                streams = {t.stream_code for t in request.required_targets}
                streams.update(
                    self._values.get_by_id(i).stream_code for i in request.characteristic_value_ids
                )
                result = self._reconcile(scopes, findings, streams)
            return result
        except QualityControlError:
            raise
        except Exception:
            raise QualityControlPersistenceError() from None

    def compare_reference(self, target_value_id, reference_value_id, rule_id, *, field_policy=None):
        """명시한 한 쌍만 비교하고 reconcile한다. 다른 reference의 issue는 보존한다."""
        try:
            with transaction(self._connection):
                _require(type(field_policy) is ImportFieldPolicy)
                _require(all(_id(i) for i in (target_value_id, reference_value_id, rule_id)))
                target = self._values.get_by_id(target_value_id)
                reference = self._values.get_by_id(reference_value_id)
                _require(target is not None and reference is not None)
                _require(target.is_active and reference.is_active)
                _require(target.stream_code == reference.stream_code)
                _require(target.dictionary_id == reference.dictionary_id)
                item = self._item(target.dictionary_id)
                _require(item.internal_name not in field_policy.excluded_internal_names)
                rule = self._repository.get_rule(rule_id)
                _require(rule is not None)
                compiled = compile_reference_rule(rule, item)
                if not rule.is_enabled:
                    result = self._reconcile((), (), {target.stream_code})
                else:
                    _require(target.unit_id == reference.unit_id)
                    column = self._provenance(target)
                    self._provenance(reference)

                    def typed(value):
                        values = (
                            value.value_integer,
                            value.value_number,
                            value.value_text,
                            value.value_date,
                        )
                        _require(sum(v is not None for v in values) == 1)
                        return {
                            "INTEGER": value.value_integer,
                            "REAL": value.value_number,
                            "TEXT": value.value_text,
                        }[item.data_type]

                    mismatch = compiled.violated(typed(target), typed(reference))
                    scope = QCCheckedScope(
                        rule_id,
                        target_value_id,
                        target.stream_code,
                        target.dictionary_id,
                        target.import_id,
                        target.import_sheet_id,
                        target.source_row,
                        column,
                        reference_value_id,
                    )
                    finding = QCFinding(
                        rule_id,
                        rule.rule_code,
                        rule.rule_version,
                        comparison_snapshot(compiled.parameters_snapshot, reference_value_id),
                        target_value_id,
                        target.stream_code,
                        target.dictionary_id,
                        target.import_id,
                        target.import_sheet_id,
                        target.source_row,
                        column,
                        "REFERENCE_VALUE_MISMATCH",
                        rule.default_severity,
                        "Value differs from the explicitly selected reference.",
                    )
                    result = self._reconcile(
                        (scope,), (finding,) if mismatch else (), {target.stream_code}
                    )
            return result
        except QualityControlError:
            raise
        except Exception:
            raise QualityControlPersistenceError() from None

    def _reconcile(self, scopes, findings, streams):
        """호출자가 소유한 transaction 안에서만 공통 reconciliation을 수행한다."""
        old_scopes = {}
        for scope in scopes:
            for issue_id in self._repository.list_active_ids_for_scope(scope):
                old_scopes[issue_id] = scope
        kept, pending = set(), []
        for finding in findings:
            matches = self._repository.list_active_identical_ids(finding)
            if matches:
                _require(set(matches) <= old_scopes.keys())
                kept.update(matches)
            else:
                pending.append(finding)
        deactivated = tuple(sorted(old_scopes.keys() - kept))
        timestamp = utc_now_text()
        created = tuple(self._repository.create_issue(f, timestamp=timestamp) for f in pending)
        for issue_id in deactivated:
            self._repository.deactivate_issue(issue_id, old_scopes[issue_id])
        counts = [self._repository.active_severity_counts(s) for s in sorted(streams)]
        status = QCSeverityCounts(
            sum(c.error for c in counts),
            sum(c.warning for c in counts),
            sum(c.info for c in counts),
        ).status
        return QualityRecheckResult(
            len(scopes),
            len(findings),
            tuple(sorted(kept)),
            created,
            deactivated,
            status,
            utc_now_text(),
        )

    def _provenance(self, value):
        if value.import_id is not None:
            _require(self._histories.get_by_id(value.import_id) is not None)
        if value.import_sheet_id is not None:
            sheet = self._sheets.get_by_id(value.import_sheet_id)
            _require(sheet is not None and sheet.import_id == value.import_id)
        if value.source_row is not None:
            _require(type(value.source_row) is int and 1 <= value.source_row <= 1048576)
        if value.mapping_id is None:
            return None
        mapping = self._mappings.get_by_id(value.mapping_id)
        _require(mapping is not None and mapping.import_sheet_id == value.import_sheet_id)
        _require(mapping.dictionary_id == value.dictionary_id)
        _require(
            type(mapping.source_column_index) is int and 1 <= mapping.source_column_index <= 16384
        )
        return mapping.source_column_index

    @staticmethod
    def _finding(compiled, stream, dictionary_id, value_id, import_id, sheet_id, row, column):
        rule = compiled.rule
        issue_type, message = _MESSAGES[rule.rule_type]
        return QCFinding(
            rule.rule_id,
            rule.rule_code,
            rule.rule_version,
            compiled.parameters_snapshot,
            value_id,
            stream,
            dictionary_id,
            import_id,
            sheet_id,
            row,
            column,
            issue_type,
            rule.default_severity,
            message,
        )
