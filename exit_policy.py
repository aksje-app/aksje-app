"""Authoritative exit and capital-replacement policy.

All production, paper and reporting code must consume this contract instead of
maintaining independent numeric defaults.  The evaluator is pure so the exact
same decision can be replayed and shown in the PDF before any mutation occurs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


@dataclass(frozen=True)
class ExitPolicy:
    policy_version: str = "1.0"
    stop_loss_pct: float = 5.0
    take_profit_pct: float = 14.0
    trailing_stop_pct: float = 7.0
    score_exit_threshold: float = 55.0
    score_drop_review_points: float = 7.0
    minimum_hold_hours: float = 24.0
    rsi_exit_level: float = 75.0
    rsi_must_fall: bool = True
    partial_take_profit_pct: float = 25.0
    stagnation_days: int = 20
    stagnation_band_pct: float = 2.0
    replacement_score_advantage: float = 6.0
    cash_review_days: int = 40
    cash_review_max_return_pct: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_EXIT_POLICY = ExitPolicy()


def policy_from(source: Mapping[str, Any] | Any | None = None) -> ExitPolicy:
    """Normalize a mapping/dataclass onto the single governed policy."""
    raw = dict(source or {}) if isinstance(source, Mapping) else {
        key: getattr(source, key) for key in ExitPolicy.__dataclass_fields__ if hasattr(source, key)
    } if source is not None else {}
    base = DEFAULT_EXIT_POLICY.to_dict()
    for key in base:
        if key in raw and raw[key] is not None:
            base[key] = raw[key]
    return ExitPolicy(
        policy_version=str(base["policy_version"]),
        stop_loss_pct=max(.1, min(50.0, _f(base["stop_loss_pct"], 5))),
        take_profit_pct=max(.1, min(300.0, _f(base["take_profit_pct"], 14))),
        trailing_stop_pct=max(.1, min(50.0, _f(base["trailing_stop_pct"], 7))),
        score_exit_threshold=max(0.0, min(100.0, _f(base["score_exit_threshold"], 55))),
        score_drop_review_points=max(0.0, min(100.0, _f(base["score_drop_review_points"], 7))),
        minimum_hold_hours=max(0.0, _f(base["minimum_hold_hours"], 24)),
        rsi_exit_level=max(0.0, min(100.0, _f(base["rsi_exit_level"], 75))),
        rsi_must_fall=bool(base["rsi_must_fall"]),
        partial_take_profit_pct=max(0.0, min(100.0, _f(base["partial_take_profit_pct"], 25))),
        stagnation_days=max(1, int(_f(base["stagnation_days"], 20))),
        stagnation_band_pct=max(0.0, _f(base["stagnation_band_pct"], 2)),
        replacement_score_advantage=max(0.0, _f(base["replacement_score_advantage"], 6)),
        cash_review_days=max(20, int(_f(base["cash_review_days"], 40))),
        cash_review_max_return_pct=max(0.0, _f(base["cash_review_max_return_pct"], 1)),
    )


def evaluate_exit(*, entry_price: float, current_price: float, highest_price: float,
                  entry_score: float = 0.0, current_score: float | None = None,
                  holding_days: int = 0, rsi: float | None = None,
                  previous_rsi: float | None = None, take_profit_taken: bool = False,
                  best_replacement_score: float | None = None,
                  policy: ExitPolicy | Mapping[str, Any] | Any | None = None) -> dict[str, Any]:
    p = policy if isinstance(policy, ExitPolicy) else policy_from(policy)
    entry, price = _f(entry_price), _f(current_price)
    high = max(_f(highest_price, price), price)
    pnl_pct = ((price / entry) - 1) * 100 if entry > 0 and price > 0 else 0.0
    drawdown_from_high = ((price / high) - 1) * 100 if high > 0 and price > 0 else 0.0
    score = _f(current_score, entry_score) if current_score is not None else _f(entry_score)
    score_drop = _f(entry_score) - score if entry_score else 0.0
    result = {"action": "HOLD", "reason_code": "NO_EXIT", "reason": "Ingen exitregel utløst",
              "sell_pct": 0.0, "pnl_pct": round(pnl_pct, 4),
              "drawdown_from_high_pct": round(drawdown_from_high, 4), "policy": p.to_dict()}
    if entry <= 0 or price <= 0:
        return {**result, "reason_code": "PRICE_INVALID", "reason": "Mangler gyldig inngangs- eller markedskurs"}
    if pnl_pct <= -p.stop_loss_pct:
        return {**result, "action": "SELL", "reason_code": "STOP_LOSS", "reason": f"Tap {pnl_pct:.2f}%", "sell_pct": 100.0}
    if high > entry and drawdown_from_high <= -p.trailing_stop_pct:
        return {**result, "action": "SELL", "reason_code": "TRAILING_STOP", "reason": f"Fall {drawdown_from_high:.2f}% fra topp", "sell_pct": 100.0}
    if score and score < p.score_exit_threshold:
        return {**result, "action": "SELL", "reason_code": "SCORE_EXIT", "reason": f"Score falt til {score:.1f}", "sell_pct": 100.0}
    if pnl_pct + 1e-9 >= p.take_profit_pct and not take_profit_taken and p.partial_take_profit_pct > 0:
        return {**result, "action": "SELL_PARTIAL", "reason_code": "TAKE_PROFIT_PARTIAL", "reason": f"Delvis gevinst ved {pnl_pct:.2f}%", "sell_pct": p.partial_take_profit_pct}
    if rsi is not None and _f(rsi) >= p.rsi_exit_level and (not p.rsi_must_fall or (previous_rsi is not None and _f(rsi) < _f(previous_rsi))):
        return {**result, "action": "SELL", "reason_code": "RSI_EXIT", "reason": f"RSI {_f(rsi):.1f} over grensen og faller", "sell_pct": 100.0}
    stagnating = int(holding_days) >= p.stagnation_days and abs(pnl_pct) < p.stagnation_band_pct
    replacement_advantage = (_f(best_replacement_score) - score) if best_replacement_score is not None else 0.0
    if stagnating and score_drop >= p.score_drop_review_points and replacement_advantage >= p.replacement_score_advantage:
        return {**result, "action": "REPLACE_REVIEW", "reason_code": "CAPITAL_REPLACEMENT",
                "reason": f"Sidelengs {holding_days} dager; erstatning er {replacement_advantage:.1f} scorepoeng bedre"}
    if int(holding_days) >= p.cash_review_days and pnl_pct <= p.cash_review_max_return_pct and (score_drop >= p.score_drop_review_points or score < _f(entry_score)):
        return {**result, "action": "CASH_REVIEW", "reason_code": "OPPORTUNITY_COST",
                "reason": f"Kapital bundet i {holding_days} dager med {pnl_pct:.2f}% avkastning og svekket score; kontanter vurderes"}
    if stagnating:
        return {**result, "action": "REVIEW", "reason_code": "CAPITAL_STAGNATION", "reason": f"Kapitalstagnasjon i {holding_days} dager"}
    if score_drop >= p.score_drop_review_points:
        return {**result, "action": "REVIEW", "reason_code": "SCORE_WEAKENED", "reason": f"Score falt {score_drop:.1f} poeng"}
    return result
