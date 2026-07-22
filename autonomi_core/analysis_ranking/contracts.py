from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class RankedCandidate:
    ticker: str
    market: str
    score: float
    confidence: float
    evidence: Mapping[str, Any] = field(default_factory=dict)
