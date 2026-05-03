"""Strategi-test Pro: historisk simulering og enkel regel-optimalisering.

Denne modulen er laget for Streamlit-appen og kjører kun når brukeren trykker på
Kjør-knappen. Den bruker daglige historiske kurser og en teknisk, historisk proxy
for score/confidence, slik at reglene kan testes bakover i tid uten å kalle den
fulle analysemodellen for hver historiske dag.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    import yfinance as yf
except Exception:  # pragma: no cover - appen viser varsel i UI
    yf = None


PERIOD_MAP = {
    "3 måneder": "3mo",
    "6 måneder": "6mo",
    "1 år": "1y",
    "2 år": "2y",
    "5 år": "5y",
    "Maks": "max",
}


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
    max_trades_per_day: int = 5

    def as_label(self) -> str:
        return (
            f"Score≥{self.min_buy_score:.1f}, Conf≥{self.min_buy_confidence}, "
            f"RSI≤{self.max_buy_rsi}, SL {self.stop_loss_pct:.0f}%, TP {self.take_profit_pct:.0f}%"
        )


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
    """Legger på historisk proxy for Top Pick-score og confidence.

    Proxyen bruker bare informasjon som finnes samme dag: trend, momentum, RSI og
    volatilitet. Det er ikke identisk med full dagsanalyse, men gjør det mulig å
    teste regel-kombinasjoner på historiske data uten lookahead.
    """
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

    for date, row in data.iterrows():
        price = float(row["Close"])
        rsi = float(row.get("rsi", 50))
        score = float(row.get("score_proxy", 0))
        conf = float(row.get("confidence_proxy", 0))
        ma20 = row.get("ma20")

        market_value = shares * price
        total_value = cash + market_value
        equity_rows.append((date, total_value))

        has_position = shares > 0
        buy_signal = (
            not has_position
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
                trades.append({"date": date, "type": "BUY", "price": price, "score": score, "confidence": conf, "rsi": rsi})
            continue

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

    # Sluttverdi med åpen posisjon mark-to-market.
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
    # Reindekser daglig og forward-filler, så aksjer med ulik historikk summeres jevnere.
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
    closed = float(per_df["closed_trades"].sum()) if "closed_trades" in per_df else 0
    # Vektet win-rate er komplisert uten hver trade; snitt er oversiktlig nok for UI.
    win_rate = float(per_df["win_rate_pct"].mean()) if "win_rate_pct" in per_df and not per_df.empty else 0
    buy_hold = float(per_df["buy_hold_return_pct"].mean()) if "buy_hold_return_pct" in per_df and not per_df.empty else 0
    return {
        "total_return_pct": total_ret,
        "max_drawdown_pct": dd,
        "trades": trades,
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


def _candidate_rule_sets(base: RuleSet, width: str) -> List[RuleSet]:
    if width == "Liten":
        score_values = sorted({round(base.min_buy_score - 0.3, 1), round(base.min_buy_score, 1), round(base.min_buy_score + 0.3, 1)})
        conf_values = sorted({max(40, base.min_buy_confidence - 5), base.min_buy_confidence, min(95, base.min_buy_confidence + 5)})
        rsi_values = sorted({max(40, base.max_buy_rsi - 5), base.max_buy_rsi, min(90, base.max_buy_rsi + 5)})
    elif width == "Bred":
        score_values = [6.0, 6.5, 7.0, 7.5, 8.0, 8.5]
        conf_values = [55, 65, 75, 85]
        rsi_values = [55, 65, 72, 80]
    else:
        score_values = [6.5, 7.0, 7.5, 8.0]
        conf_values = [60, 70, 80]
        rsi_values = [60, 72, 80]

    out: List[RuleSet] = []
    for score in score_values:
        for conf in conf_values:
            for rsi in rsi_values:
                out.append(RuleSet(
                    min_buy_score=float(score),
                    min_buy_confidence=int(conf),
                    max_buy_rsi=int(rsi),
                    stop_loss_pct=base.stop_loss_pct,
                    take_profit_pct=base.take_profit_pct,
                    trailing_stop_pct=base.trailing_stop_pct,
                    rsi_exit_level=base.rsi_exit_level,
                    position_size_pct=base.position_size_pct,
                    max_open_positions=base.max_open_positions,
                    max_trades_per_day=base.max_trades_per_day,
                ))
    return out


def optimize_rule_sets(histories: Dict[str, pd.DataFrame], base: RuleSet, width: str, start_cash: float = 100_000.0) -> pd.DataFrame:
    rows = []
    for rules in _candidate_rule_sets(base, width):
        result = run_group_backtest(histories, rules, start_cash=start_cash)
        s = result.get("summary", {}) or {}
        rows.append({
            "Min score": rules.min_buy_score,
            "Min confidence": rules.min_buy_confidence,
            "Maks RSI kjøp": rules.max_buy_rsi,
            "Avkastning %": round(float(s.get("total_return_pct", 0)), 2),
            "Mot buy&hold %": round(float(s.get("vs_buy_hold_pct", 0)), 2),
            "Max drawdown %": round(float(s.get("max_drawdown_pct", 0)), 2),
            "Trades": int(s.get("trades", 0) or 0),
            "Win rate %": round(float(s.get("win_rate_pct", 0)), 1),
            "Score": round(float(s.get("total_return_pct", 0)) + float(s.get("vs_buy_hold_pct", 0)) * 0.25 + float(s.get("max_drawdown_pct", 0)) * 0.35, 2),
        })
    opt = pd.DataFrame(rows)
    if opt.empty:
        return opt
    return opt.sort_values(["Score", "Avkastning %"], ascending=False).reset_index(drop=True)


def _parse_ticker_text(raw: str, fallback: Iterable[str]) -> List[str]:
    raw = str(raw or "")
    parts = raw.replace(";", ",").replace("\n", ",").split(",")
    tickers = [p.strip().upper() for p in parts if p.strip()]
    if not tickers:
        tickers = [str(t).strip().upper() for t in fallback if str(t).strip()]
    seen = set()
    out = []
    for t in tickers:
        if t and t not in seen:
            out.append(t)
            seen.add(t)
    return out[:12]


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


def render_strategy_test_pro(default_ticker: str, default_tickers: Iterable[str], default_rules: dict, key_prefix: str = "strategy_pro") -> None:
    """Streamlit UI for Oppgave 10."""
    default_list = list(default_tickers or [])
    if default_ticker and default_ticker not in default_list:
        default_list.insert(0, default_ticker)

    with st.expander("🧪 Strategi-test Pro / optimalisering", expanded=False):
        st.caption(
            "Test én eller flere tickere mot trading-reglene og en historisk teknisk score-proxy. "
            "Dette er simulering, ikke investeringsråd eller ordreutførelse."
        )

        c1, c2, c3 = st.columns([2.1, 1, 1])
        with c1:
            raw_tickers = st.text_area(
                "Tickere som skal testes",
                value=", ".join(default_list[:6]) if default_list else str(default_ticker or "AAPL"),
                height=76,
                help="Bruk komma. Eksempel: AAPL, MSFT, NVDA, EQNR.OL, VOLV-B.ST",
                key=f"{key_prefix}_tickers",
            )
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
            mode = st.radio(
                "Testmodus",
                ["Test gjeldende regler", "Finn beste kombinasjon"],
                index=0,
                key=f"{key_prefix}_mode",
            )
            grid_width = st.selectbox(
                "Søkeområde",
                ["Liten", "Normal", "Bred"],
                index=1,
                disabled=mode != "Finn beste kombinasjon",
                key=f"{key_prefix}_width",
            )

        with st.expander("Juster regler for denne testen", expanded=False):
            r1, r2, r3, r4 = st.columns(4)
            with r1:
                min_score = st.slider("Min BUY score", 4.0, 10.0, float(default_rules.get("min_buy_score", 7.5)), 0.1, key=f"{key_prefix}_min_score")
                stop_loss = st.slider("Stop-loss %", 1.0, 30.0, float(default_rules.get("stop_loss_pct", 7.0)), 0.5, key=f"{key_prefix}_sl")
            with r2:
                min_conf = st.slider("Min BUY confidence", 40, 95, int(default_rules.get("min_buy_confidence", 70)), 1, key=f"{key_prefix}_min_conf")
                take_profit = st.slider("Take-profit %", 1.0, 80.0, float(default_rules.get("take_profit_pct", 12.0)), 0.5, key=f"{key_prefix}_tp")
            with r3:
                max_rsi = st.slider("Maks RSI for kjøp", 40, 90, int(default_rules.get("max_buy_rsi", 72)), 1, key=f"{key_prefix}_max_rsi")
                trailing = st.slider("Trailing stop %", 1.0, 40.0, float(default_rules.get("trailing_stop_pct", 8.0)), 0.5, key=f"{key_prefix}_trail")
            with r4:
                rsi_exit = st.slider("RSI exit", 55, 95, int(default_rules.get("rsi_exit_level", 75)), 1, key=f"{key_prefix}_rsi_exit")
                pos_size = st.slider("Posisjonsstørrelse %", 1.0, 100.0, float(default_rules.get("position_size_pct", 10.0)), 1.0, key=f"{key_prefix}_pos")

        run_btn = st.button("🧪 Kjør Strategi-test Pro", type="primary", use_container_width=True, key=f"{key_prefix}_run")
        if not run_btn:
            return

        tickers = _parse_ticker_text(raw_tickers, default_list)
        if not tickers:
            st.warning("Legg inn minst én ticker.")
            return
        if len(tickers) >= 12:
            st.info("Maks 12 tickere testes samtidig i denne versjonen for å holde appen rask.")

        period = PERIOD_MAP.get(period_label, "1y")
        with st.spinner(f"Henter historikk og tester {len(tickers)} ticker(e)..."):
            histories = fetch_strategy_histories(tuple(tickers), period)

        missing = [t for t in tickers if t not in histories]
        if missing:
            st.warning("Fant ikke nok historikk for: " + ", ".join(missing))
        if not histories:
            st.error("Klarte ikke å hente historikk. Sjekk internett/Yahoo Finance eller ticker-symbolene.")
            return

        rules = RuleSet(
            min_buy_score=float(min_score),
            min_buy_confidence=int(min_conf),
            max_buy_rsi=int(max_rsi),
            stop_loss_pct=float(stop_loss),
            take_profit_pct=float(take_profit),
            trailing_stop_pct=float(trailing),
            rsi_exit_level=int(rsi_exit),
            position_size_pct=float(pos_size),
            max_open_positions=int(default_rules.get("max_open_positions", 5)),
            max_trades_per_day=int(default_rules.get("max_trades_per_day", 5)),
        )

        if mode == "Finn beste kombinasjon":
            opt = optimize_rule_sets(histories, rules, grid_width, start_cash=float(start_cash))
            if opt.empty:
                st.warning("Fant ingen gyldige optimaliseringsresultater.")
                return
            st.markdown("#### Beste kombinasjoner")
            st.dataframe(opt.head(20), use_container_width=True, hide_index=True)
            best = opt.iloc[0]
            rules = RuleSet(
                min_buy_score=float(best["Min score"]),
                min_buy_confidence=int(best["Min confidence"]),
                max_buy_rsi=int(best["Maks RSI kjøp"]),
                stop_loss_pct=float(stop_loss),
                take_profit_pct=float(take_profit),
                trailing_stop_pct=float(trailing),
                rsi_exit_level=int(rsi_exit),
                position_size_pct=float(pos_size),
                max_open_positions=int(default_rules.get("max_open_positions", 5)),
                max_trades_per_day=int(default_rules.get("max_trades_per_day", 5)),
            )
            st.success("Beste regelsett brukes i grafen under: " + rules.as_label())

        result = run_group_backtest(histories, rules, start_cash=float(start_cash))
        portfolio = result.get("portfolio")
        per_ticker = result.get("per_ticker")
        summary = result.get("summary", {}) or {}

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
            )
            st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True, "displaylogo": False})

        if isinstance(per_ticker, pd.DataFrame) and not per_ticker.empty:
            show = per_ticker.copy()
            rename = {
                "ticker": "Ticker",
                "total_return_pct": "Avkastning %",
                "buy_hold_return_pct": "Buy&hold %",
                "max_drawdown_pct": "Max DD %",
                "trades": "Trades",
                "win_rate_pct": "Win rate %",
                "final_value": "Sluttverdi",
            }
            show = show.rename(columns=rename)
            wanted = [c for c in ["Ticker", "Avkastning %", "Buy&hold %", "Max DD %", "Trades", "Win rate %", "Sluttverdi"] if c in show.columns]
            st.markdown("#### Resultat per ticker")
            st.dataframe(show[wanted].round(2), use_container_width=True, hide_index=True)

        st.caption(
            "Merk: historisk score/confidence er en teknisk proxy beregnet uten fremtidsdata. "
            "Resultater kan bli annerledes i live-modellen med nyheter, fundamentale data og faktisk spread/slippage."
        )
