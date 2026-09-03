"""Single fail-closed Paper Trading gate for v19.14.2."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import Any, Mapping

from durable_runtime import read_json, write_json
from runtime_safety import paper_trading_decision
from storage_architecture import runtime_data_path


class PaperTradingDisabledError(RuntimeError):
    """Raised by the persistence layer when a trade write bypasses the order API."""


@dataclass(frozen=True)
class TradeGateResult:
    allowed: bool
    code: str
    message: str
    action: str
    ticker: str
    source: str
    run_id: str = ""


_LOCK = RLock()
_RUN_ACTIONS: "OrderedDict[str, dict[str, set[str]]]" = OrderedDict()
_MAX_RUNS = 200
_PERSISTENT_KEY = "paper_trading/trade_run_registry.json"
_PERSISTENT_PATH = runtime_data_path("paper_trading", "trade_run_registry.json")


def _persistent_actions() -> dict[str, dict[str, list[str]]]:
    value = read_json(_PERSISTENT_KEY, _PERSISTENT_PATH, {})
    if not isinstance(value, Mapping):
        return {}
    return {
        str(run_id): {
            str(ticker).upper(): sorted({str(action).upper() for action in actions})
            for ticker, actions in tickers.items() if isinstance(actions, (list, tuple, set))
        }
        for run_id, tickers in value.items() if isinstance(tickers, Mapping)
    }


def _normalise_action(action: Any) -> str:
    value = str(action or "TRADE").strip().upper()
    aliases = {"KJØP": "BUY", "KJOP": "BUY", "SALG": "SELL", "SELGE": "SELL"}
    return aliases.get(value, value)


def check_paper_trade(
    action: Any,
    *,
    ticker: Any = "",
    source: Any = "",
    run_id: Any = "",
    candidate: Mapping[str, Any] | None = None,
    automatic: bool = False,
) -> TradeGateResult:
    action_n = _normalise_action(action)
    ticker_n = str(ticker or "").strip().upper()
    source_n = str(source or "paper_order_layer").strip()
    run_n = str(run_id or "").strip()
    decision = paper_trading_decision()
    if not decision.allowed:
        return TradeGateResult(
            False, decision.code,
            f"{decision.reason} {action_n} {ticker_n or ''}".strip(),
            action_n, ticker_n, source_n, run_n,
        )

    if action_n == "BUY" and candidate:
        outcome = str(candidate.get("autonomy_outcome_code") or "").upper()
        portfolio_action = str(candidate.get("portfolio_action") or candidate.get("decision") or "").upper()
        valid_data = candidate.get("valid_for_decision") is not False
        valid_evidence = candidate.get("evidence_valid_for_decision") is not False
        if outcome and outcome != "KJØPSKANDIDAT":
            return TradeGateResult(False, "CANDIDATE_NOT_APPROVED", "Kjøp blokkert: kandidaten er ikke Kjøpskandidat.", action_n, ticker_n, source_n, run_n)
        if portfolio_action and portfolio_action not in {"BUY", "KJØP", "BUY_ELIGIBLE"}:
            return TradeGateResult(False, "ACTION_NOT_BUY", "Kjøp blokkert: beslutningen er ikke BUY/KJØP.", action_n, ticker_n, source_n, run_n)
        if not valid_data:
            return TradeGateResult(False, "INVALID_MARKET_DATA", "Kjøp blokkert: markedsdata er ikke beslutningsgyldige.", action_n, ticker_n, source_n, run_n)
        if not valid_evidence:
            return TradeGateResult(False, "INVALID_EVIDENCE", "Kjøp blokkert: evidensgrunnlaget er ikke beslutningsgyldig.", action_n, ticker_n, source_n, run_n)
    elif automatic and action_n == "BUY" and candidate is None:
        return TradeGateResult(
            False, "MISSING_CANDIDATE_CONTEXT",
            "Automatisk kjøp er blokkert fordi beslutningsgrunnlaget mangler.",
            action_n, ticker_n, source_n, run_n,
        )

    if run_n and ticker_n:
        opposite = "SELL" if action_n == "BUY" else "BUY" if action_n == "SELL" else ""
        with _LOCK:
            memory_actions = _RUN_ACTIONS.get(run_n, {}).get(ticker_n, set())
            durable_actions = set(_persistent_actions().get(run_n, {}).get(ticker_n, []))
            actions = set(memory_actions) | durable_actions
            if opposite and opposite in actions:
                return TradeGateResult(
                    False, "SAME_RUN_ROUNDTRIP",
                    f"{ticker_n} kan ikke både kjøpes og selges i samme kjøring ({run_n}).",
                    action_n, ticker_n, source_n, run_n,
                )
    return TradeGateResult(True, "ALLOWED", "Paper-handelen er godkjent av sentral sperre.", action_n, ticker_n, source_n, run_n)


def record_paper_trade(action: Any, *, ticker: Any = "", run_id: Any = "") -> None:
    run_n = str(run_id or "").strip()
    ticker_n = str(ticker or "").strip().upper()
    action_n = _normalise_action(action)
    if not run_n or not ticker_n or action_n not in {"BUY", "SELL"}:
        return
    with _LOCK:
        run_actions = _RUN_ACTIONS.setdefault(run_n, {})
        run_actions.setdefault(ticker_n, set()).add(action_n)
        _RUN_ACTIONS.move_to_end(run_n)
        while len(_RUN_ACTIONS) > _MAX_RUNS:
            _RUN_ACTIONS.popitem(last=False)
        durable = _persistent_actions()
        tickers = durable.setdefault(run_n, {})
        tickers[ticker_n] = sorted(set(tickers.get(ticker_n, [])) | {action_n})
        if len(durable) > _MAX_RUNS:
            for old_run in list(durable)[:-_MAX_RUNS]:
                durable.pop(old_run, None)
        write_json(_PERSISTENT_KEY, _PERSISTENT_PATH, durable)


def require_paper_trade(action: Any, **kwargs: Any) -> TradeGateResult:
    result = check_paper_trade(action, **kwargs)
    if not result.allowed:
        raise PaperTradingDisabledError(result.message)
    return result


def clear_trade_registry() -> None:
    with _LOCK:
        _RUN_ACTIONS.clear()
        write_json(_PERSISTENT_KEY, _PERSISTENT_PATH, {})


__all__ = [
    "PaperTradingDisabledError", "TradeGateResult", "check_paper_trade",
    "clear_trade_registry", "record_paper_trade", "require_paper_trade",
]
