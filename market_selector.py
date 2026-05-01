import pandas as pd
import streamlit as st
from analysis import score_stock
from background_guard import score_stock_guarded

@st.cache_data(ttl=900, show_spinner=False)
def cached_score_stock(ticker, use_news=False):
    """
    Cache + market guard:
    - henter fersk data kun når markedet for tickeren er åpent
    - bruker cache når markedet er stengt
    """
    return score_stock_guarded(score_stock, ticker, use_news=use_news, mode="background")

@st.cache_data(ttl=900, show_spinner=False)
def cached_score_stock_manual(ticker, use_news=False):
    """
    Manuell UI-henting:
    Tillater at bruker henter Top Picks selv om markedet er stengt.
    Auto/Cron bruker fortsatt background guard.
    """
    return score_stock_guarded(score_stock, ticker, use_news=use_news, mode="manual")


def auto_rank_market(tickers, max_count=30, use_news=False):
    """
    Automatisk markedsscanner:
    - analyserer tickere
    - scorer dem
    - sorterer dynamisk etter score
    Listen og rekkefølgen endrer seg når prisdata/marked endrer seg.
    """
    results = []
    for ticker in tickers[:max_count]:
        item = cached_score_stock_manual(ticker, use_news=use_news) if force_manual_fetch else cached_score_stock(ticker, use_news=use_news)
        if item:
            results.append(item)

    return sorted(results, key=lambda x: x.get("score", 0), reverse=True)

def build_top_picks(results, min_score=6.5, max_items=10):
    """
    Velger automatisk de sterkeste kandidatene basert på score.
    Dette er en enkel top-picks-liste, ikke investeringsråd.
    """
    picks = [r for r in results if r.get("score", 0) >= min_score]
    return sorted(picks, key=lambda x: x.get("score", 0), reverse=True)[:max_items]
