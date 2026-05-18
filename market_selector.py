import pandas as pd
import streamlit as st
from analysis import rank_stocks, score_stock
from background_guard import score_stock_guarded

@st.cache_data(ttl=900, show_spinner=False)
def cached_score_stock(ticker, use_news=False, include_insider=False):
    """
    Cache + market guard:
    - henter fersk data kun når markedet for tickeren er åpent
    - bruker cache når markedet er stengt
    """
    return score_stock_guarded(score_stock, ticker, use_news=use_news, mode="background", include_insider=include_insider)

@st.cache_data(ttl=900, show_spinner=False)
def cached_score_stock_manual(ticker, use_news=False, include_insider=False):
    """
    Manuell UI-henting:
    Tillater at bruker henter Top Picks selv om markedet er stengt.
    Auto/Cron bruker fortsatt background guard.
    """
    return score_stock_guarded(score_stock, ticker, use_news=use_news, mode="manual", include_insider=include_insider)


def auto_rank_market(tickers, max_count=30, use_news=False, force_manual_fetch=False, include_insider=True, insider_limit=12):
    # AUTO_RANK_FORCE_MANUAL_FETCH_HOTFIX
    try:
        force_manual_fetch
    except NameError:
        force_manual_fetch = False

    """
    Automatisk markedsscanner:
    - analyserer tickere
    - scorer dem
    - sorterer dynamisk etter score
    Listen og rekkefølgen endrer seg når prisdata/marked endrer seg.
    """
    clean = [str(t or "").strip().upper() for t in (tickers or []) if str(t or "").strip()][:max_count]
    if force_manual_fetch:
        try:
            return rank_stocks(
                clean,
                max_count=max_count,
                use_news=use_news,
                include_insider=include_insider,
                insider_limit=insider_limit,
                use_batch=True,
            )
        except Exception:
            pass

    results = []
    fetcher = cached_score_stock_manual if force_manual_fetch else cached_score_stock
    for ticker in clean:
        item = fetcher(ticker, use_news=use_news, include_insider=False)
        if item:
            results.append(item)

    results = sorted(results, key=lambda x: x.get("score", 0), reverse=True)
    if include_insider and results:
        enriched = []
        limit = max(0, min(int(insider_limit or 0), len(results)))
        for idx, item in enumerate(results):
            if idx < limit:
                ticker = item.get("ticker")
                enriched_item = fetcher(ticker, use_news=use_news, include_insider=True)
                enriched.append(enriched_item or item)
            else:
                enriched.append(item)
        results = enriched

    return sorted(results, key=lambda x: x.get("score", 0), reverse=True)

def build_top_picks(results, min_score=6.5, max_items=10):
    """
    Velger automatisk de sterkeste kandidatene basert på score.
    Dette er en enkel top-picks-liste, ikke investeringsråd.
    """
    picks = [r for r in results if r.get("score", 0) >= min_score]
    return sorted(picks, key=lambda x: x.get("score", 0), reverse=True)[:max_items]
