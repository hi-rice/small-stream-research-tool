"""Validate the versioned unit-evidence resource without mutating the research DB."""

import hashlib
import json
from importlib.resources import files

from small_stream_research_tool.models.source_unit import (
    UnitApplicability,
    UnitEvidenceItem,
    UnitEvidencePolicy,
)
from small_stream_research_tool.services.research_dictionary_bootstrap import (
    load_research_manifest,
    manifest_fingerprint,
)


class ResearchUnitEvidenceError(Exception):
    def __init__(self):
        super().__init__("연구 단위 근거를 확인할 수 없습니다.")


class ResearchUnitEvidenceService:
    def load(self):
        path = files("small_stream_research_tool").joinpath(
            "resources", "research_unit_evidence_v1.json"
        )
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if set(raw) != {
                "evidence_version",
                "compatible_research_manifest_version",
                "compatible_research_manifest_fingerprint",
                "revision",
                "items",
            }:
                raise ValueError
            research = load_research_manifest(raw["compatible_research_manifest_version"])
            research_fp = manifest_fingerprint(research)
            if research_fp != raw["compatible_research_manifest_fingerprint"]:
                raise ValueError
            v1 = load_research_manifest("research-dictionary-v1")
            expected_names = {
                row["internal_name"] for row in v1["items"] if row["unit_symbol"] is None
            }
            seen = set()
            items = []
            for row in raw["items"]:
                if set(row) != {
                    "internal_name",
                    "applicability",
                    "approved_source_notations",
                    "evidence_id",
                }:
                    raise ValueError
                item = UnitEvidenceItem(
                    row["internal_name"],
                    UnitApplicability(row["applicability"]),
                    tuple(row["approved_source_notations"]),
                    row["evidence_id"],
                )
                if item.internal_name in seen or not item.evidence_id:
                    raise ValueError
                if (
                    item.applicability != UnitApplicability.UNIT_DEFINED
                    and item.approved_source_notations
                ):
                    raise ValueError
                seen.add(item.internal_name)
                items.append(item)
            if seen != expected_names or len(items) != 20:
                raise ValueError
            canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            return UnitEvidencePolicy(
                raw["evidence_version"],
                fingerprint,
                raw["compatible_research_manifest_version"],
                research_fp,
                tuple(items),
            )
        except (OSError, UnicodeError, ValueError, TypeError, KeyError):
            raise ResearchUnitEvidenceError() from None
