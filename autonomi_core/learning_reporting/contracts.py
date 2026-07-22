from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class LearningOutcome:
    ran: bool
    proposal_created: bool = False
    approval_required: bool = True
    detail: str = ""


@dataclass(frozen=True)
class CanonicalResultRef:
    """Stable identity shared by reporting, history and learning consumers."""

    result_id: str
    run_id: str
    schema_version: str = "1.0"

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "CanonicalResultRef":
        return cls(
            result_id=str(record.get("result_id") or ""),
            run_id=str(record.get("run_id") or ""),
            schema_version=str(record.get("schema_version") or "1.0"),
        )
