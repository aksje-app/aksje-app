"""Advisory early-loss policy for new theoretical positions.

No order execution, mutation or replacement of existing engine stop rules.
Loss thresholds are proposals for Shadow/Paper validation only.
"""
from datetime import datetime, timezone
from math import isfinite


def early_loss_review(*, entry_at, observed_at, entry_price, current_price,
                      thesis_valid=None, score_change=None,
                      relative_return_pct=None, data_fresh=False,
                      trading_sessions_since_entry=None,
                      enabled=False):
    result = {"action":"ORDINARY_STOP_RULES", "execution_authorized":False,
              "early_policy_applied":False, "reason_codes":[]}
    if not enabled:
        result["reason_codes"].append("POLICY_DISABLED")
        return result
    try:
        started = datetime.fromisoformat(str(entry_at).replace("Z","+00:00"))
        observed = datetime.fromisoformat(str(observed_at).replace("Z","+00:00"))
        entry, current = float(entry_price), float(current_price)
        if (started.tzinfo is None or observed.tzinfo is None or observed < started
                or not data_fresh or not all(isfinite(x) and x > 0 for x in (entry,current))):
            raise ValueError("Invalid evidence")
        if (not isinstance(trading_sessions_since_entry,int)
                or isinstance(trading_sessions_since_entry,bool)
                or trading_sessions_since_entry < 0):
            raise ValueError("Trading-session count is required")
    except (TypeError, ValueError, OverflowError):
        result.update(action="OVERVAAK",reason_codes=["MISSING_OR_STALE_EVIDENCE"])
        return result
    if trading_sessions_since_entry >= 5:
        result["reason_codes"].append("INITIAL_WINDOW_ENDED")
        return result
    loss = (current / entry - 1) * 100
    result.update(early_policy_applied=True,loss_pct=round(loss,3))
    if loss <= -2.0:
        result.update(action="SELG",reason_codes=["EARLY_HARD_STOP_2_PCT"])
    elif loss <= -1.5 and thesis_valid is False and (
            (score_change is not None and score_change < 0)
            or (relative_return_pct is not None and relative_return_pct < 0)):
        result.update(action="SELG",reason_codes=["EARLY_CONFIRMED_THESIS_FAILURE"])
    elif loss <= -0.8:
        result.update(action="OVERVAAK",reason_codes=["EARLY_LOSS_REASSESS"])
    else:
        result.update(action="BEHOLD",reason_codes=["NO_EARLY_LOSS_TRIGGER"])
    return result
