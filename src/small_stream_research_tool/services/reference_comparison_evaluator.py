"""명시적 typed 값의 순수 비교. 허용오차·문자열 정규화·단위변환을 추측하지 않는다."""

import json
import math
from dataclasses import dataclass, field
from fractions import Fraction

from small_stream_research_tool.models.quality_control_errors import (
    QualityControlError,
    QualityRuleConfigurationError,
)
from small_stream_research_tool.services.quality_rule_evaluator import _object


@dataclass(frozen=True)
class CompiledReferenceRule:
    parameters_snapshot: str | None = field(repr=False)
    data_type: str
    absolute_tolerance: Fraction | None = field(default=None, repr=False)
    relative_tolerance: Fraction | None = field(default=None, repr=False)

    def violated(self, target, reference):
        try:
            if self.data_type == "TEXT":
                if type(target) is not str or type(reference) is not str:
                    raise ValueError()
                return target != reference
            for value in (target, reference):
                if self.data_type == "INTEGER":
                    if type(value) is not int or not -(2**63) <= value < 2**63:
                        raise ValueError()
                elif type(value) is not float or not math.isfinite(value):
                    raise ValueError()
            # 저장된 숫자의 십진 표현을 정확한 유리수로 비교하여 연산 반올림을 피한다.
            target, reference = Fraction(str(target)), Fraction(str(reference))
            difference = abs(target - reference)
            if self.relative_tolerance is not None:
                if reference == 0:
                    raise ValueError()
                return difference > self.relative_tolerance * abs(reference)
            if self.absolute_tolerance is not None:
                return difference > self.absolute_tolerance
            return difference != 0
        except (ValueError, TypeError, OverflowError, ZeroDivisionError):
            raise QualityControlError() from None


def compile_reference_rule(rule, item):
    try:
        if (
            rule.rule_type != "REFERENCE_COMPARE"
            or rule.target_type != "CHARACTERISTIC_VALUE"
            or rule.dictionary_id != item.dictionary_id
            or item.storage_type != "FLEX"
            or item.data_type not in ("INTEGER", "REAL", "TEXT")
            or rule.default_severity not in ("ERROR", "WARNING", "INFO")
            or type(rule.rule_version) is not str
            or not rule.rule_version.strip()
        ):
            raise ValueError()
        rule.rule_version.encode("utf-8")
        params = (
            {}
            if rule.parameters_json is None
            else json.loads(rule.parameters_json, object_pairs_hook=_object)
        )
        if type(params) is not dict or not params.keys() <= {
            "comparison",
            "absolute_tolerance",
            "relative_tolerance",
        }:
            raise ValueError()
        expected = "text" if item.data_type == "TEXT" else "numeric"
        if params.get("comparison", expected) != expected:
            raise ValueError()
        tolerances = params.keys() & {"absolute_tolerance", "relative_tolerance"}
        if len(tolerances) > 1 or (item.data_type == "TEXT" and tolerances):
            raise ValueError()
        for key in tolerances:
            number = params[key]
            if (
                type(number) not in (int, float)
                or (type(number) is float and not math.isfinite(number))
                or number < 0
            ):
                raise ValueError()
        snapshot = (
            None
            if rule.parameters_json is None
            else json.dumps(params, sort_keys=True, separators=(",", ":"), allow_nan=False)
        )
        return CompiledReferenceRule(
            snapshot,
            item.data_type,
            Fraction(str(params["absolute_tolerance"])) if "absolute_tolerance" in params else None,
            Fraction(str(params["relative_tolerance"])) if "relative_tolerance" in params else None,
        )
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise QualityRuleConfigurationError() from None
