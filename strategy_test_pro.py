"""Strategi-test Pro: historisk simulering, intervall-testing og smart optimalisering.

V12 dekker:
- test av én eller flere tickere samtidig
- ferdige test-ranger: rask, standard og kraftig smart-test
- kombinasjonsvern, slik at appen ikke henger ved for store intervaller
- automatisk logg av resultater og grovtest
- PDF-rapport og strategi-profiler
- in-sample / out-of-sample-validering for å redusere falsk beste strategi

Merk: Dette er historisk simulering med teknisk score-proxy, ikke investeringsråd
og ikke ordreutførelse.
"""

from __future__ import annotations
import logging

import html
import itertools
import json
import math
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from global_busy import set_global_busy, update_global_busy, finish_global_busy

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None


PERIOD_MAP = {
    "3 måneder": "3mo",
    "6 måneder": "6mo",
    "1 år": "1y",
    "2 år": "2y",
    "5 år": "5y",
    "Maks": "max",
}

LOG_FILE = Path("strategy_test_logs.json")  # legacy fallback only
PROFILE_FILE = Path("strategy_profiles.json")  # legacy fallback only
LOG_STORAGE_KEY = "strategy_testing/logs.json"
PROFILE_STORAGE_KEY = "strategy_testing/profiles.json"
MAX_DISPLAY_ROWS = 25
MAX_SMART_STAGE_COMBINATIONS = 2_500


def _safe_rerun() -> None:
    try:
        st.rerun()
    except AttributeError:  # pragma: no cover
        try:
            st.experimental_rerun()
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)


def _render_pro_progress_step(holder: Any, progress: Any, *, step: int, total: int, text: str) -> None:
    pct = min(1.0, max(0.0, step / max(1, total)))
    holder.markdown(
        f'<div style="position:relative;z-index:50;display:flex;align-items:center;gap:.75rem;border:2px solid rgba(56,189,248,.82);background:linear-gradient(180deg,rgba(7,89,133,.80),rgba(15,23,42,.98));border-radius:18px;padding:.92rem 1rem;margin:.55rem 0 .75rem 0;color:#e5edf8;box-shadow:0 14px 32px rgba(14,165,233,.26);">'
        '<style>@keyframes proSpin{to{transform:rotate(360deg)}}</style>'
        '<span style="width:21px;height:21px;border:4px solid rgba(125,211,252,.25);border-top-color:#38bdf8;border-radius:999px;display:inline-block;animation:proSpin .72s linear infinite;flex:0 0 auto;"></span>'
        '<span style="font-weight:950;color:#f8fafc;">Strategi-test Pro</span>'
        f'<span style="color:#bae6fd;font-weight:900;">{step}/{total}</span>'
        f'<span style="color:#cbd5e1;font-weight:750;">{html.escape(str(text))}</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    try:
        progress.progress(pct, text=f"{step}/{total} {text}")
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
    try:
        time.sleep(0.55)
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)


def _finish_pro_progress(holder: Any, progress: Any, text: str, ok: bool = True) -> None:
    border = "rgba(34,197,94,.58)" if ok else "rgba(250,204,21,.62)"
    color = "#bbf7d0" if ok else "#fde68a"
    holder.markdown(
        f'<div style="border:1px solid {border};background:rgba(15,23,42,.88);border-radius:14px;padding:.55rem .72rem;margin:.35rem 0 .45rem 0;color:{color};font-weight:900;">✅ Strategi-test Pro: {html.escape(str(text))}</div>',
        unsafe_allow_html=True,
    )
    try:
        progress.empty()
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)


def _storage():
    try:
        from services.storage_service import get_storage_service
        return get_storage_service()
    except Exception:
        return None


def _storage_key_for_path(path: Path) -> str:
    name = str(path.name)
    if name == LOG_FILE.name:
        return LOG_STORAGE_KEY
    if name == PROFILE_FILE.name:
        return PROFILE_STORAGE_KEY
    return f"strategy_testing/{name}"


TEST_TYPE_OPTIONS = [
    "Gjeldende regler",
    "Rask test",
    "Standard test",
    "Kraftig smart-test",
    "Finjuster siste grovtest",
    "Egendefinert intervall",
]

TEST_TYPE_HELP = {
    "Gjeldende regler": 'Tester bare verdiene som står i "Juster gjeldende regler". Ingen optimalisering.',
    "Rask test": "Få forhåndsvalgte intervaller. Rask kontroll av om strategien har potensial.",
    "Standard test": "Balansert intervall-test. Anbefalt startpunkt for én eller flere aksjer.",
    "Kraftig smart-test": "Kjører først grovtest, lagrer toppresultater, og finjusterer automatisk rundt de beste.",
    "Finjuster siste grovtest": "Bruker sist lagrede grovtest fra loggen og finjusterer den videre.",
    "Egendefinert intervall": "Bruker intervallene du selv skriver inn i feltene under.",
}

VALIDATION_METHOD_OPTIONS = [
    "Ingen validering / hele perioden",
    "70/30 in-sample / out-of-sample",
    "80/20 in-sample / out-of-sample",
    "Walk-forward test",
]

VALIDATION_HELP = {
    "Ingen validering / hele perioden": "Bruker hele perioden både til test og vurdering. Raskt, men høyere risiko for falsk beste strategi.",
    "70/30 in-sample / out-of-sample": "Første 70 % finner reglene. Siste 30 % tester låste regler uten ny justering.",
    "80/20 in-sample / out-of-sample": "Første 80 % finner reglene. Siste 20 % tester låste regler uten ny justering.",
    "Walk-forward test": "Bruker rullerende out-of-sample-kontroll av låste regler over flere senere perioder.",
}

TRAINING_SHARE_OPTIONS = [60, 70, 80]


def _safe_widget_suffix(text: str) -> str:
    return str(text or "").lower().replace(" ", "_").replace("/", "_").replace("-", "_").replace("æ", "ae").replace("ø", "o").replace("å", "a")


@dataclass(frozen=True)
class RuleSet:
    min_buy_score: float
    min_buy_confidence: int
    max_buy_rsi: int
    stop_loss_pct: float
    take_profit_pct: float
    trailing_stop_pct: float
    rsi_exit_level: int
    position_size_pct: float
    max_open_positions: int = 5
    max_trades_per_day: int = 5  # brukes som maks kjøp per dag i V12

    def as_label(self) -> str:
        return (
            f"Score≥{self.min_buy_score:.1f}, Conf≥{self.min_buy_confidence}, "
            f"RSI≤{self.max_buy_rsi}, SL {self.stop_loss_pct:.1f}%, "
            f"TP {self.take_profit_pct:.1f}%, Trail {self.trailing_stop_pct:.1f}%"
        )

    def to_row(self) -> Dict[str, object]:
        return {
            "Min score": self.min_buy_score,
            "Min confidence": self.min_buy_confidence,
            "Maks RSI kjøp": self.max_buy_rsi,
            "Stop-loss %": self.stop_loss_pct,
            "Take-profit %": self.take_profit_pct,
            "Trailing stop %": self.trailing_stop_pct,
            "RSI exit": self.rsi_exit_level,
            "Posisjonsstørrelse %": self.position_size_pct,
            "Maks kjøp per dag": self.max_trades_per_day,
        }


# -------------------------------------------------------------------
# Data og score-proxy
# -------------------------------------------------------------------
@st.cache_data(ttl=30 * 60, show_spinner=False)
def fetch_strategy_histories(tickers_tuple: Tuple[str, ...], period: str) -> Dict[str, pd.DataFrame]:
    """Henter historikk for en liste tickere. Cache hindrer nye kall ved hver rerun."""
    if yf is None:
        return {}

    out: Dict[str, pd.DataFrame] = {}
    for ticker in tickers_tuple:
        try:
            hist = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=False, prepost=False)
            if hist is None or hist.empty or "Close" not in hist:
                continue
            hist = hist.copy()
            hist.index = pd.to_datetime(hist.index).tz_localize(None)
            cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in hist.columns]
            out[ticker] = hist[cols].dropna(subset=["Close"])
        except Exception:
            continue
    return out


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, math.nan)
    return (100 - (100 / (1 + rs))).fillna(50)


def _clip01(series: pd.Series) -> pd.Series:
    return series.clip(lower=0, upper=1)


def add_historical_score_proxy(df: pd.DataFrame) -> pd.DataFrame:
    """Historisk proxy for Top Pick-score og confidence uten lookahead."""
    out = df.copy()
    close = out["Close"].astype(float)
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    mom20 = close.pct_change(20)
    vol20 = close.pct_change().rolling(20).std() * math.sqrt(252)
    dd60 = close / close.rolling(60).max() - 1

    rsi = _rsi(close)
    trend_score = _clip01((close / ma50 - 0.92) / 0.20).fillna(0.50)
    momentum_score = _clip01((mom20 + 0.12) / 0.30).fillna(0.50)
    rsi_score = _clip01((75 - rsi) / 55).fillna(0.50)
    risk_score = _clip01(1 - (vol20 / 0.85)).fillna(0.50)
    drawdown_score = _clip01((dd60 + 0.35) / 0.35).fillna(0.50)

    score10 = (
        trend_score * 2.6
        + momentum_score * 2.6
        + rsi_score * 1.7
        + risk_score * 1.5
        + drawdown_score * 1.6
    )
    confidence = _clip01((score10 - 4.0) / 5.0) * 100

    out["rsi"] = rsi
    out["ma20"] = ma20
    out["ma50"] = ma50
    out["score_proxy"] = score10.clip(0, 10)
    out["confidence_proxy"] = confidence.clip(0, 100)
    return out


