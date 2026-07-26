"""Domain contracts for AI Aksje Analyzer Pro."""
from domain.strategy_versioning import (
    ExecutionMode,
    StrategyStatus,
    StrategyVersion,
    STRATEGY_CONTRACT_SCHEMA_VERSION,
)
from domain.market_snapshot import (
    CandidateSnapshot,
    MarketSnapshot,
    CANDIDATE_SNAPSHOT_SCHEMA_VERSION,
    MARKET_SNAPSHOT_SCHEMA_VERSION,
)

__all__ = [
    "ExecutionMode", "StrategyStatus", "StrategyVersion",
    "STRATEGY_CONTRACT_SCHEMA_VERSION",
    "CandidateSnapshot", "MarketSnapshot",
    "CANDIDATE_SNAPSHOT_SCHEMA_VERSION", "MARKET_SNAPSHOT_SCHEMA_VERSION",
]
