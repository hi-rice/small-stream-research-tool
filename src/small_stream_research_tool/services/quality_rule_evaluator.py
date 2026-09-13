"""SQL·원본 parsing 없는 순수 규칙 검증/평가. 연구 항목명이나 임계값 seed는 없다."""

import json
import math
from dataclasses import dataclass, field

from small_stream_research_tool.models.quality_control import QualityRule
from small_stream_research_tool.models.quality_control_errors import QualityRuleConfigurationError


@dataclass(frozen=True)
class CompiledQualityRule:
    rule: QualityRule = field(repr=False)
    parameters_snapshot: str | None = field(repr=False)
    minimum: int | float | None = None
    maximum: int | float | None = None
    include_min: bool = True
    include_max: bool = True

    def violated(self, *, number=None, present=None):
        if self.rule.rule_type == "REQUIRED":
            return present is False
        if self.rule.rule_type == "NON_NEGATIVE":
            return number < 0
        return (
            self.minimum is not None
            and (number < self.minimum or (not self.include_min and number == self.minimum))
        ) or (
            self.maximum is not None
            and (number > self.maximum or (not self.include_max and number == self.maximum))
        )


def _number(value):
    return type(value) is int or (type(value) is float and math.isfinite(value))


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def compile_rule(rule, item) -> CompiledQualityRule:
    try:
        if rule.dictionary_id is None or rule.dictionary_id != item.dictionary_id:
            raise ValueError()
        if item.storage_type != "FLEX":
            raise ValueError()
        if rule.default_severity not in ("ERROR", "WARNING", "INFO"):
            raise ValueError()
        if not isinstance(rule.rule_version, str) or not rule.rule_version.strip():
            raise ValueError()
        rule.rule_version.encode("utf-8")
        params = (
            {}
            if rule.parameters_json is None
            else json.loads(rule.parameters_json, object_pairs_hook=_object)
        )
        if type(params) is not dict:
            raise ValueError()
        if rule.rule_type == "REQUIRED":
            if rule.target_type != "STREAM_DICTIONARY" or not item.required or params:
                raise ValueError()
        elif rule.rule_type in ("NON_NEGATIVE", "RANGE"):
            if rule.target_type != "CHARACTERISTIC_VALUE" or item.data_type not in (
                "REAL",
                "INTEGER",
            ):
                raise ValueError()
            if rule.rule_type == "NON_NEGATIVE":
                if params:
                    raise ValueError()
            else:
                if not params.keys() <= {
                    "min",
                    "max",
                    "include_min",
                    "include_max",
                } or not params.keys() & {"min", "max"}:
                    raise ValueError()
                for key in ("min", "max"):
                    if key in params and not _number(params[key]):
                        raise ValueError()
                for flag, bound in (("include_min", "min"), ("include_max", "max")):
                    if flag in params and (type(params[flag]) is not bool or bound not in params):
                        raise ValueError()
                if "min" in params and "max" in params and params["min"] > params["max"]:
                    raise ValueError()
        else:
            raise ValueError()
        snapshot = (
            None
            if rule.parameters_json is None
            else json.dumps(params, sort_keys=True, separators=(",", ":"), allow_nan=False)
        )
        return CompiledQualityRule(
            rule,
            snapshot,
            params.get("min"),
            params.get("max"),
            params.get("include_min", True),
            params.get("include_max", True),
        )
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise QualityRuleConfigurationError() from None
