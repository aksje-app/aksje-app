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


def validate_observation(*, observed_at, evaluated_at, max_age_minutes=60,
                         provider_confirmed=False, session_count_verified=False):
    """Verify provenance and age before any early-loss preview.

    The caller must obtain these facts from its market provider/calendar.
    Timestamp arithmetic alone cannot prove quote or session authenticity.
    """
    try:
        observed = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
        evaluated = datetime.fromisoformat(str(evaluated_at).replace("Z", "+00:00"))
        age = (evaluated - observed).total_seconds() / 60
        valid = (observed.tzinfo is not None and evaluated.tzinfo is not None
                 and isinstance(max_age_minutes, (int, float))
                 and isfinite(max_age_minutes) and max_age_minutes > 0
                 and 0 <= age <= max_age_minutes
                 and provider_confirmed is True and session_count_verified is True)
    except (TypeError, ValueError, OverflowError):
        valid = False
    return {"verified":bool(valid), "execution_authorized":False,
            "reason": "VERIFIED_OBSERVATION" if valid else "UNVERIFIED_OR_STALE_OBSERVATION"}


def review_with_verified_observation(position, evidence, *, entry_field,
                                     price_field, current_field):
    """Strict adapter shared across engines. Never guesses session age."""
    check = validate_observation(
        observed_at=evidence.get("observed_at"),
        evaluated_at=evidence.get("evaluated_at"),
        max_age_minutes=evidence.get("max_age_minutes", 60),
        provider_confirmed=evidence.get("provider_confirmed", False),
        session_count_verified=evidence.get("session_count_verified", False))
    result = early_loss_review(
        entry_at=position.get(entry_field),
        observed_at=evidence.get("observed_at"),
        entry_price=position.get(price_field),
        current_price=evidence.get(current_field),
        thesis_valid=evidence.get("thesis_valid"),
        score_change=evidence.get("score_change"),
        relative_return_pct=evidence.get("relative_return_pct"),
        data_fresh=check["verified"],
        trading_sessions_since_entry=evidence.get("trading_sessions_since_entry"),
        enabled=evidence.get("early_loss_preview_enabled", False))
    return {**result, "observation_check":check}