# -------------------------------------------------------------------
# Simulering
# -------------------------------------------------------------------
def _max_drawdown_pct(values: pd.Series) -> float:
    if values is None or values.empty:
        return 0.0
    peak = values.cummax()
    dd = values / peak - 1
    return float(dd.min() * 100)


def simulate_one_ticker(df: pd.DataFrame, rules: RuleSet, start_cash: float = 100_000.0) -> Dict[str, object]:
    if df is None or df.empty or "Close" not in df:
        return {"equity": pd.DataFrame(columns=["date", "value"]), "trades": [], "stats": {}}

    data = add_historical_score_proxy(df).dropna(subset=["Close"]).copy()
    if len(data) < 35:
        return {"equity": pd.DataFrame(columns=["date", "value"]), "trades": [], "stats": {}}

    cash = float(start_cash)
    shares = 0.0
    entry = 0.0
    peak_price = 0.0
    trades: List[Dict[str, object]] = []
    equity_rows: List[Tuple[pd.Timestamp, float]] = []
    buys_by_day: Dict[str, int] = {}

    for date, row in data.iterrows():
        price = float(row["Close"])
        rsi = float(row.get("rsi", 50))
        score = float(row.get("score_proxy", 0))
        conf = float(row.get("confidence_proxy", 0))
        ma20 = row.get("ma20")
        day_key = pd.Timestamp(date).date().isoformat()

        market_value = shares * price
        total_value = cash + market_value
        equity_rows.append((date, total_value))

        has_position = shares > 0
        buy_count_today = buys_by_day.get(day_key, 0)
        buy_signal = (
            not has_position
            and buy_count_today < max(1, int(rules.max_trades_per_day))
            and score >= rules.min_buy_score
            and conf >= rules.min_buy_confidence
            and rsi <= rules.max_buy_rsi
            and pd.notna(ma20)
            and price >= float(ma20)
        )

        if buy_signal:
            budget = cash * max(0.01, min(1.0, rules.position_size_pct / 100.0))
            new_shares = budget / price if price > 0 else 0
            if new_shares > 0:
                cash -= new_shares * price
                shares += new_shares
                entry = price
                peak_price = price
                buys_by_day[day_key] = buy_count_today + 1
                trades.append({"date": date, "type": "BUY", "price": price, "score": score, "confidence": conf, "rsi": rsi})
            continue

        # V12: exit/salg begrenses aldri av maks kjøp per dag.
        if has_position:
            peak_price = max(peak_price, price)
            pnl_pct = ((price / entry) - 1) * 100 if entry else 0
            trail_pct = ((price / peak_price) - 1) * 100 if peak_price else 0
            sell_reason = None
            if pnl_pct <= -abs(rules.stop_loss_pct):
                sell_reason = "Stop-loss"
            elif pnl_pct >= abs(rules.take_profit_pct):
                sell_reason = "Take-profit"
            elif trail_pct <= -abs(rules.trailing_stop_pct):
                sell_reason = "Trailing stop"
            elif rsi >= rules.rsi_exit_level:
                sell_reason = "RSI exit"
            elif pd.notna(ma20) and price < float(ma20) and score < rules.min_buy_score - 0.7:
                sell_reason = "Trend/score exit"

            if sell_reason:
                cash += shares * price
                trades.append({"date": date, "type": "SELL", "price": price, "pnl_pct": pnl_pct, "reason": sell_reason, "rsi": rsi})
                shares = 0.0
                entry = 0.0
                peak_price = 0.0

    last_date = data.index[-1]
    last_price = float(data["Close"].iloc[-1])
    final_value = cash + shares * last_price
    if equity_rows:
        equity_rows[-1] = (last_date, final_value)
    equity = pd.DataFrame(equity_rows, columns=["date", "value"])

    sells = [t for t in trades if t.get("type") == "SELL"]
    wins = [t for t in sells if float(t.get("pnl_pct", 0)) > 0]
    buy_hold = ((last_price / float(data["Close"].iloc[0])) - 1) * 100 if float(data["Close"].iloc[0]) else 0
    stats = {
        "total_return_pct": ((final_value / start_cash) - 1) * 100 if start_cash else 0,
        "buy_hold_return_pct": buy_hold,
        "max_drawdown_pct": _max_drawdown_pct(equity["value"]),
        "trades": len(trades),
        "buys": len([t for t in trades if t.get("type") == "BUY"]),
        "closed_trades": len(sells),
        "win_rate_pct": (len(wins) / len(sells) * 100) if sells else 0,
        "final_value": final_value,
    }
    return {"equity": equity, "trades": trades, "stats": stats}


def combine_ticker_results(results: Dict[str, Dict[str, object]], start_cash_total: float) -> Tuple[pd.DataFrame, pd.DataFrame]:
    per_rows = []
    equity_parts = []
    for ticker, res in results.items():
        stats = dict(res.get("stats", {}) or {})
        if not stats:
            continue
        stats["ticker"] = ticker
        per_rows.append(stats)
        equity = res.get("equity")
        if isinstance(equity, pd.DataFrame) and not equity.empty:
            part = equity[["date", "value"]].copy()
            part["ticker"] = ticker
            equity_parts.append(part)

    per_df = pd.DataFrame(per_rows)
    if not equity_parts:
        return pd.DataFrame(columns=["date", "value"]), per_df

    merged = pd.concat(equity_parts, ignore_index=True)
    portfolio = merged.groupby("date", as_index=False)["value"].sum().sort_values("date")
    if not portfolio.empty:
        portfolio = portfolio.set_index("date").sort_index().asfreq("D").ffill().dropna().reset_index()
    return portfolio, per_df


def summarize_portfolio(portfolio: pd.DataFrame, per_df: pd.DataFrame, start_cash_total: float) -> Dict[str, float]:
    if portfolio is None or portfolio.empty or start_cash_total <= 0:
        return {"total_return_pct": 0, "max_drawdown_pct": 0, "trades": 0, "win_rate_pct": 0, "vs_buy_hold_pct": 0}
    vals = portfolio["value"].astype(float)
    total_ret = (vals.iloc[-1] / start_cash_total - 1) * 100
    dd = _max_drawdown_pct(vals)
    trades = int(per_df["trades"].sum()) if "trades" in per_df else 0
    buys = int(per_df["buys"].sum()) if "buys" in per_df else 0
    closed = float(per_df["closed_trades"].sum()) if "closed_trades" in per_df else 0
    win_rate = float(per_df["win_rate_pct"].mean()) if "win_rate_pct" in per_df and not per_df.empty else 0
    buy_hold = float(per_df["buy_hold_return_pct"].mean()) if "buy_hold_return_pct" in per_df and not per_df.empty else 0
    return {
        "total_return_pct": total_ret,
        "max_drawdown_pct": dd,
        "trades": trades,
        "buys": buys,
        "closed_trades": closed,
        "win_rate_pct": win_rate,
        "buy_hold_return_pct": buy_hold,
        "vs_buy_hold_pct": total_ret - buy_hold,
        "final_value": float(vals.iloc[-1]),
    }


def run_group_backtest(histories: Dict[str, pd.DataFrame], rules: RuleSet, start_cash: float = 100_000.0) -> Dict[str, object]:
    clean = {t: df for t, df in histories.items() if isinstance(df, pd.DataFrame) and not df.empty}
    if not clean:
        return {"portfolio": pd.DataFrame(), "per_ticker": pd.DataFrame(), "summary": {}, "raw": {}}
    per_cash = start_cash / max(len(clean), 1)
    raw = {ticker: simulate_one_ticker(df, rules, start_cash=per_cash) for ticker, df in clean.items()}
    portfolio, per_df = combine_ticker_results(raw, start_cash)
    summary = summarize_portfolio(portfolio, per_df, start_cash)
    return {"portfolio": portfolio, "per_ticker": per_df, "summary": summary, "raw": raw}


# -------------------------------------------------------------------
# Validering mot falsk beste strategi / overtilpasning
# -------------------------------------------------------------------
def _validation_train_share_pct(method: str, selected_pct: int) -> int:
    if method.startswith("70/30"):
        return 70
    if method.startswith("80/20"):
        return 80
    try:
        return int(selected_pct)
    except Exception:
        return 70


def split_histories_in_out(histories: Dict[str, pd.DataFrame], train_pct: int) -> Tuple[Dict[str, pd.DataFrame], Dict[str, pd.DataFrame], Dict[str, str]]:
    """Splitter hver ticker kronologisk: første del = in-sample, siste del = out-of-sample."""
    train: Dict[str, pd.DataFrame] = {}
    validate: Dict[str, pd.DataFrame] = {}
    meta: Dict[str, str] = {}
    share = max(0.50, min(0.90, float(train_pct) / 100.0))
    for ticker, df in histories.items():
        if not isinstance(df, pd.DataFrame) or df.empty:
            continue
        clean = df.sort_index().dropna(subset=["Close"]) if "Close" in df.columns else df.sort_index()
        n = len(clean)
        if n < 60:
            train[ticker] = clean
            meta[ticker] = "For lite historikk til robust split - hele serien brukt som in-sample."
            continue
        split_idx = int(n * share)
        split_idx = max(35, min(split_idx, n - 20))
        tr = clean.iloc[:split_idx].copy()
        va = clean.iloc[split_idx:].copy()
        if not tr.empty:
            train[ticker] = tr
        if not va.empty:
            validate[ticker] = va
        meta[ticker] = f"{tr.index[0].date()} -> {tr.index[-1].date()} / {va.index[0].date()} -> {va.index[-1].date()}" if not tr.empty and not va.empty else "Split ga ikke nok data."
    return train, validate, meta


