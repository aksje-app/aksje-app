from dataclasses import dataclass


@dataclass(frozen=True)
class PortfolioDecision:
    ticker: str
    action: str
    reason: str
    theoretical_only: bool = True
