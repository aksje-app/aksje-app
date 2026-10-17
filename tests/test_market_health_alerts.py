from datetime import datetime, timedelta, timezone
from market_health_alerts import critical_alert
from market_health_history import normalize


def packet(days=0):
    value={"value": 42.0, "observed_at": (datetime.now(timezone.utc)-timedelta(days=days)).isoformat(), "source": "verified provider"}
    return value, normalize("vix", value)


def test_critical_requires_explicit_validated_rule():
    raw, measured = packet()
    policy={"indicator":"vix","enabled":True,"validated":True,"critical_threshold":40,"direction":"above","policy_id":"TEST"}
    assert critical_alert("vix", raw, measured, policy)["severity"] == "CRITICAL"
    assert critical_alert("vix", raw, measured, {**policy,"validated":False}) is None
    assert critical_alert("vix", raw, measured, {**policy,"indicator":"dxy"}) is None
    assert critical_alert("vix", raw, measured, {**policy,"critical_threshold":50}) is None


def test_stale_or_missing_quote_never_blinks():
    raw, measured=packet(days=3)
    rule={"indicator":"vix","enabled":True,"validated":True,"critical_threshold":40,"direction":"above"}
    assert critical_alert("vix", raw, measured, rule) is None
    assert critical_alert("vix", {}, None, rule) is None
