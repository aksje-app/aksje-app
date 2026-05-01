
def latest_value(series, default=None):
    try:
        clean = series.dropna()
        if len(clean) == 0:
            return default
        return float(clean.iloc[-1])
    except Exception:
        return default


def prev_value(series, default=None):
    try:
        clean = series.dropna()
        if len(clean) < 2:
            return default
        return float(clean.iloc[-2])
    except Exception:
        return default


def rsi_status(rsi_now, rsi_prev=None):
    delta = 0 if rsi_prev is None else rsi_now - rsi_prev
    arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"

    if rsi_now >= 80:
        status = "EKSTREM OVERKJØPT"
        color = "#ff2e2e"
    elif rsi_now >= 70:
        status = "OVERKJØPT"
        color = "#ff6b6b"
    elif rsi_now <= 25:
        status = "EKSTREM LAV"
        color = "#00e676"
    elif rsi_now <= 30:
        status = "OVERSOLGT"
        color = "#00cc96"
    else:
        status = "NØYTRAL"
        color = "#ffa500"

    if abs(delta) > 2:
        momentum = "Sterk"
    elif abs(delta) > 0.7:
        momentum = "Moderat"
    else:
        momentum = "Svak"

    return {
        "status": status,
        "color": color,
        "arrow": arrow,
        "delta": delta,
        "momentum": momentum,
    }


def macd_status(macd_now, signal_now, macd_prev=None, signal_prev=None):
    bullish = macd_now > signal_now
    cross_up = False
    cross_down = False

    if macd_prev is not None and signal_prev is not None:
        cross_up = macd_prev <= signal_prev and macd_now > signal_now
        cross_down = macd_prev >= signal_prev and macd_now < signal_now

    if cross_up:
        status = "MACD krysser opp"
        signal = "BUY"
        color = "#00e676"
    elif cross_down:
        status = "MACD krysser ned"
        signal = "SELL"
        color = "#ff4d4d"
    elif bullish:
        status = "MACD bullish"
        signal = "BULLISH"
        color = "#00cc96"
    else:
        status = "MACD bearish"
        signal = "BEARISH"
        color = "#ff6b6b"

    return {
        "bullish": bullish,
        "cross_up": cross_up,
        "cross_down": cross_down,
        "status": status,
        "signal": signal,
        "color": color,
    }


def combo_signal(rsi_series, macd_series, macd_signal_series):
    rsi_now = latest_value(rsi_series, 50)
    rsi_prev = prev_value(rsi_series, rsi_now)

    macd_now = latest_value(macd_series, 0)
    macd_prev = prev_value(macd_series, macd_now)

    sig_now = latest_value(macd_signal_series, 0)
    sig_prev = prev_value(macd_signal_series, sig_now)

    rsi = rsi_status(rsi_now, rsi_prev)
    macd = macd_status(macd_now, sig_now, macd_prev, sig_prev)

    combo = "HOLD"
    confidence = 50
    reason = "Nøytral kombinasjon"

    # Strong BUY: RSI low and turning up + MACD bullish/crossing up
    if rsi_now < 35 and rsi["delta"] > 0 and (macd["bullish"] or macd["cross_up"]):
        combo = "BUY"
        confidence = 78 if macd["cross_up"] else 70
        reason = "RSI lav/snur opp + MACD bullish"

    # Early BUY
    elif rsi_now < 45 and rsi["delta"] > 1 and macd["cross_up"]:
        combo = "BUY"
        confidence = 72
        reason = "RSI bedrer seg + MACD krysser opp"

    # Strong SELL: RSI high and falling + MACD bearish/crossing down
    elif rsi_now > 70 and rsi["delta"] < 0 and (not macd["bullish"] or macd["cross_down"]):
        combo = "SELL"
        confidence = 80 if macd["cross_down"] else 72
        reason = "RSI overkjøpt/snur ned + MACD bearish"

    # Early SELL
    elif rsi_now > 75 and rsi["delta"] < -1:
        combo = "SELL"
        confidence = 68
        reason = "RSI høy og faller"

    # Trend support
    elif macd["bullish"] and 40 <= rsi_now <= 68:
        combo = "HOLD / BULLISH"
        confidence = 62
        reason = "MACD bullish og RSI i sunn sone"

    elif not macd["bullish"] and rsi_now > 55:
        combo = "HOLD / WEAK"
        confidence = 58
        reason = "MACD bearish og RSI svekkes"

    return {
        "combo": combo,
        "confidence": confidence,
        "reason": reason,
        "rsi_now": round(rsi_now, 1),
        "rsi_prev": round(rsi_prev, 1),
        "rsi_delta": round(rsi["delta"], 2),
        "rsi_status": rsi["status"],
        "rsi_arrow": rsi["arrow"],
        "rsi_momentum": rsi["momentum"],
        "rsi_color": rsi["color"],
        "macd_now": round(macd_now, 4),
        "macd_signal": round(sig_now, 4),
        "macd_status": macd["status"],
        "macd_color": macd["color"],
        "macd_cross_up": macd["cross_up"],
        "macd_cross_down": macd["cross_down"],
    }