def _summary_row(summary: Dict[str, object], label: str) -> Dict[str, object]:
    summary = summary or {}
    return {
        "Måling": label,
        "Avkastning %": round(float(summary.get("total_return_pct", 0) or 0), 2),
        "Mot buy & hold %": round(float(summary.get("vs_buy_hold_pct", 0) or 0), 2),
        "Max drawdown %": round(float(summary.get("max_drawdown_pct", 0) or 0), 2),
        "Win rate %": round(float(summary.get("win_rate_pct", 0) or 0), 1),
        "Trades": int(summary.get("trades", 0) or 0),
    }


def assess_overfit_risk(in_sample: Dict[str, object], out_sample: Dict[str, object]) -> str:
    """En enkel, forklarbar risikovurdering. Brukes som varsel, ikke fasit."""
    if not out_sample:
        return "Ukjent"
    in_ret = float((in_sample or {}).get("total_return_pct", 0) or 0)
    out_ret = float((out_sample or {}).get("total_return_pct", 0) or 0)
    in_vs = float((in_sample or {}).get("vs_buy_hold_pct", 0) or 0)
    out_vs = float((out_sample or {}).get("vs_buy_hold_pct", 0) or 0)
    in_dd = abs(float((in_sample or {}).get("max_drawdown_pct", 0) or 0))
    out_dd = abs(float((out_sample or {}).get("max_drawdown_pct", 0) or 0))

    if in_ret > 5 and out_ret < 0:
        return "Høy"
    if in_ret > 0 and out_ret < in_ret * 0.35:
        return "Høy"
    if in_vs > 0 and out_vs < -5:
        return "Høy"
    if out_dd > max(15, in_dd * 1.75):
        return "Høy"
    if in_ret > 0 and out_ret < in_ret * 0.70:
        return "Moderat"
    if out_vs < 0 <= in_vs:
        return "Moderat"
    if out_dd > in_dd * 1.25 and out_dd > 8:
        return "Moderat"
    return "Lav"


def _avg_summaries(rows: List[Dict[str, object]]) -> Dict[str, float]:
    if not rows:
        return {"total_return_pct": 0, "vs_buy_hold_pct": 0, "max_drawdown_pct": 0, "win_rate_pct": 0, "trades": 0}
    return {
        "total_return_pct": float(sum(float(r.get("total_return_pct", 0) or 0) for r in rows) / len(rows)),
        "vs_buy_hold_pct": float(sum(float(r.get("vs_buy_hold_pct", 0) or 0) for r in rows) / len(rows)),
        # max drawdown er negativ - bruk verste fold
        "max_drawdown_pct": float(min(float(r.get("max_drawdown_pct", 0) or 0) for r in rows)),
        "win_rate_pct": float(sum(float(r.get("win_rate_pct", 0) or 0) for r in rows) / len(rows)),
        "trades": int(sum(int(r.get("trades", 0) or 0) for r in rows)),
    }


def run_walk_forward_validation(histories: Dict[str, pd.DataFrame], rules: RuleSet, start_cash: float, train_pct: int, folds: int = 3) -> Dict[str, object]:
    """Rullerende validering av låste regler.

    For å holde appen rask gjenoptimaliseres ikke reglene i hver fold i denne versjonen.
    Reglene er allerede valgt/optimalisert på in-sample før denne kontrollen kjøres.
    """
    train_summaries: List[Dict[str, object]] = []
    out_summaries: List[Dict[str, object]] = []
    fold_rows: List[Dict[str, object]] = []
    share = max(0.50, min(0.90, float(train_pct) / 100.0))

    for fold in range(max(1, int(folds))):
        tr: Dict[str, pd.DataFrame] = {}
        va: Dict[str, pd.DataFrame] = {}
        for ticker, df in histories.items():
            if not isinstance(df, pd.DataFrame) or df.empty or "Close" not in df.columns:
                continue
            clean = df.sort_index().dropna(subset=["Close"])
            n = len(clean)
            if n < 90:
                continue
            initial_end = int(n * share)
            remaining = n - initial_end
            if remaining < 20:
                continue
            fold_size = max(10, remaining // max(1, folds))
            val_start = initial_end + fold * fold_size
            val_end = n if fold == folds - 1 else min(n, val_start + fold_size)
            if val_start >= n or val_end <= val_start:
                continue
            train_end = val_start
            tr[ticker] = clean.iloc[:train_end].copy()
            va[ticker] = clean.iloc[val_start:val_end].copy()
        if not tr or not va:
            continue
        tr_res = run_group_backtest(tr, rules, start_cash=start_cash)
        va_res = run_group_backtest(va, rules, start_cash=start_cash)
        tr_sum = dict(tr_res.get("summary", {}) or {})
        va_sum = dict(va_res.get("summary", {}) or {})
        train_summaries.append(tr_sum)
        out_summaries.append(va_sum)
        fold_rows.append({
            "Fold": fold + 1,
            "In-sample avkastning %": round(float(tr_sum.get("total_return_pct", 0) or 0), 2),
            "Out-of-sample avkastning %": round(float(va_sum.get("total_return_pct", 0) or 0), 2),
            "Out-of-sample mot B&H %": round(float(va_sum.get("vs_buy_hold_pct", 0) or 0), 2),
            "Out-of-sample drawdown %": round(float(va_sum.get("max_drawdown_pct", 0) or 0), 2),
            "Trades": int(va_sum.get("trades", 0) or 0),
        })

    in_avg = _avg_summaries(train_summaries)
    out_avg = _avg_summaries(out_summaries)
    return {
        "method": "Walk-forward test",
        "train_pct": int(train_pct),
        "mode": "rolling_locked_rules",
        "fold_rows": fold_rows,
        "in_sample_summary": in_avg,
        "out_of_sample_summary": out_avg,
        "overfit_risk": assess_overfit_risk(in_avg, out_avg),
    }


def run_validation_check(histories: Dict[str, pd.DataFrame], rules: RuleSet, start_cash: float, method: str, train_pct: int) -> Dict[str, object]:
    if method == "Ingen validering / hele perioden":
        return {}
    if method == "Walk-forward test":
        return run_walk_forward_validation(histories, rules, start_cash=start_cash, train_pct=train_pct, folds=3)
    train_hist, out_hist, split_meta = split_histories_in_out(histories, train_pct)
    train_result = run_group_backtest(train_hist, rules, start_cash=start_cash) if train_hist else {"summary": {}}
    out_result = run_group_backtest(out_hist, rules, start_cash=start_cash) if out_hist else {"summary": {}}
    in_summary = dict(train_result.get("summary", {}) or {})
    out_summary = dict(out_result.get("summary", {}) or {})
    return {
        "method": method,
        "train_pct": int(train_pct),
        "split_meta": split_meta,
        "in_sample_summary": in_summary,
        "out_of_sample_summary": out_summary,
        "overfit_risk": assess_overfit_risk(in_summary, out_summary),
    }


# -------------------------------------------------------------------
# Intervaller, kombinasjonsvern og optimalisering
# -------------------------------------------------------------------
def _unique_sorted(values, cast=float):
    out = []
    for v in values:
        try:
            cv = cast(v)
            if cv not in out:
                out.append(cv)
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)
    return sorted(out)


def preset_ranges(base: RuleSet, preset: str) -> Dict[str, List[float]]:
    if preset == "Rask test":
        return {
            "min_buy_score": [7.0, 7.5, 8.0],
            "min_buy_confidence": [60, 70, 80],
            "max_buy_rsi": [55, 65, 75],
            "stop_loss_pct": [2, 5],
            "take_profit_pct": [5, 10],
            "trailing_stop_pct": [0, 5, 8],
            "rsi_exit_level": [70, 80],
            "position_size_pct": [5, 10],
            "max_trades_per_day": [1, 3, 5],
        }
    if preset == "Kraftig grovtest":
        return {
            "min_buy_score": [6.5, 7.0, 7.5, 8.0, 8.5],
            "min_buy_confidence": [55, 65, 70, 75, 85],
            "max_buy_rsi": [50, 55, 60, 65, 70, 75],
            "stop_loss_pct": [1.5, 2, 3, 5, 8],
            "take_profit_pct": [2, 3, 5, 8, 12, 15],
            "trailing_stop_pct": [0, 3, 5, 8, 12],
            "rsi_exit_level": [65, 70, 75, 80, 85],
            "position_size_pct": [5, 10, 15],
            "max_trades_per_day": [1, 3, 5],
        }
    # Standard test - balansert, men capper faktisk kjøring dersom for stort.
    return {
        "min_buy_score": [6.5, 7.0, 7.5, 8.0, 8.5],
        "min_buy_confidence": [55, 65, 75, 85],
        "max_buy_rsi": [55, 65, 72, 80],
        "stop_loss_pct": [2, 5, 8],
        "take_profit_pct": [3, 8, 12, 15],
        "trailing_stop_pct": [0, 5, 8, 12],
        "rsi_exit_level": [70, 75, 80, 85],
        "position_size_pct": [5, 10, 15],
        "max_trades_per_day": [1, 3, 5],
    }


