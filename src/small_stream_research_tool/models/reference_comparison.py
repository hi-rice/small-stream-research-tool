"""비교 실행 identity와 규칙 설정을 분리한 versioned snapshot. 원본값은 포함하지 않는다."""

import json


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def comparison_snapshot(parameters_json, reference_value_id):
    return json.dumps(
        {
            "format": "reference_compare_v1",
            "rule_parameters": None if parameters_json is None else json.loads(parameters_json),
            "execution": {"reference_value_id": reference_value_id},
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def snapshot_reference_id(snapshot):
    """알 수 없거나 손상된 snapshot은 scope에 포함하지 않는다."""
    try:
        data = json.loads(snapshot, object_pairs_hook=_unique_object)
        if (
            type(data) is not dict
            or set(data) != {"format", "rule_parameters", "execution"}
            or data.get("format") != "reference_compare_v1"
            or (data["rule_parameters"] is not None and type(data["rule_parameters"]) is not dict)
        ):
            return None
        execution = data.get("execution")
        if type(execution) is not dict or set(execution) != {"reference_value_id"}:
            return None
        value = execution.get("reference_value_id")
        return value if type(value) is int and 0 < value < 2**63 else None
    except (TypeError, ValueError, RecursionError):
        return None
