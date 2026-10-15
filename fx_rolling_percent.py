"""Rolling percentage FX signals, independent of manual price-limit alerts.

An hourly history fetch supports every lookback from 1 hour to 30 days.
No alerts are generated when a historical comparison is unavailable.
"""
from datetime import datetime, timedelta, timezone

WINDOWS = (
    ("1t", 1, .5), ("6t", 6, .8), ("12t", 12, 1.0),
    ("24t", 24, 1.5), ("48t", 48, 2.0),
    ("3d", 72, 2.5), ("5d", 120, 3.0), ("7d", 168, 3.5),
    ("14d", 336, 4.0), ("21d", 504, 4.5), ("30d", 720, 5.0),
)
STATE_KEY = "fx_rolling_pct_alerts_v1"
MIN_REPEAT_HOURS = 6
EXTRA_MOVE_PCT = .5


def historical_changes(symbol, current_rate, *, ticker_factory=None, now=None):
    """Return percentage changes based on actual historical observations.

    Older weekend/holiday prices are accepted only within 72h of target;
    the 1h lookback requires data no older than 90 minutes.
    """
    if ticker_factory is None:
        import yfinance as yf
        ticker_factory = yf.Ticker
    now = now or datetime.now(timezone.utc)
    history = ticker_factory(symbol).history(
        period="60d", interval="1h", auto_adjust=False, prepost=True
    )
    if history is None or getattr(history, "empty", True) or "Close" not in history:
        return []
    close = history["Close"].dropna()
    if close.empty:
        return []
    points = []
    for ts, value in close.items():
        try:
            dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            points.append((dt.astimezone(timezone.utc), float(value)))
        except (TypeError, ValueError):
            continue
    if not points or (now - points[-1][0]) > timedelta(hours=3):
        return []
    output = []
    for label, hours, threshold in WINDOWS:
        target = now - timedelta(hours=hours)
        possible = [(t, value) for t, value in points if t <= target]
        if not possible:
            continue
        observed_at, reference = possible[-1]
        max_age = timedelta(minutes=90) if hours == 1 else timedelta(hours=72)
        if target - observed_at > max_age or reference <= 0:
            continue
        pct = (float(current_rate) / reference - 1) * 100
        output.append({
            "window": label, "hours": hours, "threshold": threshold,
            "change_pct": round(pct, 4), "reference_rate": reference,
            "reference_at": observed_at.isoformat(),
            "breach": abs(pct) >= threshold,
        })
    return output


def evaluate(settings, *, symbol, pair, rate, sender, now=None, changes=None):
    """One consolidated Pushover per movement direction and severity upgrade.

    All stored data is compact; no price history is retained in the settings DB.
    """
    now = now or datetime.now(timezone.utc)
    changes = historical_changes(symbol, rate, now=now) if changes is None else changes
    root = settings.setdefault(STATE_KEY, {})
    key = str(symbol)
    state = dict(root.get(key) or {})
    breached = [x for x in changes if x.get("breach")]
    if not breached:
        if changes:
            state["direction"] = None
            state["peak_pct"] = 0
            state["last_window"] = None
        state["last_checked_at"] = now.isoformat()
        root[key] = state
        return {"sent": False, "reason": "no_breach", "windows_checked": len(changes)}

    strongest = max(breached, key=lambda x: abs(x["change_pct"]) / x["threshold"])
    direction = "up" if strongest["change_pct"] > 0 else "down"
    magnitude = max(abs(x["change_pct"]) for x in breached if (x["change_pct"] > 0) == (direction == "up"))
    old_direction = state.get("direction")
    old_peak = float(state.get("peak_pct") or 0) if old_direction == direction else 0
    previous_at = state.get("last_sent_at")
    try:
        last_sent = datetime.fromisoformat(previous_at) if previous_at else None
        if last_sent and last_sent.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=timezone.utc)
    except ValueError:
        last_sent = None
    new_direction = old_direction != direction
    upgraded = magnitude >= old_peak + EXTRA_MOVE_PCT
    ready = not last_sent or now - last_sent >= timedelta(hours=MIN_REPEAT_HOURS)
    should_send = bool(new_direction or (upgraded and ready))
    state["last_checked_at"] = now.isoformat()
    state["direction"] = direction
    state["last_window"] = strongest["window"]
    result = {"sent": False, "reason": "suppressed", "direction": direction,
              "change_pct": strongest["change_pct"], "window": strongest["window"],
              "windows_checked": len(changes)}
    if should_send:
        direction_label = "styrket" if direction == "up" else "svekket"
        lines = [
            f"{pair} – prosentvis valutabevegelse",
            f"1 BRL = {rate:.4f} NOK",
            f"BRL har {direction_label} seg {abs(strongest['change_pct']):.2f} % over {strongest['window']}.",
            f"Referanse: {strongest['reference_rate']:.4f} NOK ({strongest['reference_at']})",
            f"Registrert: {now.isoformat()}",
            "Varslet er et markedssignal, ikke en automatisk handelsordre.",
        ]
        try:
            response = sender("\n".join(lines), title=f"Valutasignal {pair}")
            ok = bool(response[0]) if isinstance(response, tuple) else bool(response)
        except Exception as exc:
            result["error"] = str(exc)[:200]
            ok = False
        if ok:
            state["last_sent_at"] = now.isoformat()
            state["peak_pct"] = magnitude
            result.update(sent=True, reason="new_direction" if new_direction else "larger_move")
        else:
            result["reason"] = "send_failed"
    root[key] = state
    return result