def parse_values(raw: str, default: List[float], cast=float) -> List[float]:
    text = str(raw or "").replace(";", ",")
    vals = [x.strip().replace("%", "") for x in text.split(",") if x.strip()]
    parsed = _unique_sorted(vals, cast=cast)
    return parsed if parsed else default


def count_combinations(ranges: Dict[str, List[float]]) -> int:
    total = 1
    for vals in ranges.values():
        total *= max(1, len(vals))
    return int(total)


def rules_from_ranges(ranges: Dict[str, List[float]], base: RuleSet, max_combinations: int = 20_000) -> List[RuleSet]:
    keys = [
        "min_buy_score", "min_buy_confidence", "max_buy_rsi", "stop_loss_pct", "take_profit_pct",
        "trailing_stop_pct", "rsi_exit_level", "position_size_pct", "max_trades_per_day"
    ]
    values = [ranges.get(k, [getattr(base, k)]) for k in keys]
    total = count_combinations({k: list(v) for k, v in zip(keys, values)})
    step = max(1, math.ceil(total / max(1, int(max_combinations))))
    out: List[RuleSet] = []
    for i, combo in enumerate(itertools.product(*values)):
        if i % step != 0:
            continue
        kwargs = dict(zip(keys, combo))
        out.append(RuleSet(
            min_buy_score=float(kwargs["min_buy_score"]),
            min_buy_confidence=int(kwargs["min_buy_confidence"]),
            max_buy_rsi=int(kwargs["max_buy_rsi"]),
            stop_loss_pct=float(kwargs["stop_loss_pct"]),
            take_profit_pct=float(kwargs["take_profit_pct"]),
            trailing_stop_pct=float(kwargs["trailing_stop_pct"]),
            rsi_exit_level=int(kwargs["rsi_exit_level"]),
            position_size_pct=float(kwargs["position_size_pct"]),
            max_open_positions=base.max_open_positions,
            max_trades_per_day=int(kwargs["max_trades_per_day"]),
        ))
    return out


def strategy_rank_score(summary: Dict[str, float]) -> float:
    # Drawdown er negativ, derfor legger vi den til med positiv koeffisient for å straffe dype fall.
    ret = float(summary.get("total_return_pct", 0))
    excess = float(summary.get("vs_buy_hold_pct", 0))
    dd = float(summary.get("max_drawdown_pct", 0))
    win = float(summary.get("win_rate_pct", 0))
    trades = float(summary.get("trades", 0))
    trade_penalty = max(0, trades - 120) * 0.03
    return ret + excess * 0.35 + dd * 0.50 + win * 0.05 - trade_penalty


def optimize_rule_sets(
    histories: Dict[str, pd.DataFrame],
    candidates: List[RuleSet],
    start_cash: float = 100_000.0,
    phase_label: str = "Test",
    ticker_count: int | None = None,
    cancel_key: str | None = None,
) -> pd.DataFrame:
    """Tester regelsett med synlig fremdrift.

    V14.5 / Oppgave 42 og 48:
    - viser ferdige kombinasjoner og prosent
    - viser fase
    - støtter en enkel avbryt-flaggsjekk via session_state
    """
    rows = []
    errors = []
    total = max(1, len(candidates))
    tickers_n = int(ticker_count or len(histories) or 1)
    status_box = st.empty()
    progress = st.progress(0.0)

    def _render_progress(done: int) -> None:
        pct = min(100.0, max(0.0, (done / total) * 100.0))
        status_box.markdown(
            f"""
            <div class="strategy-progress-box">
                <b>Strategi-test fremdrift</b><br>
                Fase: <b>{html.escape(str(phase_label))}</b> · 
                Ferdig: <b>{done:,}</b> / <b>{total:,}</b> kombinasjoner 
                ({pct:.1f} %) · Tickere: <b>{tickers_n}</b>
            </div>
            """.replace(",", " "),
            unsafe_allow_html=True,
        )
        progress.progress(min(1.0, done / total))

    _render_progress(0)
    for i, rules in enumerate(candidates):
        if cancel_key and bool(st.session_state.get(cancel_key, False)):
            st.warning(f"Testen ble avbrutt etter {len(rows)} av {total} kombinasjoner.")
            break
        try:
            result = run_group_backtest(histories, rules, start_cash=start_cash)
        except Exception as e:
            errors.append(str(e))
            if len(errors) <= 3:
                st.warning(f"Hoppet over en regelkombinasjon som feilet i {phase_label}: {e}")
            continue
        s = result.get("summary", {}) or {}
        row = rules.to_row()
        row.update({
            "Avkastning %": round(float(s.get("total_return_pct", 0)), 2),
            "Mot buy&hold %": round(float(s.get("vs_buy_hold_pct", 0)), 2),
            "Max drawdown %": round(float(s.get("max_drawdown_pct", 0)), 2),
            "Trades": int(s.get("trades", 0) or 0),
            "Kjøp": int(s.get("buys", 0) or 0),
            "Win rate %": round(float(s.get("win_rate_pct", 0)), 1),
            "Strategi-score": round(strategy_rank_score(s), 2),
        })
        rows.append(row)
        done = i + 1
        if done == 1 or done % 10 == 0 or done == total:
            _render_progress(done)

    if rows:
        _render_progress(len(rows))
    progress.empty()
    if errors:
        st.warning(f"{len(errors)} regelkombinasjoner feilet og ble hoppet over. Testen fortsatte med resten.")
    # Behold siste statusboks synlig, slik at ferdig prosent ikke forsvinner med en gang.
    opt = pd.DataFrame(rows)
    if opt.empty:
        return opt
    return opt.sort_values(["Strategi-score", "Avkastning %"], ascending=False).reset_index(drop=True)


def _finish_strategy_pro_early_v1863ac(holder: Any, progress: Any, message: str, *, ok: bool = False) -> None:
    try:
        _finish_pro_progress(holder, progress, message, ok=ok)
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
    finish_global_busy("Klar", message)


def _rules_from_opt_row(row, base: RuleSet) -> RuleSet:
    return RuleSet(
        min_buy_score=float(row["Min score"]),
        min_buy_confidence=int(row["Min confidence"]),
        max_buy_rsi=int(row["Maks RSI kjøp"]),
        stop_loss_pct=float(row["Stop-loss %"]),
        take_profit_pct=float(row["Take-profit %"]),
        trailing_stop_pct=float(row["Trailing stop %"]),
        rsi_exit_level=int(row["RSI exit"]),
        position_size_pct=float(row["Posisjonsstørrelse %"]),
        max_open_positions=base.max_open_positions,
        max_trades_per_day=int(row.get("Maks kjøp per dag", base.max_trades_per_day)),
    )


def refine_candidates_from_top(top_df: pd.DataFrame, base: RuleSet, max_candidates: int = 12_000) -> List[RuleSet]:
    candidates: Dict[Tuple, RuleSet] = {}
    if top_df is None or top_df.empty:
        return []
    for _, row in top_df.head(30).iterrows():
        seed = _rules_from_opt_row(row, base)
        ranges = {
            "min_buy_score": _unique_sorted([seed.min_buy_score - 0.2, seed.min_buy_score - 0.1, seed.min_buy_score, seed.min_buy_score + 0.1, seed.min_buy_score + 0.2]),
            "min_buy_confidence": _unique_sorted([seed.min_buy_confidence - 5, seed.min_buy_confidence, seed.min_buy_confidence + 5], int),
            "max_buy_rsi": _unique_sorted([seed.max_buy_rsi - 3, seed.max_buy_rsi, seed.max_buy_rsi + 3], int),
            "stop_loss_pct": _unique_sorted([max(0.5, seed.stop_loss_pct - 1), seed.stop_loss_pct, seed.stop_loss_pct + 1]),
            "take_profit_pct": _unique_sorted([max(1, seed.take_profit_pct - 2), seed.take_profit_pct, seed.take_profit_pct + 2]),
            "trailing_stop_pct": _unique_sorted([max(0, seed.trailing_stop_pct - 1), seed.trailing_stop_pct, seed.trailing_stop_pct + 1]),
            "rsi_exit_level": _unique_sorted([seed.rsi_exit_level - 3, seed.rsi_exit_level, seed.rsi_exit_level + 3], int),
            "position_size_pct": _unique_sorted([max(1, seed.position_size_pct - 2), seed.position_size_pct, seed.position_size_pct + 2]),
            "max_trades_per_day": [seed.max_trades_per_day],
        }
        for rules in rules_from_ranges(ranges, seed, max_combinations=450):
            key = tuple(asdict(rules).items())
            candidates[key] = rules
            if len(candidates) >= max_candidates:
                break
        if len(candidates) >= max_candidates:
            break
    return list(candidates.values())


# -------------------------------------------------------------------
# Logg, profiler og PDF
# -------------------------------------------------------------------
def _load_json_list(path: Path) -> List[dict]:
    storage = _storage()
    if storage is not None:
        data = storage.read_json(_storage_key_for_path(path), default=None)
        if isinstance(data, list):
            return [dict(r) for r in data if isinstance(r, dict)]

    # One-time legacy migration from old root file if present locally.
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                rows = data if isinstance(data, list) else []
            if storage is not None and rows:
                storage.write_json(_storage_key_for_path(path), rows[-250:])
            return [dict(r) for r in rows if isinstance(r, dict)]
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
    return []


