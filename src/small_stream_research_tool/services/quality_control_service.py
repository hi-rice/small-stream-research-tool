"""명시적 값/Import 필수항목 QC. 평가와 issue 저장을 분리하고 자료 자체는 수정하지 않는다."""

import math

from small_stream_research_tool.database.connection import read_transaction, transaction
from small_stream_research_tool.models.import_preparation import ImportFieldPolicy
from small_stream_research_tool.models.quality_control import (
    QCFinding,
    QualityControlRequest,
    QualityControlResult,
    RequiredImportTarget,
)
from small_stream_research_tool.models.quality_control_errors import (
    QualityControlError,
    QualityControlPersistenceError,
    QualityRuleConfigurationError,
)
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

    def _evaluate(self, request, policy):
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
        for rule in self._repository.list_enabled_rules():
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
