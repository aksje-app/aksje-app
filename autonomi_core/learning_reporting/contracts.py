from dataclasses import dataclass


@dataclass(frozen=True)
class LearningOutcome:
    ran: bool
    proposal_created: bool = False
    approval_required: bool = True
    detail: str = ""