def _save_json_list(path: Path, rows: List[dict]) -> None:
    rows = [dict(r) for r in rows[-250:] if isinstance(r, dict)]
    storage = _storage()
    if storage is not None:
        try:
            storage.write_json(_storage_key_for_path(path), rows)
            return
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)


def save_strategy_log(payload: dict) -> str:
    rows = _load_json_list(LOG_FILE)
    test_id = datetime.now().strftime("STRAT-%Y%m%d-%H%M%S")
    payload = dict(payload)
    payload.setdefault("test_id", test_id)
    payload.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
    rows.append(payload)
    _save_json_list(LOG_FILE, rows)
    return str(payload["test_id"])


def latest_coarse_log() -> dict | None:
    rows = _load_json_list(LOG_FILE)
    for row in reversed(rows):
        if row.get("phase") == "grovtest" and row.get("top_rows"):
            return row
    return None


def save_strategy_profile(profile: dict) -> None:
    rows = _load_json_list(PROFILE_FILE)
    rows.append(profile)
    _save_json_list(PROFILE_FILE, rows)


def _pdf_escape(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_simple_pdf(lines: List[str], title: str = "Strategi-test Pro rapport") -> bytes:
    """Lager en enkel PDF uten eksterne biblioteker."""
    safe_lines = [str(title), "", *[str(x) for x in lines]]
    y = 800
    commands = ["BT", "/F1 16 Tf", f"50 {y} Td", f"({_pdf_escape(safe_lines[0])}) Tj"]
    commands += ["/F1 10 Tf"]
    y -= 28
    for line in safe_lines[1:60]:
        if y < 55:
            break
        commands.append(f"50 {y} Td")
        commands.append(f"({_pdf_escape(line)}) Tj")
        commands.append(f"-50 {-y} Td")
        y -= 14
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="replace")
    objs = []
    objs.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objs.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    objs.append(b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n")
    objs.append(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
    objs.append(b"5 0 obj << /Length " + str(len(stream)).encode() + b" >> stream\n" + stream + b"\nendstream endobj\n")
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(out))
        out.extend(obj)
    xref = len(out)
    out.extend(f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode())
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(f"trailer << /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(out)


def _normalize_ticker(ticker: str) -> str:
    return str(ticker or "").strip().upper().replace(" ", "")


def _parse_ticker_text(raw: str, fallback: Iterable[str]) -> List[str]:
    """Parser testtickere. Manuell tekst har alltid prioritet over default/fallback.

    V14: leser og normaliserer streng direkte, slik at feltet "Tickere som skal testes"
    faktisk styrer Strategi-test Pro og ikke faller stille tilbake til valgt AAPL.
    """
    raw = str(raw or "")
    parts = raw.replace(";", ",").replace("\n", ",").split(",")
    tickers = [_normalize_ticker(p) for p in parts if _normalize_ticker(p)]
    if not tickers:
        tickers = [_normalize_ticker(t) for t in fallback if _normalize_ticker(t)]
    seen = set()
    out = []
    for t in tickers:
        if t and t not in seen:
            out.append(t)
            seen.add(t)
    return out[:20]


def _rule_from_ui(default_rules: dict) -> RuleSet:
    return RuleSet(
        min_buy_score=float(default_rules.get("min_buy_score", 7.5)),
        min_buy_confidence=int(default_rules.get("min_buy_confidence", 70)),
        max_buy_rsi=int(default_rules.get("max_buy_rsi", 72)),
        stop_loss_pct=float(default_rules.get("stop_loss_pct", 7.0)),
        take_profit_pct=float(default_rules.get("take_profit_pct", 12.0)),
        trailing_stop_pct=float(default_rules.get("trailing_stop_pct", 8.0)),
        rsi_exit_level=int(default_rules.get("rsi_exit_level", 75)),
        position_size_pct=float(default_rules.get("position_size_pct", 10.0)),
        max_open_positions=int(default_rules.get("max_open_positions", 5)),
        max_trades_per_day=int(default_rules.get("max_trades_per_day", 5)),
    )


def _show_combination_status(total: int, candidates: int, tickers: int) -> None:
    full_tests = total * max(1, tickers)
    actual_tests = candidates * max(1, tickers)
    if total > candidates:
        st.warning(
            f"Kombinasjonsvern aktivt: {total:,} mulige kombinasjoner ({full_tests:,} aksje-tester) "
            f"er redusert til {candidates:,} kombinasjoner ({actual_tests:,} aksje-tester).".replace(",", " ")
        )
    else:
        st.info(f"Denne kjøringen tester {candidates:,} kombinasjoner × {tickers} ticker(e).".replace(",", " "))


def render_test_summary_card(
    tickers: List[str],
    period_label: str,
    test_type: str,
    validation_method: str,
    train_pct: int,
    total_est: int,
    candidate_est: int,
    max_combos: int,
) -> None:
    """V14.5 / Oppgave 47: tydelig sammendrag før kjøring."""
    tickers_txt = ", ".join(tickers[:8]) + (" ..." if len(tickers) > 8 else "") if tickers else "Ingen"
    validation_txt = validation_method
    if validation_method != "Ingen validering / hele perioden":
        validation_txt += f" · treningsandel {train_pct}%"
    capped_txt = "Ja" if total_est > candidate_est else "Nei"
    st.markdown(
        f"""
        <div class="strategy-summary-card">
            <b>Test-sammendrag før kjøring</b><br>
            Tickere: <b>{html.escape(tickers_txt)}</b> · Tidshorisont: <b>{html.escape(period_label)}</b><br>
            Test-type: <b>{html.escape(test_type)}</b> · Validering: <b>{html.escape(validation_txt)}</b><br>
            Kombinasjoner: <b>{candidate_est:,}</b> av <b>{total_est:,}</b> mulig · Maksgrense: <b>{int(max_combos):,}</b> · Begrenset: <b>{capped_txt}</b><br>
            Logg/PDF: resultat lagres etter kjøring, og PDF kan lastes ned fra resultatdelen.
        </div>
        """.replace(",", " "),
        unsafe_allow_html=True,
    )


def data_quality_warnings(histories: Dict[str, pd.DataFrame], requested_tickers: List[str]) -> List[str]:
    """V14.5 / Oppgave 46: enkle datakvalitetsvarsler før resultat tolkes."""
    warnings: List[str] = []
    missing = [t for t in requested_tickers if t not in histories]
    if missing:
        warnings.append("Mangler historikk for: " + ", ".join(missing))
    for ticker, df in histories.items():
        if not isinstance(df, pd.DataFrame) or df.empty:
            warnings.append(f"{ticker}: ingen brukbare historiske rader.")
            continue
        n = len(df)
        if n < 90:
            warnings.append(f"{ticker}: bare {n} historiske datapunkter. Strategi-testen kan være svak.")
        elif n < 180:
            warnings.append(f"{ticker}: relativt kort historikk ({n} datapunkter). Vurder lengre periode for robuste tester.")
        if "Close" not in df.columns or df["Close"].dropna().empty:
            warnings.append(f"{ticker}: mangler sluttkurs/Close-data.")
        try:
            last_date = pd.to_datetime(df.index[-1]).date()
            days_old = (datetime.now().date() - last_date).days
            if days_old > 10:
                warnings.append(f"{ticker}: siste datapunkt er {last_date} ({days_old} dager gammelt).")
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)
        if "Volume" in df.columns:
            try:
                nonzero_share = float((df["Volume"].fillna(0) > 0).mean())
                if nonzero_share < 0.30:
                    warnings.append(f"{ticker}: volumdata virker mangelfullt. Volum-baserte signaler kan bli svake.")
            except Exception as e:
                logging.warning("Silenced exception restored in v18.6.3: %s", e)
    return warnings


def show_data_quality_box(histories: Dict[str, pd.DataFrame], requested_tickers: List[str]) -> None:
    warnings = data_quality_warnings(histories, requested_tickers)
    if warnings:
        with st.expander("⚠️ Datakvalitetsvarsler", expanded=True):
            for msg in warnings[:12]:
                st.warning(msg)
            if len(warnings) > 12:
                st.caption(f"+ {len(warnings) - 12} flere varsler skjult.")
    else:
        st.success("Datakvalitet: OK for valgte tickere og periode.")


def render_strategy_test_pro(default_ticker: str, default_tickers: Iterable[str], default_rules: dict, key_prefix: str = "strategy_pro") -> None:
    """Streamlit UI for Strategi-test Pro."""
    st.markdown(
        """
        <style>
        .strategy-summary-card, .strategy-progress-box {
            background: rgba(15,23,42,0.88);
            border: 1px solid rgba(56,189,248,0.32);
            border-radius: 12px;
            padding: 9px 12px;
            margin: 8px 0;
            color: #dbeafe !important;
            font-size: 0.86rem;
            line-height: 1.45;
        }
        .strategy-progress-box {
            border-color: rgba(34,197,94,0.36);
            background: rgba(5,46,22,0.30);
        }
        .strategy-confirm-card {
            background: rgba(245,158,11,0.10);
            border: 1px solid rgba(245,158,11,0.40);
            border-radius: 12px;
            padding: 9px 12px;
            margin: 8px 0;
            color: #fde68a !important;
            font-size: 0.84rem;
            line-height: 1.4;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    default_list = list(default_tickers or [])
    if default_ticker and default_ticker not in default_list:
        default_list.insert(0, default_ticker)

    base_from_rules = _rule_from_ui(default_rules)

    with st.expander("🧪 Strategi-test Pro / optimalisering", expanded=False):
        st.caption(
            "Test én eller flere tickere mot trading-reglene og historisk teknisk score-proxy. "
            "Dette er simulering, ikke investeringsråd eller ordreutførelse."
        )

        c1, c2, c3 = st.columns([2.0, 1.05, 1.15])
        with c1:
            raw_tickers = st.text_area(
                "Tickere som skal testes",
                value=", ".join(default_list[:6]) if default_list else str(default_ticker or "AAPL"),
                height=64,
                key=f"{key_prefix}_tickers",
            )
            st.caption("Bruk komma. Eksempel: AAPL, MSFT, NVDA, EQNR.OL, VOLV-B.ST")
        with c2:
            period_label = st.selectbox(
                "Tidshorisont bakover",
                list(PERIOD_MAP.keys()),
                index=2,
                key=f"{key_prefix}_period",
            )
            start_cash = st.number_input(
                "Startkapital",
                min_value=10_000,
                max_value=10_000_000,
                value=int(float(default_rules.get("start_cash", 100_000))),
                step=10_000,
                key=f"{key_prefix}_cash",
            )
        with c3:
            # V14.3 hotfix / Oppgave 40:
            # Vis alle testvalg tydelig. Tidligere så det ut som bare "Gjeldende regler" fantes,
            # selv om mer funksjonalitet lå under. Radio-listen gjør valgene synlige uten å
            # endre logg/PDF-formatet eller selve testmotoren.
            test_type = st.radio(
                "Test-type",
                TEST_TYPE_OPTIONS,
                index=0,
                key=f"{key_prefix}_test_type",
            )
            st.caption(TEST_TYPE_HELP.get(test_type, ""))
            max_combos = st.selectbox(
                "Maks kombinasjoner",
                [500, 2_000, 5_000, 10_000, 20_000, 50_000],
                index=3,
                key=f"{key_prefix}_max_combos",
            )
            effective_max_combos = int(max_combos)
            if test_type == "Kraftig smart-test" and effective_max_combos > MAX_SMART_STAGE_COMBINATIONS:
                effective_max_combos = MAX_SMART_STAGE_COMBINATIONS
                st.info(
                    f"Kraftig smart-test bruker maks {MAX_SMART_STAGE_COMBINATIONS:,} kombinasjoner per fase "
                    "for at appen ikke skal fryse. Velg Standard test for bredere manuell kjøring."
                )
            validation_method = st.selectbox(
                "Valideringsmetode",
                VALIDATION_METHOD_OPTIONS,
                index=0,
                key=f"{key_prefix}_validation_method",
            )
            default_train_idx = 1
            if validation_method.startswith("80/20"):
                default_train_idx = 2
            elif validation_method == "Walk-forward test":
                default_train_idx = 1
            training_share_choice = st.selectbox(
                "Treningsandel",
                TRAINING_SHARE_OPTIONS,
                index=default_train_idx,
                key=f"{key_prefix}_training_share",
            )
            applied_train_share = _validation_train_share_pct(validation_method, int(training_share_choice))
            st.caption(VALIDATION_HELP.get(validation_method, ""))

        # Hovedregel for gjeldende test
        with st.expander("Juster gjeldende regler", expanded=False):
            r1, r2, r3, r4 = st.columns(4)
            with r1:
                min_score = st.slider("Min BUY score", 4.0, 10.0, float(default_rules.get("min_buy_score", 7.5)), 0.1, key=f"{key_prefix}_min_score")
                stop_loss = st.slider("Stop-loss %", 0.5, 30.0, float(default_rules.get("stop_loss_pct", 7.0)), 0.5, key=f"{key_prefix}_sl")
            with r2:
                min_conf = st.slider("Min BUY confidence", 40, 95, int(default_rules.get("min_buy_confidence", 70)), 1, key=f"{key_prefix}_min_conf")
                take_profit = st.slider("Take-profit %", 1.0, 80.0, float(default_rules.get("take_profit_pct", 12.0)), 0.5, key=f"{key_prefix}_tp")
            with r3:
                max_rsi = st.slider("Maks RSI for kjøp", 40, 90, int(default_rules.get("max_buy_rsi", 72)), 1, key=f"{key_prefix}_max_rsi")
                trailing = st.slider("Trailing stop %", 0.0, 40.0, float(default_rules.get("trailing_stop_pct", 8.0)), 0.5, key=f"{key_prefix}_trail")
            with r4:
                rsi_exit = st.slider("RSI exit", 55, 95, int(default_rules.get("rsi_exit_level", 75)), 1, key=f"{key_prefix}_rsi_exit")
                pos_size = st.slider("Posisjonsstørrelse %", 1.0, 100.0, float(default_rules.get("position_size_pct", 10.0)), 1.0, key=f"{key_prefix}_pos")
                max_buys = st.slider("Maks kjøp per dag", 1, 10, int(default_rules.get("max_trades_per_day", 3)), 1, key=f"{key_prefix}_max_buys")

        base = RuleSet(
            min_buy_score=float(min_score),
            min_buy_confidence=int(min_conf),
            max_buy_rsi=int(max_rsi),
            stop_loss_pct=float(stop_loss),
            take_profit_pct=float(take_profit),
            trailing_stop_pct=float(trailing),
            rsi_exit_level=int(rsi_exit),
            position_size_pct=float(pos_size),
            max_open_positions=base_from_rules.max_open_positions,
            max_trades_per_day=int(max_buys),
        )

        default_range = preset_ranges(base, "Kraftig grovtest" if test_type == "Kraftig smart-test" else test_type if test_type in {"Rask test", "Standard test"} else "Standard test")
        range_key_suffix = _safe_widget_suffix(test_type)
        with st.expander("Intervaller for test", expanded=test_type in {"Rask test", "Standard test", "Kraftig smart-test", "Egendefinert intervall"}):
            if test_type == "Gjeldende regler":
                st.caption("Intervallfeltene brukes ikke i denne modusen. Velg Rask, Standard, Kraftig eller Egendefinert for optimalisering.")
            elif test_type == "Finjuster siste grovtest":
                st.caption("Intervallfeltene brukes ikke direkte. Programmet henter toppkombinasjoner fra siste lagrede grovtest og lager finere intervaller rundt dem.")
            else:
                st.caption("Bruk komma mellom verdier. Mindre intervaller er kraftige, men kan gi svært mange kombinasjoner.")
            a, b, c = st.columns(3)
            with a:
                v_score = st.text_input("BUY score", ", ".join(map(str, default_range["min_buy_score"])), key=f"{key_prefix}_{range_key_suffix}_range_score")
                v_conf = st.text_input("BUY confidence", ", ".join(map(str, default_range["min_buy_confidence"])), key=f"{key_prefix}_{range_key_suffix}_range_conf")
                v_buy_rsi = st.text_input("Maks RSI kjøp", ", ".join(map(str, default_range["max_buy_rsi"])), key=f"{key_prefix}_{range_key_suffix}_range_buy_rsi")
            with b:
                v_sl = st.text_input("Stop-loss %", ", ".join(map(str, default_range["stop_loss_pct"])), key=f"{key_prefix}_{range_key_suffix}_range_sl")
                v_tp = st.text_input("Take-profit %", ", ".join(map(str, default_range["take_profit_pct"])), key=f"{key_prefix}_{range_key_suffix}_range_tp")
                v_tr = st.text_input("Trailing stop %", ", ".join(map(str, default_range["trailing_stop_pct"])), key=f"{key_prefix}_{range_key_suffix}_range_tr")
            with c:
                v_exit = st.text_input("RSI exit", ", ".join(map(str, default_range["rsi_exit_level"])), key=f"{key_prefix}_{range_key_suffix}_range_exit")
                v_pos = st.text_input("Posisjonsstørrelse %", ", ".join(map(str, default_range["position_size_pct"])), key=f"{key_prefix}_{range_key_suffix}_range_pos")
                v_buys = st.text_input("Maks kjøp per dag", ", ".join(map(str, default_range["max_trades_per_day"])), key=f"{key_prefix}_{range_key_suffix}_range_buys")

        custom_ranges = {
            "min_buy_score": parse_values(v_score, default_range["min_buy_score"]),
            "min_buy_confidence": parse_values(v_conf, default_range["min_buy_confidence"], int),
            "max_buy_rsi": parse_values(v_buy_rsi, default_range["max_buy_rsi"], int),
            "stop_loss_pct": parse_values(v_sl, default_range["stop_loss_pct"]),
            "take_profit_pct": parse_values(v_tp, default_range["take_profit_pct"]),
            "trailing_stop_pct": parse_values(v_tr, default_range["trailing_stop_pct"]),
            "rsi_exit_level": parse_values(v_exit, default_range["rsi_exit_level"], int),
            "position_size_pct": parse_values(v_pos, default_range["position_size_pct"]),
            "max_trades_per_day": parse_values(v_buys, default_range["max_trades_per_day"], int),
        }

        raw_tickers_active = st.session_state.get(f"{key_prefix}_tickers", raw_tickers)
        tickers_preview = _parse_ticker_text(raw_tickers_active, default_list)
        st.caption("Testen vil bruke: " + (", ".join(tickers_preview) if tickers_preview else "ingen tickere valgt"))
        if test_type == "Gjeldende regler":
            total_est = 1
            candidate_est = 1
        elif test_type == "Finjuster siste grovtest":
            last = latest_coarse_log()
            if last and last.get("top_rows"):
                total_est = min(len(last.get("top_rows", [])) * 450, int(effective_max_combos))
                candidate_est = total_est
                st.info(f"Finjustering bruker siste lagrede grovtest: {last.get('test_id', 'ukjent')}")
            else:
                total_est = 0
                candidate_est = 0
                st.warning("Ingen lagret grovtest funnet ennå. Kjør Kraftig smart-test først.")
        else:
            est_ranges = custom_ranges if test_type in {"Egendefinert intervall", "Kraftig smart-test"} else preset_ranges(base, test_type if test_type in {"Rask test", "Standard test"} else "Rask test")
            total_est = count_combinations(est_ranges)
            candidate_est = min(int(effective_max_combos), total_est)
        _show_combination_status(total_est, candidate_est, len(tickers_preview) or 1)
        render_test_summary_card(
            tickers_preview,
            period_label,
            test_type,
            validation_method,
            int(applied_train_share),
            int(total_est),
            int(candidate_est),
            int(effective_max_combos),
        )

        cancel_key = f"{key_prefix}_cancel_requested"
        run_col, cancel_col = st.columns([1.0, 1.0])
        with run_col:
            run_btn = st.button(
                "🧪 Kjør Strategi-test Pro for " + (", ".join(tickers_preview[:3]) if tickers_preview else "valgte tickere"),
                type="primary",
                width="content",
                key=f"{key_prefix}_run",
                on_click=set_global_busy,
                kwargs={"label": "Kjører Strategi-test Pro", "detail": "Forbereder historikk", "step": 1, "total": 4},
            )
        with cancel_col:
            if st.button("⏹️ Avbryt test", width="content", key=f"{key_prefix}_cancel_btn"):
                st.session_state[cancel_key] = True
                st.warning("Avbryt er bedt om. Pågående test stopper ved neste mulige kontrollpunkt.")
        pending_run_key = f"{key_prefix}_run_pending_v18524"
        if run_btn:
            st.session_state[cancel_key] = False
            st.session_state[pending_run_key] = True
            _safe_rerun()

        with st.expander("📚 Strategi-test logg", expanded=False):
            logs = _load_json_list(LOG_FILE)
            if logs:
                log_rows = []
                for row in logs[-10:][::-1]:
                    best = row.get("best_summary", {}) or {}
                    log_rows.append({
                        "Test-ID": row.get("test_id"),
                        "Tid": row.get("created_at"),
                        "Type": row.get("test_type"),
                        "Fase": row.get("phase", "slutt"),
                        "Tickere": ", ".join(row.get("tickers", [])[:5]),
                        "Avkastning %": round(float(best.get("total_return_pct", 0)), 2),
                        "Mot B&H %": round(float(best.get("vs_buy_hold_pct", 0)), 2),
                    })
                st.dataframe(pd.DataFrame(log_rows), width="stretch", hide_index=True)
            else:
                st.caption("Ingen strategi-tester er lagret ennå.")

        run_pending = bool(st.session_state.pop(pending_run_key, False))
        if not run_pending:
            return

        progress_holder = st.empty()
        try:
            progress_bar = st.progress(0.0, text="Starter Strategi-test Pro …")
        except TypeError:
            progress_bar = st.progress(0.0)
        update_global_busy("Kjører Strategi-test Pro", "Henter kursdata for valgte tickere", step=1, total=4)
        _render_pro_progress_step(progress_holder, progress_bar, step=1, total=4, text="Henter kursdata for valgte tickere")

        raw_tickers_active = st.session_state.get(f"{key_prefix}_tickers", raw_tickers)
        tickers = _parse_ticker_text(raw_tickers_active, default_list)
        if not tickers:
            st.warning("Legg inn minst én ticker.")
            _finish_strategy_pro_early_v1863ac(progress_holder, progress_bar, "Strategi-test Pro manglet tickere.")
            return
        if len(tickers) >= 20:
            st.info("Maks 20 tickere testes samtidig i denne versjonen for å holde appen rask.")

        period = PERIOD_MAP.get(period_label, "1y")
        histories = fetch_strategy_histories(tuple(tickers), period)
        update_global_busy("Kjører Strategi-test Pro", "Scorer regelsett og bygger kombinasjoner", step=2, total=4)
        _render_pro_progress_step(progress_holder, progress_bar, step=2, total=4, text="Scorer regelsett og bygger kombinasjoner")

        missing = [t for t in tickers if t not in histories]
        if missing:
            st.warning("Fant ikke nok historikk for: " + ", ".join(missing))
        if not histories:
            st.error("Klarte ikke å hente historikk. Sjekk internett/Yahoo Finance eller ticker-symbolene.")
            _finish_strategy_pro_early_v1863ac(progress_holder, progress_bar, "Strategi-test Pro fant ikke historikk.")
            return
        show_data_quality_box(histories, tickers)

        validation_active = validation_method != "Ingen validering / hele perioden"
        train_histories, out_histories, split_meta = ({}, {}, {})
        optimization_histories = histories
        if validation_active:
            train_histories, out_histories, split_meta = split_histories_in_out(histories, applied_train_share)
            if train_histories:
                optimization_histories = train_histories
            st.info(
                f"Validering aktiv: {validation_method}. Reglene optimaliseres på in-sample "
                f"({applied_train_share} %) og testes låst på out-of-sample."
            )
            if not out_histories and validation_method != "Walk-forward test":
                st.warning("Fant ikke nok out-of-sample-data for alle tickere. Bruk lengre tidshorisont eller lavere treningsandel.")

        opt = pd.DataFrame()
        rules = base
        run_note = ""
        phase = "slutt"
        update_global_busy("Kjører Strategi-test Pro", "Filtrerer risiko, momentum og validering", step=3, total=4)
        _render_pro_progress_step(progress_holder, progress_bar, step=3, total=4, text="Filtrerer risiko, momentum og validering")

        if test_type == "Gjeldende regler":
            st.info("Tester gjeldende regelsett uten optimalisering.")
        elif test_type == "Finjuster siste grovtest":
            last = latest_coarse_log()
            if not last:
                st.warning("Fant ingen lagret grovtest. Kjør Kraftig smart-test først.")
                _finish_strategy_pro_early_v1863ac(progress_holder, progress_bar, "Strategi-test Pro manglet lagret grovtest.")
                return
            top_rows = pd.DataFrame(last.get("top_rows", []))
            candidates = refine_candidates_from_top(top_rows, base, max_candidates=int(effective_max_combos))
            st.info(f"Finjusterer {len(candidates)} kombinasjoner fra siste lagrede grovtest: {last.get('test_id')}")
            opt = optimize_rule_sets(optimization_histories, candidates, start_cash=float(start_cash), phase_label="Finjustering", ticker_count=len(histories), cancel_key=cancel_key)
        elif test_type == "Kraftig smart-test":
            coarse_ranges = custom_ranges
            total = count_combinations(coarse_ranges)
            coarse_candidates = rules_from_ranges(coarse_ranges, base, max_combinations=int(effective_max_combos))
            _show_combination_status(total, len(coarse_candidates), len(histories))
            st.info("Steg 1/2: kjører grovtest og lagrer toppresultater automatisk.")
            coarse = optimize_rule_sets(optimization_histories, coarse_candidates, start_cash=float(start_cash), phase_label="Grovtest", ticker_count=len(histories), cancel_key=cancel_key)
            if coarse.empty:
                st.warning("Grovtesten ga ingen resultater.")
                _finish_strategy_pro_early_v1863ac(progress_holder, progress_bar, "Strategi-test Pro ga ingen grovtest-resultater.")
                return
            coarse_id = save_strategy_log({
                "test_type": test_type,
                "phase": "grovtest",
                "period_label": period_label,
                "tickers": list(histories.keys()),
                "combination_count": int(len(coarse_candidates)),
                "validation_method": validation_method,
                "training_share_pct": int(applied_train_share),
                "split_meta": split_meta,
                "top_rows": coarse.head(50).to_dict(orient="records"),
                "best_summary": {"total_return_pct": float(coarse.iloc[0].get("Avkastning %", 0)), "vs_buy_hold_pct": float(coarse.iloc[0].get("Mot buy&hold %", 0))},
            })
            st.success(f"Grovtest lagret automatisk: {coarse_id}")
            st.info("Steg 2/2: finjusterer rundt beste grovtest-kombinasjoner.")
            refine = refine_candidates_from_top(coarse, base, max_candidates=int(effective_max_combos))
            opt = optimize_rule_sets(optimization_histories, refine, start_cash=float(start_cash), phase_label="Finjustering", ticker_count=len(histories), cancel_key=cancel_key)
            run_note = f"Kraftig smart-test: grovtest {coarse_id} + finjustering."
        else:
            ranges = custom_ranges if test_type == "Egendefinert intervall" else preset_ranges(base, test_type)
            total = count_combinations(ranges)
            candidates = rules_from_ranges(ranges, base, max_combinations=int(effective_max_combos))
            _show_combination_status(total, len(candidates), len(histories))
            opt = optimize_rule_sets(optimization_histories, candidates, start_cash=float(start_cash), phase_label=test_type, ticker_count=len(histories), cancel_key=cancel_key)

        if not opt.empty:
            st.markdown("#### Beste kombinasjoner")
            st.dataframe(opt.head(MAX_DISPLAY_ROWS), width="stretch", hide_index=True)
            best = opt.iloc[0]
            rules = _rules_from_opt_row(best, base)
            st.success("Beste regelsett brukes i grafen under: " + rules.as_label())

        result = run_group_backtest(histories, rules, start_cash=float(start_cash))
        portfolio = result.get("portfolio")
        per_ticker = result.get("per_ticker")
        summary = result.get("summary", {}) or {}
        validation_payload = run_validation_check(histories, rules, float(start_cash), validation_method, int(applied_train_share)) if validation_active else {}
        update_global_busy("Kjører Strategi-test Pro", "Rangerer og lagrer resultat", step=4, total=4)
        _render_pro_progress_step(progress_holder, progress_bar, step=4, total=4, text="Rangerer og lagrer resultat")
        _finish_pro_progress(progress_holder, progress_bar, "ferdig", ok=True)
        finish_global_busy("Klar", "Strategi-test Pro ferdig")

        if validation_payload:
            st.markdown("#### In-sample / out-of-sample-validering")
            val_rows = [
                _summary_row(validation_payload.get("in_sample_summary", {}), "In-sample"),
                _summary_row(validation_payload.get("out_of_sample_summary", {}), "Out-of-sample"),
            ]
            st.dataframe(pd.DataFrame(val_rows), width="stretch", hide_index=True)
            risk = validation_payload.get("overfit_risk", "Ukjent")
            if risk == "Høy":
                st.error("Overfit-risiko: Høy - strategien ser mye svakere ut utenfor treningsperioden.")
            elif risk == "Moderat":
                st.warning("Overfit-risiko: Moderat - vurder lengre periode eller flere tickere.")
            else:
                st.success(f"Overfit-risiko: {risk} - out-of-sample er relativt stabil mot in-sample.")
            if validation_payload.get("fold_rows"):
                with st.expander("Walk-forward detaljer", expanded=False):
                    st.dataframe(pd.DataFrame(validation_payload.get("fold_rows", [])), width="stretch", hide_index=True)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total avkastning", f"{float(summary.get('total_return_pct', 0)):.2f}%")
        m2.metric("Mot buy & hold", f"{float(summary.get('vs_buy_hold_pct', 0)):+.2f}%")
        m3.metric("Max drawdown", f"{float(summary.get('max_drawdown_pct', 0)):.2f}%")
        m4.metric("Trades", int(summary.get("trades", 0) or 0))

        m5, m6, m7 = st.columns(3)
        m5.metric("Win rate", f"{float(summary.get('win_rate_pct', 0)):.1f}%")
        m6.metric("Buy & hold snitt", f"{float(summary.get('buy_hold_return_pct', 0)):.2f}%")
        m7.metric("Sluttverdi", f"{float(summary.get('final_value', 0)):,.0f} kr".replace(",", " "))

        if isinstance(portfolio, pd.DataFrame) and not portfolio.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=portfolio["date"], y=portfolio["value"], mode="lines", name="Strategi Pro"))
            fig.update_layout(
                title="Porteføljeutvikling for valgt regelsett",
                template="plotly_dark",
                height=420,
                paper_bgcolor="#07111f",
                plot_bgcolor="#07111f",
                margin=dict(l=35, r=35, t=55, b=45),
                hovermode="x unified",
                hoverlabel=dict(bgcolor="rgba(15,23,42,0.96)", bordercolor="rgba(148,163,184,0.45)", font=dict(color="#f8fafc")),
            )
            st.plotly_chart(fig, width="stretch", config={"scrollZoom": True, "displaylogo": False})

        if isinstance(per_ticker, pd.DataFrame) and not per_ticker.empty:
            show = per_ticker.copy()
            rename = {
                "ticker": "Ticker",
                "total_return_pct": "Avkastning %",
                "buy_hold_return_pct": "Buy&hold %",
                "max_drawdown_pct": "Max DD %",
                "trades": "Trades",
                "buys": "Kjøp",
                "win_rate_pct": "Win rate %",
                "final_value": "Sluttverdi",
            }
            show = show.rename(columns=rename)
            wanted = [c for c in ["Ticker", "Avkastning %", "Buy&hold %", "Max DD %", "Trades", "Kjøp", "Win rate %", "Sluttverdi"] if c in show.columns]
            st.markdown("#### Resultat per ticker")
            st.dataframe(show[wanted].round(2), width="stretch", hide_index=True)

        top_rows = opt.head(50).to_dict(orient="records") if not opt.empty else []
        test_id = save_strategy_log({
            "test_type": test_type,
            "phase": phase,
            "period_label": period_label,
            "period": period,
            "tickers": list(histories.keys()),
            "start_cash": float(start_cash),
            "rules": asdict(rules),
            "validation_method": validation_method,
            "training_share_pct": int(applied_train_share),
            "split_meta": split_meta,
            "validation": validation_payload,
            "best_summary": {k: float(v) if isinstance(v, (int, float)) else v for k, v in summary.items()},
            "top_rows": top_rows,
            "note": run_note,
        })
        st.success(f"Resultat lagret i strategi-test-logg: {test_id}")

        profile = {
            "name": f"{','.join(list(histories.keys())[:3])} {period_label} {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "tickers": list(histories.keys()),
            "period_label": period_label,
            "rules": asdict(rules),
            "summary": summary,
            "validation_method": validation_method,
            "training_share_pct": int(applied_train_share),
            "validation": validation_payload,
            "source_test_id": test_id,
        }
        st.markdown(
            """
            <div class="strategy-confirm-card">
                <b>Trygg bruk av strategi</b><br>
                Før du lagrer eller bruker en strategi i praksis bør out-of-sample-resultat, drawdown, antall trades og datakvalitet vurderes.
                Historisk best kombinasjon er ikke en garanti for fremtidig resultat.
            </div>
            """,
            unsafe_allow_html=True,
        )
        confirm_profile = st.checkbox(
            "Jeg har vurdert validering/datavarsler og vil lagre dette som strategi-profil",
            key=f"{key_prefix}_confirm_profile",
        )
        if st.button("⭐ Lagre beste strategi som profil", key=f"{key_prefix}_save_profile", disabled=not confirm_profile):
            save_strategy_profile(profile)
            st.success("Strategi-profil lagret ✅")

        pdf_lines = [
            f"Test-ID: {test_id}",
            f"Dato: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            f"Test-type: {test_type}",
            f"Valideringsmetode: {validation_method}",
            f"Treningsandel: {applied_train_share}%" if validation_active else "Treningsandel: ikke brukt",
            f"Overfit-risiko: {validation_payload.get('overfit_risk', 'Ikke beregnet')}" if validation_active else "Overfit-risiko: ikke beregnet",
            f"Tickere: {', '.join(list(histories.keys()))}",
            f"Tidshorisont: {period_label}",
            "",
            "Beste parametere:",
            *[f"- {k}: {v}" for k, v in rules.to_row().items()],
            "",
            "Resultater:",
            f"- Total avkastning: {float(summary.get('total_return_pct', 0)):.2f}%",
            f"- Mot buy & hold: {float(summary.get('vs_buy_hold_pct', 0)):+.2f}%",
            f"- Max drawdown: {float(summary.get('max_drawdown_pct', 0)):.2f}%",
            f"- Win rate: {float(summary.get('win_rate_pct', 0)):.1f}%",
            f"- Trades: {int(summary.get('trades', 0) or 0)}",
        ]
        if validation_payload:
            in_s = validation_payload.get("in_sample_summary", {}) or {}
            out_s = validation_payload.get("out_of_sample_summary", {}) or {}
            pdf_lines += [
                "",
                "Validering:",
                f"- In-sample avkastning: {float(in_s.get('total_return_pct', 0)):.2f}%",
                f"- Out-of-sample avkastning: {float(out_s.get('total_return_pct', 0)):.2f}%",
                f"- Out-of-sample mot buy & hold: {float(out_s.get('vs_buy_hold_pct', 0)):+.2f}%",
                f"- Out-of-sample max drawdown: {float(out_s.get('max_drawdown_pct', 0)):.2f}%",
                f"- Overfit-risiko: {validation_payload.get('overfit_risk', 'Ukjent')}",
            ]
        pdf_lines += [
            "",
            "Merk: historisk simulering/proxy - ingen garanti for fremtidig avkastning.",
        ]
        st.download_button(
            "📄 Last ned PDF-rapport",
            data=make_simple_pdf(pdf_lines),
            file_name=f"strategi_test_{test_id}.pdf",
            mime="application/pdf",
            width="content",
            key=f"{key_prefix}_pdf",
        )

        if not opt.empty:
            st.download_button(
                "⬇️ Last ned beste kombinasjoner CSV",
                data=opt.head(200).to_csv(index=False).encode("utf-8"),
                file_name=f"strategi_test_{test_id}_kombinasjoner.csv",
                mime="text/csv",
                width="content",
                key=f"{key_prefix}_csv",
            )

        st.caption(
            "Historisk score/confidence er en teknisk proxy beregnet uten fremtidsdata. "
            "Resultater kan bli annerledes i live-modellen med nyheter, fundamentale data, spread/slippage og datakvalitet."
        )
