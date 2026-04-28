import pandas as pd
import numpy as np

def _local_extrema(close, order=5):
    highs = []
    lows = []
    values = close.values
    idx = close.index

    for i in range(order, len(values) - order):
        window = values[i-order:i+order+1]
        if values[i] == window.max():
            highs.append((idx[i], float(values[i])))
        if values[i] == window.min():
            lows.append((idx[i], float(values[i])))

    return highs, lows

def detect_head_shoulders(df, lookback=180, tolerance=0.08):
    """
    Enkel hode/skulder-deteksjon:
    Ser etter tre lokale topper hvor midtre topp er høyest,
    og venstre/høyre skulder er omtrent like.
    """
    if df is None or df.empty or len(df) < 80:
        return {"found": False, "label": "For lite data", "confidence": 0}

    close = df["Close"].dropna().tail(lookback)
    highs, lows = _local_extrema(close, order=5)

    if len(highs) < 3:
        return {"found": False, "label": "Ingen tydelig hode/skulder", "confidence": 0}

    # Test de siste kombinasjonene av tre topper
    for a, b, c in zip(highs[-8:], highs[-7:], highs[-6:]):
        left_date, left = a
        head_date, head = b
        right_date, right = c

        if not (left_date < head_date < right_date):
            continue

        shoulders_similar = abs(left - right) / max(left, right) <= tolerance
        head_higher = head > left * (1 + tolerance / 2) and head > right * (1 + tolerance / 2)

        if shoulders_similar and head_higher:
            confidence = min(1.0, (head / max(left, right) - 1) * 5 + 0.45)
            return {
                "found": True,
                "label": "Mulig hode/skulder ⚠️",
                "confidence": round(confidence, 2),
                "points": {
                    "left_shoulder": (str(left_date.date()), left),
                    "head": (str(head_date.date()), head),
                    "right_shoulder": (str(right_date.date()), right),
                },
            }

    return {"found": False, "label": "Ingen tydelig hode/skulder", "confidence": 0}

def detect_inverse_head_shoulders(df, lookback=180, tolerance=0.08):
    """
    Enkel invertert hode/skulder:
    Ser etter tre lokale bunner hvor midtre bunn er lavest.
    """
    if df is None or df.empty or len(df) < 80:
        return {"found": False, "label": "For lite data", "confidence": 0}

    close = df["Close"].dropna().tail(lookback)
    highs, lows = _local_extrema(close, order=5)

    if len(lows) < 3:
        return {"found": False, "label": "Ingen tydelig invertert hode/skulder", "confidence": 0}

    for a, b, c in zip(lows[-8:], lows[-7:], lows[-6:]):
        left_date, left = a
        head_date, head = b
        right_date, right = c

        if not (left_date < head_date < right_date):
            continue

        shoulders_similar = abs(left - right) / max(left, right) <= tolerance
        head_lower = head < left * (1 - tolerance / 2) and head < right * (1 - tolerance / 2)

        if shoulders_similar and head_lower:
            confidence = min(1.0, (min(left, right) / head - 1) * 5 + 0.45)
            return {
                "found": True,
                "label": "Mulig invertert hode/skulder 🟢",
                "confidence": round(confidence, 2),
                "points": {
                    "left_shoulder": (str(left_date.date()), left),
                    "head": (str(head_date.date()), head),
                    "right_shoulder": (str(right_date.date()), right),
                },
            }

    return {"found": False, "label": "Ingen tydelig invertert hode/skulder", "confidence": 0}

def breakout_scanner(df, window=60, volume_window=20):
    """
    Scanner for breakout over motstand eller breakdown under støtte.
    """
    if df is None or df.empty or len(df) < window + 5:
        return {"signal": "For lite data", "type": "neutral", "strength": 0}

    recent = df.tail(window)
    close = df["Close"].dropna()
    latest_close = float(close.iloc[-1])

    resistance = float(recent["High"].iloc[:-1].max()) if "High" in recent else float(recent["Close"].iloc[:-1].max())
    support = float(recent["Low"].iloc[:-1].min()) if "Low" in recent else float(recent["Close"].iloc[:-1].min())

    volume_boost = 1.0
    if "Volume" in df and len(df["Volume"].dropna()) >= volume_window + 2:
        avg_vol = df["Volume"].tail(volume_window + 1).iloc[:-1].mean()
        last_vol = df["Volume"].iloc[-1]
        if avg_vol and avg_vol > 0:
            volume_boost = float(last_vol / avg_vol)

    if latest_close > resistance:
        strength = min(1.0, ((latest_close / resistance) - 1) * 20 + min(volume_boost / 3, 0.5))
        return {
            "signal": "Breakout over motstand 🟢",
            "type": "bullish",
            "strength": round(strength, 2),
            "support": round(support, 2),
            "resistance": round(resistance, 2),
            "volume_boost": round(volume_boost, 2),
        }

    if latest_close < support:
        strength = min(1.0, ((support / latest_close) - 1) * 20 + min(volume_boost / 3, 0.5))
        return {
            "signal": "Breakdown under støtte 🔴",
            "type": "bearish",
            "strength": round(strength, 2),
            "support": round(support, 2),
            "resistance": round(resistance, 2),
            "volume_boost": round(volume_boost, 2),
        }

    distance_to_resistance = (resistance - latest_close) / latest_close
    distance_to_support = (latest_close - support) / latest_close

    return {
        "signal": "Ingen breakout nå",
        "type": "neutral",
        "strength": 0,
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "distance_to_resistance": round(distance_to_resistance, 4),
        "distance_to_support": round(distance_to_support, 4),
        "volume_boost": round(volume_boost, 2),
    }

def build_signal_alerts(rsi_value, macd_value, macd_signal, breakout, hs, inv_hs):
    alerts = []

    if breakout.get("type") == "bullish":
        alerts.append(("Bullish breakout", "Pris har brutt over nylig motstand.", "bullish"))
    elif breakout.get("type") == "bearish":
        alerts.append(("Bearish breakdown", "Pris har falt under nylig støtte.", "bearish"))

    if inv_hs.get("found"):
        alerts.append(("Mulig bullish pattern", "Invertert hode/skulder kan være vendepunkt opp.", "bullish"))

    if hs.get("found"):
        alerts.append(("Mulig bearish pattern", "Hode/skulder kan være vendepunkt ned.", "bearish"))

    if rsi_value <= 30 and macd_value > macd_signal:
        alerts.append(("Oversolgt + MACD bullish", "RSI er lav og MACD peker opp.", "bullish"))

    if rsi_value >= 70 and macd_value < macd_signal:
        alerts.append(("Overkjøpt + MACD bearish", "RSI er høy og MACD peker ned.", "bearish"))

    if not alerts:
        alerts.append(("Ingen sterke alerts", "Ingen tydelige tekniske varsel akkurat nå.", "neutral"))

    return alerts
