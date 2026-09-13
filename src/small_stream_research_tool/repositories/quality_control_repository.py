"""QC 조회·issue 생성/비활성화. transaction은 Service가 소유한다."""

import sqlite3
from dataclasses import asdict

from small_stream_research_tool.models.quality_control import (
    QCCheckedScope,
    QCFinding,
    QCSeverityCounts,
    QualityIssue,
    QualityRule,
)
from small_stream_research_tool.models.quality_control_errors import QualityControlPersistenceError
from small_stream_research_tool.models.reference_comparison import snapshot_reference_id

_RULE_COLUMNS = (
    "rule_id,rule_code,target_type,dictionary_id,rule_type,default_severity,"
    "parameters_json,rule_version,is_enabled"
)
_ISSUE_COLUMNS = (
    "issue_id,rule_id,characteristic_value_id,stream_code,dictionary_id,import_id,"
    "issue_type,severity,review_status,is_active"
)
_IDENTITY = (
    "rule_id",
    "characteristic_value_id",
    "stream_code",
    "dictionary_id",
    "import_id",
    "import_sheet_id",
    "source_row",
    "source_column",
    "issue_type",
    "severity",
    "rule_version_snapshot",
    "rule_parameters_snapshot_json",
)
_SCOPE = (
    "rule_id",
    "characteristic_value_id",
    "stream_code",
    "dictionary_id",
    "import_id",
    "import_sheet_id",
    "source_row",
    "source_column",
)


def _scope_where(scope):
    if type(scope) is not QCCheckedScope:
        raise QualityControlPersistenceError()
    types = (
        ("UNIT_MISMATCH", "UNIT_MISSING")
        if scope.unit_rule_type == "UNIT_MATCH"
        else ("UNIT_CONVERSION_MISSING",)
        if scope.unit_rule_type == "UNIT_CONVERSION_MISSING"
        else ("REFERENCE_VALUE_MISMATCH",)
        if scope.reference_value_id is not None
        else ("REQUIRED_VALUE_MISSING",)
        if scope.characteristic_value_id is None
        else ("NEGATIVE_VALUE", "VALUE_OUT_OF_RANGE")
    )
    where = " AND ".join(name + " IS ?" for name in _SCOPE)
    where += " AND issue_type IN (" + ",".join("?" for _ in types) + ")"
    return where, (*tuple(getattr(scope, name) for name in _SCOPE), *types)


class QualityControlRepository:
    def __init__(self, connection):
        self._connection = connection

    def _execute(self, sql, parameters=(), *, write=False, update=False):
        try:
            if write and not self._connection.in_transaction:
                raise QualityControlPersistenceError()
            cursor = self._connection.execute(sql, parameters)
            try:
                if update:
                    return cursor.rowcount
                return cursor.lastrowid if write else cursor.fetchall()
            finally:
                cursor.close()
        except (sqlite3.Error, OverflowError, UnicodeError):
            raise QualityControlPersistenceError() from None

    def list_enabled_rules(self) -> tuple[QualityRule, ...]:
        return tuple(
            QualityRule(*row)
            for row in self._execute(
                f"SELECT {_RULE_COLUMNS} FROM quality_rule WHERE is_enabled=1 ORDER BY rule_id"
            )
        )

    def get_rule(self, rule_id: int) -> QualityRule | None:
        rows = self._execute(
            f"SELECT {_RULE_COLUMNS} FROM quality_rule WHERE rule_id=?", (rule_id,)
        )
        return QualityRule(*rows[0]) if rows else None

    def list_rules_by_dictionary(self, dictionary_id) -> tuple[QualityRule, ...]:
        return tuple(
            QualityRule(*row)
            for row in self._execute(
                f"SELECT {_RULE_COLUMNS} FROM quality_rule WHERE dictionary_id=? "
                "AND is_enabled=1 ORDER BY rule_id",
                (dictionary_id,),
            )
        )

    def import_value_exists(self, stream_code, dictionary_id, import_id) -> bool:
        return bool(
            self._execute(
                "SELECT 1 FROM characteristic_value WHERE stream_code=? AND dictionary_id=? "
                "AND import_id=? AND source_type='IMPORT' AND is_active=1 LIMIT 1",
                (stream_code, dictionary_id, import_id),
            )
        )

    def find_active_identical(self, finding: QCFinding) -> int | None:
        ids = self.list_active_identical_ids(finding)
        return ids[0] if ids else None

    def list_active_identical_ids(self, finding: QCFinding) -> tuple[int, ...]:
        rows = self._execute(
            "SELECT issue_id FROM data_quality_issue WHERE is_active=1 AND "
            + " AND ".join(name + " IS ?" for name in _IDENTITY)
            + " ORDER BY issue_id",
            tuple(getattr(finding, name) for name in _IDENTITY),
        )
        return tuple(row[0] for row in rows)

    def list_active_ids_for_scope(self, scope: QCCheckedScope) -> tuple[int, ...]:
        where, parameters = _scope_where(scope)
        return tuple(
            row[0]
            for row in self._execute(
                "SELECT issue_id,rule_parameters_snapshot_json FROM data_quality_issue "
                "WHERE is_active=1 AND " + where + " ORDER BY issue_id",
                parameters,
            )
            if scope.reference_value_id is None
            or snapshot_reference_id(row[1]) == scope.reference_value_id
        )

    def deactivate_issue(self, issue_id: int, scope: QCCheckedScope) -> None:
        """검증된 ID와 전체 scope가 모두 일치할 때 is_active만 1→0으로 변경한다."""
        where, parameters = _scope_where(scope)
        if scope.reference_value_id is not None:
            if issue_id not in self.list_active_ids_for_scope(scope):
                raise QualityControlPersistenceError()
        count = self._execute(
            "UPDATE data_quality_issue SET is_active=0 WHERE issue_id=? AND is_active=1 AND "
            + where,
            (issue_id, *parameters),
            write=True,
            update=True,
        )
        if count != 1:
            raise QualityControlPersistenceError()

    def create_issue(self, finding: QCFinding, *, timestamp: str) -> int:
        if type(finding) is not QCFinding:
            raise QualityControlPersistenceError()
        values = asdict(finding)
        values.pop("rule_code")  # 실제 schema에 컬럼이 없으며 rule_id로 연결한다.
        values["created_at"] = timestamp
        return self._execute(
            "INSERT INTO data_quality_issue ("
            + ",".join(values)
            + ") VALUES ("
            + ",".join("?" for _ in values)
            + ")",
            tuple(values.values()),
            write=True,
        )

    def list_active_issues(self, stream_code: str) -> tuple[QualityIssue, ...]:
        return tuple(
            QualityIssue(*row)
            for row in self._execute(
                f"SELECT {_ISSUE_COLUMNS} FROM data_quality_issue "
                "WHERE stream_code=? AND is_active=1 ORDER BY issue_id",
                (stream_code,),
            )
        )

    def count_active_issues(self, stream_code: str) -> int:
        return self._execute(
            "SELECT count(*) FROM data_quality_issue WHERE stream_code=? AND is_active=1",
            (stream_code,),
        )[0][0]

    def active_severity_counts(self, stream_code: str) -> QCSeverityCounts:
        counts = dict(
            self._execute(
                "SELECT severity,count(*) FROM data_quality_issue "
                "WHERE stream_code=? AND is_active=1 GROUP BY severity",
                (stream_code,),
            )
        )
        return QCSeverityCounts(
            counts.get("ERROR", 0), counts.get("WARNING", 0), counts.get("INFO", 0)
        )
