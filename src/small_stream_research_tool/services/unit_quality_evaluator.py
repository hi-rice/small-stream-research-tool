"""단위 metadata만 판정한다. 변환식을 실행하거나 값/단위를 변경하지 않는다."""

import json
import math

from small_stream_research_tool.models.quality_control_errors import QualityRuleConfigurationError
from small_stream_research_tool.services.quality_rule_evaluator import _object

UNIT_RULES = ("UNIT_MATCH", "UNIT_CONVERSION_MISSING")
UNIT_MESSAGES = {
    "UNIT_MISMATCH": "Stored unit does not match the configured unit.",
    "UNIT_MISSING": "Unit information is missing.",
    "UNIT_CONVERSION_MISSING": "No registered direct conversion is available.",
}


def compile_unit_rule(rule, item):
    try:
        if (
            rule.rule_type not in UNIT_RULES
            or rule.target_type != "CHARACTERISTIC_VALUE"
            or rule.dictionary_id != item.dictionary_id
            or item.storage_type != "FLEX"
            or item.data_type not in ("INTEGER", "REAL")
            or rule.default_severity not in ("ERROR", "WARNING", "INFO")
            or type(rule.rule_version) is not str
            or not rule.rule_version.strip()
        ):
            raise ValueError()
        rule.rule_version.encode("utf-8")
        params = (
            None
            if rule.parameters_json is None
            else json.loads(rule.parameters_json, object_pairs_hook=_object)
        )
        if rule.parameters_json is not None and (type(params) is not dict or params):
            raise ValueError()
        return params
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise QualityRuleConfigurationError() from None


def direct_conversion_available(candidates):
    if len(candidates) > 1:
        raise QualityRuleConfigurationError()
    if not candidates:
        return False
    conversion = candidates[0]
    if (
        not conversion.is_active
        or conversion.formula_type != "LINEAR"
        or any(
            type(v) not in (int, float) or not math.isfinite(v)
            for v in (conversion.factor, conversion.offset)
        )
    ):
        raise QualityRuleConfigurationError()
    return True


def unit_issue_type(rule_type, expected, actual, conversion_available=None):
    if expected == actual:
        return None
    if rule_type == "UNIT_MATCH":
        return "UNIT_MISSING" if actual is None else "UNIT_MISMATCH"
    if actual is None:
        # actual→expected 방향을 구성할 수 없다. UNIT_MATCH의 missing 검사와 구분한다.
        raise QualityRuleConfigurationError()
    return None if conversion_available else "UNIT_CONVERSION_MISSING"


def unit_snapshot(parameters, expected, actual):
    return json.dumps(
        {
            "format": "unit_qc_v1",
            "rule_parameters": parameters,
            "execution": {"expected_unit_id": expected, "actual_unit_id": actual},
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
