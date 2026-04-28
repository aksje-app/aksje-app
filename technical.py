import pandas as pd

def calculate_rsi(df, period=14):
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_macd(df):
    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    histogram = macd - signal
    return macd, signal, histogram

def calculate_bollinger(df, window=20, std_mult=2):
    ma = df["Close"].rolling(window=window).mean()
    std = df["Close"].rolling(window=window).std()
    upper = ma + (std * std_mult)
    lower = ma - (std * std_mult)
    return ma, upper, lower

def detect_trend(df):
    ma50 = df["Close"].rolling(50).mean()
    ma200 = df["Close"].rolling(200).mean()
    if len(df) < 200 or pd.isna(ma50.iloc[-1]) or pd.isna(ma200.iloc[-1]):
        return "For lite data"
    return "Opptrend 📈" if ma50.iloc[-1] > ma200.iloc[-1] else "Nedtrend 📉"

def technical_signal(rsi_value, macd_value, signal_value, close_value, upper_bb, lower_bb):
    signals = []
    if rsi_value >= 70:
        signals.append("RSI: Overkjøpt ⚠️")
    elif rsi_value <= 30:
        signals.append("RSI: Oversolgt 🟢")
    else:
        signals.append("RSI: Nøytral")

    signals.append("MACD: Bullish 🟢" if macd_value > signal_value else "MACD: Bearish 🔴")

    if close_value > upper_bb:
        signals.append("Pris over Bollinger Band ⚠️")
    elif close_value < lower_bb:
        signals.append("Pris under Bollinger Band 🟢")
    else:
        signals.append("Bollinger: Normal")
    return signals
