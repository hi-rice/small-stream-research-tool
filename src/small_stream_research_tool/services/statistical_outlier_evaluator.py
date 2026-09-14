"""결정적인 단변량 IQR 후보 판정. 연구 기본 임계값·자동 제외는 없다."""

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
class StatisticalPolicy:
    parameters_snapshot: str = field(repr=False)
    multiplier: Fraction = field(repr=False)
    minimum_sample_size: int


@dataclass(frozen=True)
class IQRBounds:
    q1: Fraction = field(repr=False)
    q3: Fraction = field(repr=False)
    lower: Fraction = field(repr=False)
    upper: Fraction = field(repr=False)

    def is_candidate(self, number):
        return number < self.lower or number > self.upper


def compile_statistical_rule(rule, item):
    try:
        if (
            rule.rule_type != "STATISTICAL_OUTLIER"
            or rule.default_severity != "INFO"
            or rule.target_type != "CHARACTERISTIC_VALUE"
            or rule.dictionary_id != item.dictionary_id
            or item.storage_type != "FLEX"
            or item.data_type not in ("INTEGER", "REAL")
            or type(rule.rule_version) is not str
            or not rule.rule_version.strip()
        ):
            raise ValueError()
        rule.rule_version.encode("utf-8")
        params = json.loads(rule.parameters_json, object_pairs_hook=_object)
        if (
            type(params) is not dict
            or params.get("method") != "IQR"
            or not {"method", "multiplier"} <= params.keys()
            or not params.keys() <= {"method", "multiplier", "minimum_sample_size"}
        ):
            raise ValueError()
        multiplier = params["multiplier"]
        if (
            type(multiplier) not in (int, float)
            or (type(multiplier) is float and not math.isfinite(multiplier))
            or multiplier < 0
        ):
            raise ValueError()
        minimum = params.get("minimum_sample_size", 1)
        if type(minimum) is not int or minimum < 1:
            raise ValueError()
        return StatisticalPolicy(
            json.dumps(params, sort_keys=True, separators=(",", ":"), allow_nan=False),
            Fraction(str(multiplier)),
            minimum,
        )
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise QualityRuleConfigurationError() from None


def numeric_value(value, data_type):
    typed = (value.value_integer, value.value_number, value.value_text, value.value_date)
    if sum(v is not None for v in typed) != 1:
        raise QualityControlError()
    number = value.value_integer if data_type == "INTEGER" else value.value_number
    if not (
        (data_type == "INTEGER" and type(number) is int and -(2**63) <= number < 2**63)
        or (data_type == "REAL" and type(number) is float and math.isfinite(number))
    ):
        raise QualityControlError()
    return Fraction(str(number))


def iqr_bounds(numbers, policy):
    if len(numbers) < policy.minimum_sample_size or not numbers:
        raise QualityControlError()
    ordered = sorted(numbers)

    def percentile(p):
        position = (len(ordered) - 1) * p
        index = position.numerator // position.denominator
        fraction = position - index
        if fraction == 0:
            return ordered[index]
        return ordered[index] + fraction * (ordered[index + 1] - ordered[index])

    q1, q3 = percentile(Fraction(1, 4)), percentile(Fraction(3, 4))
    spread = policy.multiplier * (q3 - q1)
    return IQRBounds(q1, q3, q1 - spread, q3 + spread)
