from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class RankedCandidate:
    ticker: str
    market: str
    score: float
    confidence: float
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParallelStrategyAssessment:
    ticker: str
    sector: str
    strategies: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    matches: tuple[str, ...] = field(default_factory=tuple)
    scenario_analysis: Mapping[str, Any] = field(default_factory=dict)
    universal_score_created: bool = False
