from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class PortfolioDecision:
    ticker: str
    action: str
    reason: str
    theoretical_only: bool = True
    portfolio_assessed: bool = False
    position_size: Mapping[str, Any] = field(default_factory=dict)
    exposure: Mapping[str, Any] = field(default_factory=dict)
    correlation: Mapping[str, Any] = field(default_factory=dict)
