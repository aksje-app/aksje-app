"""Durable confirmation from two qualifying scans and distinct fresh bars.

These are repeated technical checks, not independent fundamental research.
The atomic document survives cron restarts; missing evidence fails closed.
"""
from datetime import datetime, timezone
from math import isfinite

from scanner_fresh_quote import validate_execution_quote

KEY = "paper_trading/entry_confirmations.json"
MIN_GAP_MINUTES = 10
WINDOW_MINUTES = 120


def observe_entry(ticker, result, quote, run_id, *, min_score, min_confidence,
                  storage=None, now=None):
    from services.storage_service import get_storage_service
    storage = storage or get_storage_service()
    now = now or datetime.now(timezone.utc)
    ticker = str(ticker).upper()
    valid = False
    try:
        score = float(result.get("score"))
        confidence = float(result.get("confidence"))
        valid = (str(result.get("signal")).upper() == "BUY" and isfinite(score)
                 and isfinite(confidence) and score >= min_score and confidence >= min_confidence)
        if valid:
            valid, _ = validate_execution_quote(quote["price"], {
                "execution_quote": quote, "market_data_at": quote["market_data_at"]}, now=now)
    except (TypeError, ValueError, KeyError):
        valid = False

    def update(raw):
        entries = dict(raw or {})
        cutoff = now.timestamp() - WINDOW_MINUTES * 60
        entries = {key: value for key, value in entries.items()
                   if isinstance(value, dict) and float(value.get("observed_epoch", 0)) >= cutoff}
        if not valid:
            entries.pop(ticker, None)
            return entries
        previous = entries.get(ticker, {})
        samples = list(previous.get("samples") or [])
        sample = {"run_id": str(run_id), "market_data_at": quote["market_data_at"],
                  "price": quote["price"], "score": score, "confidence": confidence,
                  "observed_at": now.isoformat()}
        if samples:
            last = samples[-1]
            gap = (datetime.fromisoformat(sample["market_data_at"]) -
                   datetime.fromisoformat(last["market_data_at"])).total_seconds() / 60
            if str(last["run_id"]) != str(run_id) and gap >= MIN_GAP_MINUTES:
                samples.append(sample)
            elif gap < 0:
                samples = []  # out-of-order evidence cannot confirm an entry
        else:
            samples.append(sample)
        entries[ticker] = {"ticker": ticker, "samples": samples[-2:], "observed_epoch": now.timestamp()}
        return dict(sorted(entries.items(), key=lambda pair: pair[1]["observed_epoch"], reverse=True)[:500])

    state = storage.mutate_json(KEY, update, default={})
    proof = dict(state.get(ticker) or {})
    proof["status"] = "CONFIRMED" if len(proof.get("samples") or []) >= 2 else "WAITING"
    return proof


def entry_is_confirmed(ticker, quote, proof, *, now=None):
    try:
        samples = proof["samples"]
        if proof.get("ticker") != str(ticker).upper() or len(samples) != 2:
            return False
        first, last = samples
        gap = (datetime.fromisoformat(last["market_data_at"]) -
               datetime.fromisoformat(first["market_data_at"])).total_seconds() / 60
        age = ((now or datetime.now(timezone.utc)) - datetime.fromisoformat(first["observed_at"])).total_seconds() / 60
        return (MIN_GAP_MINUTES <= gap <= WINDOW_MINUTES and 0 <= age <= WINDOW_MINUTES
                and first["run_id"] != last["run_id"]
                and last["market_data_at"] == quote["market_data_at"]
                and abs(float(last["price"]) - float(quote["price"])) < 1e-8)
    except (KeyError, TypeError, ValueError):
        return False
