"""Source-unit evidence and per-workflow confirmation models."""

from dataclasses import dataclass, field
from enum import StrEnum


class UnitApplicability(StrEnum):
    UNIT_DEFINED = "UNIT_DEFINED"
    UNITLESS = "UNITLESS"
    UNRESOLVED = "UNRESOLVED"


class UnitConfirmationStatus(StrEnum):
    UNCONFIRMED = "UNCONFIRMED"
    CONFIRMED = "CONFIRMED"
    MISMATCH = "MISMATCH"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class UnitEvidenceItem:
    internal_name: str
    applicability: UnitApplicability
    approved_source_notations: tuple[str, ...] = ()
    evidence_id: str = ""


@dataclass(frozen=True)
class UnitEvidencePolicy:
    version: str
    fingerprint: str
    research_version: str
    research_fingerprint: str
    items: tuple[UnitEvidenceItem, ...]


@dataclass(frozen=True)
class SourceUnitConfirmation:
    source_column_index: int
    mapped_internal_name: str
    applicability: UnitApplicability
    expected_unit_id: int | None = field(default=None, repr=False)
    selected_unit_id: int | None = field(default=None, repr=False)
    source_notation: str | None = field(default=None, repr=False)
    status: UnitConfirmationStatus = UnitConfirmationStatus.UNCONFIRMED
    mapping_generation: str = field(default="", repr=False)
    research_fingerprint: str = field(default="", repr=False)
    evidence_fingerprint: str = field(default="", repr=False)
