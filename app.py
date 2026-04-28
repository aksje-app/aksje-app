import streamlit as st
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

from stocks import get_sp500_tickers, get_norwegian_tickers
from analysis import rank_stocks
from backtest_strategy import run_monthly_score_strategy, add_stats
from ipo import get_ipo_calendar

st.set_page_config(page_title="AI Aksje Analyzer Pro", page_icon="📈", layout="wide")
st_autorefresh(interval=300000, key="refresh")

st.markdown("""
<style>
.stApp { background: #0b111c; color: #e8eefc; }
[data-testid="stSidebar"] { background: #111827; }
div[data-testid="stMetric"] { background: #121a2a; border: 1px solid #24324a; padding: 14px; border-radius: 14px; }
.card { background: #111827; border: 1px solid #24324a; border-radius: 16px; padding: 14px; margin-bottom: 10px; }
.small { color: #9aa8c7; font-size: 0.9rem; }
.good { color: #00e396; font-weight: 700; }
.mid { color: #f5b041; font-weight: 700; }
.bad { color: #ff4d6d; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

def score_color(score):
    if score >= 7: return "good", "🟢"
    if score >= 4: return "mid", "🟡"
    return "bad", "🔴"

def plot_price(hist, title):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist.index, y=hist["Close"], mode="lines", name="Close"))
    fig.update_layout(title=title, template="plotly_dark", height=420, paper_bgcolor="#0b111c", plot_bgcolor="#0b111c")
    return fig

def render_ranking(results, title):
    st.subheader(title)
    if not results:
        st.warning("Fant ingen data.")
        return
    best = results[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Beste aksje", f"{best['ticker']} {best['score']}/10")
    c2.metric("Analyserte", len(results))
    c3.metric("Beste 6m", f"{best['ret_6m']*100:.1f}%")
    c4.metric("Auto-refresh", "5 min")

    for item in results[:10]:
        css, emoji = score_color(item["score"])
        left, right = st.columns([1.2, 2.2])
        with left:
            st.markdown(f"""
            <div class="card">
                <h3>{emoji} {item['ticker']}</h3>
                <div class="{css}">{item['score']}/10</div>
                <div class="small">{item['name']}</div>
            </div>
            """, unsafe_allow_html=True)
        with right:
            st.progress(min(item["score"] / 10, 1.0))
            st.caption(
                f"1y: {item['ret_1y']*100:.1f}% · "
                f"6m: {item['ret_6m']*100:.1f}% · "
                f"3m: {item['ret_3m']*100:.1f}% · "
                f"Vol: {item['volatility']:.4f} · "
                f"DD: {item['max_drawdown']*100:.1f}%"
            )

def render_analysis(results, label):
    st.subheader("📊 Interaktiv analyse")
    if not results:
        return
    selected = st.selectbox(f"Velg aksje ({label})", [r["ticker"] for r in results], key=f"select_{label}")
    item = next(r for r in results if r["ticker"] == selected)
    st.plotly_chart(plot_price(item["hist"], f"{selected} - prisutvikling"), use_container_width=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Score", f"{item['score']}/10")
    m2.metric("P/E", item.get("forward_pe") or item.get("trailing_pe") or "N/A")
    m3.metric("Revenue growth", f"{item['revenue_growth']*100:.1f}%" if isinstance(item.get("revenue_growth"), (int,float)) else "N/A")
    m4.metric("Max drawdown", f"{item['max_drawdown']*100:.1f}%")

    st.markdown("#### 🧠 Score-forklaring")
    parts = item.get("score_parts", {})
    if parts:
        for k, v in parts.items():
            st.progress(float(v))
            st.caption(f"{k}: {v}")

    st.markdown("#### 📰 Nyheter")
    if item["news_error"]:
        st.info(item["news_error"])
    elif not item["articles"]:
        st.info("Ingen relevante nyheter funnet.")
    else:
        for a in item["articles"]:
            st.markdown(f"- **{a.get('title','Uten tittel')}**  \n  <span class='small'>{a.get('source','')} · {a.get('published','')}</span>", unsafe_allow_html=True)

def render_ipo():
    st.subheader("🚀 Nye og kommende børsnoteringer")
    ipo_list, error = get_ipo_calendar()
    if error:
        st.info(error)
        return
    if not ipo_list:
        st.info("Fant ingen IPO-data akkurat nå.")
        return
    for ipo in ipo_list[:12]:
        st.markdown(f"**{ipo.get('name','Ukjent selskap')}** ({ipo.get('symbol','N/A')})")
        st.caption(f"{ipo.get('date','Ukjent dato')} · {ipo.get('exchange','Ukjent børs')}")
        st.divider()

def render_strategy_backtest(tickers, label):
    st.subheader("🧪 Smartere strategi-backtest")
    st.caption("Månedlig rebalansering, transaksjonskostnader, drawdown og benchmark.")

    col_a, col_b, col_c = st.columns(3)
    months = col_a.slider("Antall måneder", 6, 36, 24, key=f"months_{label}")
    top_n = col_b.slider("Topp N aksjer", 2, 10, 5, key=f"topn_{label}")
    cost = col_c.slider("Transaksjonskostnad", 0.0, 1.0, 0.2, step=0.1, key=f"cost_{label}") / 100

    use_stop = st.checkbox("Bruk enkel stop-loss", value=False, key=f"stop_{label}")
    stop_loss = st.slider("Stop-loss %", 3, 25, 10, key=f"sl_{label}") / 100 if use_stop else None

    benchmark = "^GSPC" if label == "USA" else "OSEBX.OL"

    if st.button(f"Kjør smartere backtest ({label})"):
        with st.spinner("Kjører backtest..."):
            strategy, bench, error = run_monthly_score_strategy(
                tickers,
                months=months,
                top_n=top_n,
                benchmark=benchmark,
                transaction_cost=cost,
                stop_loss=stop_loss,
            )

        if error:
            st.error(error)
            return

        strategy, stats = add_stats(strategy)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total avkastning", f"{stats['total_return']*100:.1f}%")
        c2.metric("Maks drawdown", f"{stats['max_drawdown']*100:.1f}%")
        c3.metric("Win-rate", f"{stats['win_rate']*100:.0f}%")
        c4.metric("Sharpe-ish", f"{stats['sharpe_like']:.2f}")

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=strategy["date"], y=strategy["value"], name="Score-strategi", mode="lines+markers"))
        if not bench.empty:
            fig.add_trace(go.Scatter(x=bench["date"], y=bench["benchmark_value"], name="Benchmark", mode="lines"))
        fig.update_layout(title="Strategi vs benchmark", template="plotly_dark", height=430)
        st.plotly_chart(fig, use_container_width=True)

        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=strategy["date"], y=strategy["drawdown"], fill="tozeroy", name="Drawdown"))
        fig_dd.update_layout(title="Drawdown", template="plotly_dark", height=300)
        st.plotly_chart(fig_dd, use_container_width=True)

        st.markdown("#### Valgte aksjer per måned")
        st.dataframe(strategy[["date", "monthly_return", "gross_return", "cost", "selected"]], use_container_width=True)

st.sidebar.title("⚙️ Innstillinger")
mode = st.sidebar.radio("Marked", ["USA / S&P 500", "Norge / Oslo Børs", "Begge"])
max_count = st.sidebar.slider("Antall aksjer å analysere", 5, 60, 15)
use_news = st.sidebar.checkbox("Bruk nyheter/sentiment", value=True)
search = st.sidebar.text_input("Søk ticker manuelt", placeholder="F.eks. AAPL, EQNR.OL")

st.title("📈 AI Aksje Analyzer Pro")
st.caption("Smartere scoring med momentum, trend, risiko, P/E, kvalitet, vekst, gjeld, nyheter og backtesting.")

if search.strip():
    tickers_us = [search.strip().upper()]
    tickers_no = []
else:
    tickers_us = get_sp500_tickers(limit=max_count)
    tickers_no = get_norwegian_tickers()[:max_count]

tabs = st.tabs(["🇺🇸 USA", "🇳🇴 Norske aksjer", "🚀 IPO", "🧪 Backtesting"])

with tabs[0]:
    if mode in ["USA / S&P 500", "Begge"] or search.strip():
        us_results = rank_stocks(tickers_us, max_count=max_count, use_news=use_news)
        render_ranking(us_results, "🏆 Topp rangerte USA/S&P 500")
        render_analysis(us_results, "USA")
    else:
        st.info("USA er slått av i sidepanelet.")

with tabs[1]:
    if mode in ["Norge / Oslo Børs", "Begge"] and not search.strip():
        no_results = rank_stocks(tickers_no, max_count=max_count, use_news=use_news)
        render_ranking(no_results, "🇳🇴 Topp 10 norske aksjer")
        render_analysis(no_results, "Norge")
    else:
        st.info("Velg Norge eller Begge i sidepanelet.")

with tabs[2]:
    render_ipo()

with tabs[3]:
    bt_market = st.radio("Backtest-marked", ["USA", "Norge"], horizontal=True)
    bt_tickers = tickers_us if bt_market == "USA" else get_norwegian_tickers()[:max_count]
    render_strategy_backtest(bt_tickers, bt_market)
