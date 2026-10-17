"""Read-only forensic evidence for stop-loss/profit-protection and diagnostics.

Does not place trades, change strategy thresholds or access market providers.
"""
from __future__ import annotations
import json
from typing import Any, Mapping


def classify_exit(row: Mapping[str, Any]) -> dict[str, Any]:
    evidence = row.get("evidence_metadata") or {}
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except (ValueError, TypeError):
            evidence = {}
    evidence = evidence if isinstance(evidence, dict) else {}
    def number(value):
        try:
            return float(value) if value is not None and value != "" else None
        except (TypeError, ValueError):
            return None
    observed = number(row.get("price")) or number(evidence.get("exit_price"))
    stop = number(evidence.get("stop_trigger_price")) or number(row.get("rule_limit"))
    result = number(row.get("pnl_pct"))
    label = str(row.get("rule_used") or row.get("reason") or "")
    is_protection = "profit protection" in label.lower()
    triggered = stop is not None and observed is not None and observed <= stop
    gap = (observed / stop - 1) * 100 if stop and observed is not None else None
    findings = []
    if triggered and gap is not None and gap < -0.5:
        findings.append("EXECUTION_BELOW_TRIGGER")
    if is_protection and result is not None and result < 0:
        findings.append("PROFIT_PROTECTION_REALIZED_LOSS")
    if row.get("type") == "SELL" and not evidence.get("execution_quote"):
        findings.append("EXECUTION_QUOTE_NOT_RECORDED")
    if row.get("type") == "SELL" and not evidence.get("market_data_at"):
        findings.append("PRICE_TIMESTAMP_NOT_RECORDED")
    return {
        "ticker": row.get("ticker"), "trade_id": row.get("trade_id") or row.get("id"),
        "event_time": row.get("time"), "rule": label,
        "entry_price": number(evidence.get("entry_price")),
        "peak_gain_pct": number(evidence.get("peak_gain_pct")),
        "trigger_price": stop, "execution_price": observed,
        "execution_gap_pct": round(gap, 3) if gap is not None else None,
        "realized_pnl_pct": result, "quote": evidence.get("execution_quote"),
        "quote_timestamp": evidence.get("market_data_at"),
        "run_id": evidence.get("run_id"), "findings": findings,
        "status": "REVIEW_REQUIRED" if findings else "NO_FINDINGS",
        "note": "A breached trigger is not proof of execution defect; inspect quote sequence and liquidity.",
    }


def error_evidence(errors, *, limit=250):
    rows = []
    for event in list(errors or [])[-limit:]:
        if not isinstance(event, dict):
            continue
        rows.append({k: event.get(k) for k in ("at", "event", "severity", "component", "stage", "run_id", "error_code", "message", "error", "source_id")})
    return rows


def diagnostic_manifest(entries: Mapping[str, bytes]) -> dict[str, Any]:
    import hashlib
    return {"schema": 1, "files": [{"path": name, "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()} for name, value in sorted(entries.items())], "strategy_validated": False, "trade_execution_enabled": False}
