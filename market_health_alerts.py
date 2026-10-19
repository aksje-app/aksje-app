"""Conservative, read-only critical market alert classification for indicator dials.

A numeric alarm must have an explicitly validated source-specific policy and
confirmed timestamp; no thresholds are invented in the presentation layer.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta


def critical_alert(key, datum, checked, policy):
    if not checked or checked.get("status") != "CURRENT":
        return None
    if not isinstance(datum, dict) or not isinstance(policy, dict):
        return None
    if policy.get("validated") is not True or policy.get("enabled") is not True:
        return None
    # Display may carry Friday closes into Monday pre-open. Alerts must not
    # classify a multi-day-old reading as a fresh critical event.
    try:
        observed = datetime.fromisoformat(str(checked["observed_at"]).replace("Z", "+00:00"))
        if observed.tzinfo is None or datetime.now(timezone.utc) - observed.astimezone(timezone.utc) > timedelta(hours=36):
            return None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if str(policy.get("indicator") or "") != str(key):
        return None
    direction = policy.get("direction")
    threshold = policy.get("critical_threshold")
    if direction not in ("above", "below") or not isinstance(threshold, (int, float)):
        return None
    try:
        value = float(checked["value"])
        crossed = value >= threshold if direction == "above" else value <= threshold
    except (TypeError, ValueError):
        return None
    if not crossed:
        return None
    return {"indicator": key, "value": value, "threshold": threshold,
            "direction": direction, "observed_at": checked["observed_at"],
            "policy_id": str(policy.get("policy_id") or "unspecified"),
            "severity": "CRITICAL", "source": checked["source"]}
