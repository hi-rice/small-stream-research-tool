"""원본 통계값 없이 명시적 모집단의 구성과 알고리즘 identity를 보존한다."""

import hashlib
import json

from small_stream_research_tool.models.reference_comparison import _unique_object

ALGORITHM = "linear_n_minus_one_v1"


def population_identity(ids, dictionary_id, unit_id):
    payload = json.dumps(
        {"value_ids": sorted(ids), "dictionary_id": dictionary_id, "unit_id": unit_id},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def statistical_snapshot(parameters, ids, dictionary_id, unit_id):
    return json.dumps(
        {
            "format": "statistical_outlier_v1",
            "rule_parameters": json.loads(parameters),
            "execution": {
                "population_value_ids": sorted(ids),
                "sample_size": len(ids),
                "dictionary_id": dictionary_id,
                "unit_id": unit_id,
                "population_identity": population_identity(ids, dictionary_id, unit_id),
                "percentile_algorithm": ALGORITHM,
            },
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def snapshot_population_identity(snapshot):
    try:
        data = json.loads(snapshot, object_pairs_hook=_unique_object)
        if type(data) is not dict or data.get("format") != "statistical_outlier_v1":
            return None
        execution = data["execution"]
        ids = execution["population_value_ids"]
        if (
            type(ids) is not list
            or not ids
            or not all(type(i) is int and 0 < i < 2**63 for i in ids)
            or ids != sorted(set(ids))
            or execution["sample_size"] != len(ids)
            or execution["percentile_algorithm"] != ALGORITHM
        ):
            return None
        identity = population_identity(ids, execution["dictionary_id"], execution["unit_id"])
        return identity if execution["population_identity"] == identity else None
    except (KeyError, TypeError, ValueError, RecursionError):
        return None
