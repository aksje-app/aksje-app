"""Renderer module extracted from app.py in v19.2.0.

Business calculations remain in the established services; this module owns only
the Streamlit presentation workflow and uses a compatibility context during the
transition away from the legacy monolith.
"""
from __future__ import annotations
from ui.legacy_context import bind_legacy_context

_PRESERVE = {'render_live_market_banner'}

def render_live_market_banner(_legacy_context):
    bind_legacy_context(globals(), _legacy_context, preserve=_PRESERVE)
    settings = load_settings()
    if not settings.get("live_banner_enabled", True):
        return

    banner_items = parse_banner_tickers(settings)
    if not banner_items:
        return

    _banner_fp = tuple((str(m), str(t), str(l)) for m, t, l in banner_items)
    _banner_key = f"live_banner_cache_v16_{_cache_key_safe(_banner_fp)}"
    _banner_selected_from_query_v18610([], banner_items)
    if not _heavy_update_allowed():
        banner_cards = st.session_state.get(_banner_key) or st.session_state.get("live_banner_cache_v16_latest") or []
        if not banner_cards:
            banner_cards = _banner_fallback_cards_v18614(banner_items)
    else:
        banner_cards = fetch_live_banner_snapshot(banner_items)
        if banner_cards:
            st.session_state[_banner_key] = banner_cards
            st.session_state["live_banner_cache_v16_latest"] = banner_cards
    if not banner_cards:
        banner_cards = _banner_fallback_cards_v18614(banner_items)
    if not banner_cards:
        return

    banner_alert_config = _load_banner_alert_config_v18610(settings)
    banner_cards = _apply_banner_alerts_v18610(banner_cards, banner_alert_config)
    _banner_selected_from_query_v18610(banner_cards, banner_items)

    cards = []
    for item in banner_cards:
        from urllib.parse import quote
        pct = float(item.get("pct", 0.0))
        delta = float(item.get("delta", 0.0))
        pct_class = "pos" if pct >= 0 else "neg"
        market_label = html.escape(str(item.get("market", "")))
        title_label = html.escape(str(item.get("label", item.get("ticker", ""))))
        ticker_value = str(item.get("ticker", "")).upper()
        raw_price = item.get("price")
        price_missing = raw_price in (None, "", 0, 0.0) or str(raw_price).strip().lower() in {"nan", "none", "-"}
        price_txt = "Data mangler" if price_missing else _banner_price_text_v18623(raw_price)
        delta_txt = "" if price_missing else f"{delta:+.2f}"
        pct_txt = "" if price_missing else f"{pct:+.2f}%"
        marker_html = _banner_marker_html_v18610(item.get("alert_marker"))
        marker_title = html.escape(str(item.get("alert_explanation") or "Åpne tickerdetalj"))
        href = f"?banner_ticker={quote(ticker_value)}&banner_market={quote(str(item.get('market', '')))}"

        change_html = "" if price_missing else f"<div class='ticker-change {pct_class}'>{delta_txt} {pct_txt}</div>"
        spark_html = "" if price_missing else str(item.get("sparkline") or "")
        cards.append(
            f"<a class='ticker-tape-item' target='_self' href='{href}' title='{marker_title}'>"
            f"{marker_html}"
            "<div class='ticker-info'>"
            f"<div class='ticker-market'>{market_label}</div>"
            f"<div class='ticker-title'>{title_label}</div>"
            f"<div class='ticker-price {'missing' if price_missing else ''}'>{price_txt}</div>"
            f"{change_html}"
            "</div>"
            f"<div class='ticker-spark'>{spark_html}</div>"
            "</a>"
        )

    cards_html = "".join(cards)
    # V17 / Oppgave 126B: skill animasjonshastighet fra data-refresh.
    # live_banner_speed_seconds styrer bare CSS-scroll, ui_refresh_minutes styrer bare datacache.
    refresh_minutes = int(settings.get("ui_refresh_minutes", 60) or 60)
    speed_seconds = int(settings.get("live_banner_speed_seconds", 70) or 70)
    speed_seconds = max(10, min(speed_seconds, 300))

    # IMPORTANT:
    # CSS ligger i vanlig string, ikke f-string, for å unngå SyntaxError fra CSS-klammer.
    banner_html = _banner_detail_layout_css_v18614() + """
    <style>
    .ticker-tape-wrap {
        width: 100%;
        overflow: hidden;
        margin: 0.20rem 0 0.42rem 0;
        padding: 0;
        border-top: 1px solid rgba(15,23,42,0.10);
        border-bottom: 1px solid rgba(15,23,42,0.14);
        background: #f8fafc;
        border-radius: 12px;
        min-height: 54px;
        box-shadow: inset 0 0 0 1px rgba(15,23,42,0.03);
    }
    .ticker-tape-track {
        display: flex;
        align-items: stretch;
        width: max-content;
        gap: 10px;
        white-space: nowrap;
        animation: tickerTapeScroll __SPEED__s linear infinite;
        padding: 6px 8px;
    }
    .ticker-tape-wrap:hover .ticker-tape-track {
        animation-play-state: paused;
    }
    .ticker-tape-item {
        display: inline-grid;
        grid-template-columns: 22px 132px 96px;
        align-items: center;
        gap: 8px;
        min-width: 236px;
        height: 42px;
        padding: 5px 9px;
        border-radius: 0;
        background: #ffffff;
        border-right: 1px solid rgba(15,23,42,0.10);
        color: inherit;
        text-decoration: none;
        position: relative;
    }
    .ticker-tape-item:hover {
        background: #eef6ff;
        box-shadow: inset 0 0 0 1px rgba(37,99,235,0.18);
    }
    .ticker-alert-marker {
        width: 22px;
        height: 22px;
        border-radius: 999px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 0.92rem;
        font-weight: 950;
        line-height: 1;
        color: #0f172a;
        border: 1.5px solid rgba(15,23,42,0.34);
        box-shadow: 0 1px 3px rgba(15,23,42,0.22);
    }
    .ticker-alert-marker.green { background: #22c55e; }
    .ticker-alert-marker.yellow { background: #facc15; }
    .ticker-alert-marker.red { background: #ef4444; color: #fff; }
    .ticker-alert-marker span { transform: translateY(-.5px); text-shadow: 0 1px 1px rgba(0,0,0,.28); }
    .ticker-alert-marker.green span { display: none; }
    .ticker-alert-marker.green:after {
        content: "";
        width: 5px;
        height: 5px;
        border-radius: 999px;
        background: #052e16;
    }
    .ticker-info {
        display: flex;
        flex-direction: column;
        justify-content: center;
        line-height: 1.12;
    }
    .ticker-market {
        font-size: 0.56rem;
        font-weight: 800;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: #64748b;
        margin-bottom: 2px;
    }
    .ticker-title {
        font-size: 0.82rem;
        font-weight: 900;
        color: #2563eb;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        margin-bottom: 4px;
    }
    .ticker-price {
        font-size: 0.90rem;
        font-weight: 900;
        color: #1f2937;
        margin-top: 0;
    }
    .ticker-change {
        font-size: 0.78rem;
        font-weight: 950;
        margin-top: 3px;
    }
    .ticker-price.missing { color:#b45309; font-size:.74rem; }
    .ticker-change.pos { color: #059669; }
    .ticker-change.neg { color: #dc2626; }
    .ticker-spark {
        display: flex;
        align-items: center;
        justify-content: flex-end;
    }
    .ticker-spark svg {
        display: block;
        width: 94px;
        height: 24px;
    }
    .banner-decision-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 7px;
        margin: 8px 0 8px 0;
    }
    .banner-decision-card {
        border: 1px solid rgba(96,165,250,.36);
        background: rgba(15,23,42,.78);
        border-radius: 7px;
        padding: 8px 10px;
        min-height: 46px;
    }
    .banner-decision-label {
        color: #93c5fd;
        font-size: .68rem;
        font-weight: 900;
        text-transform: uppercase;
    }
    .banner-decision-value {
        color: #f8fafc;
        font-size: 1.02rem;
        font-weight: 950;
        margin-top: 2px;
    }
    .banner-decision-sub {
        color: #cbd5e1;
        font-size: .72rem;
        font-weight: 800;
        margin-top: 2px;
    }
    @keyframes tickerTapeScroll {
        from { transform: translateX(0); }
        to { transform: translateX(-50%); }
    }
    @media (max-width: 1100px) {
        .ticker-tape-wrap { min-height: 58px; }
        .ticker-tape-item {
            grid-template-columns: 22px 134px 102px;
            min-width: 276px;
            height: 48px;
            padding: 8px 12px;
        }
        .ticker-title { font-size: 0.96rem; }
        .ticker-price { font-size: 1.04rem; }
        .ticker-change { font-size: 0.90rem; }
        .ticker-spark svg { width: 102px; height: 26px; }
    }
    @media (max-width: 700px) {
        .ticker-tape-wrap {
            min-height: 56px;
            border-radius: 8px;
        }
        .ticker-tape-track {
            gap: 8px;
            padding: 8px 8px;
        }
        .ticker-tape-item {
            grid-template-columns: 22px 120px 86px;
            min-width: 244px;
            height: 46px;
            padding: 7px 10px;
            gap: 10px;
        }
        .ticker-market { font-size: 0.58rem; margin-bottom: 1px; }
        .ticker-title { font-size: 0.82rem; margin-bottom: 3px; }
        .ticker-price { font-size: 0.92rem; }
        .ticker-change { font-size: 0.78rem; margin-top: 4px; }
        .ticker-spark svg { width: 86px; height: 24px; }
    }
    /* v18.5.26: stop banner text from being clipped under the tape. */
    .ticker-tape-wrap + div, .ticker-tape-wrap + p { margin-top: .35rem !important; }
    .ticker-tape-item, .ticker-info, .ticker-change { overflow: visible !important; }
    </style>
    <div class='ticker-tape-wrap' aria-label='Ticker-banner'>
        <div class='ticker-tape-track'>__CARDS____CARDS__</div>
    </div>
    """
    banner_html = banner_html.replace("__SPEED__", str(speed_seconds)).replace("__CARDS__", cards_html)

    st.markdown(banner_html, unsafe_allow_html=True)
    alert_counts = {"red": 0, "yellow": 0, "green": 0}
    for card in banner_cards:
        css = str((card.get("alert_marker") or {}).get("css") or "green")
        if css in alert_counts:
            alert_counts[css] += 1
    st.caption(
        f"Banner: {len(banner_cards)} kort · grønn {alert_counts['green']} · gul {alert_counts['yellow']} · rød {alert_counts['red']} · "
        f"{speed_seconds}s · data ca. hver {refresh_minutes}. min. Lavere tall = raskere, høyere tall = saktere."
    )
    if st.session_state.pop("banner_detail_suppress_picker_once_v18611", False):
        st.session_state.pop("live_banner_open_picker_v18610", None)
    option_map = {
        f"{card.get('ticker')} | {card.get('label')} | {card.get('market')}": card
        for card in banner_cards
    }
    if option_map:
        with st.expander("Åpne ticker manuelt hvis bannerkortet er vanskelig å treffe", expanded=False):
            pick = st.selectbox(
                "Ticker",
                [""] + list(option_map.keys()),
                key="live_banner_open_picker_v18610",
            )
            if pick:
                card = option_map[pick]
                st.session_state["live_banner_selected_ticker_v18610"] = str(card.get("ticker") or "").upper()
                st.session_state["live_banner_selected_market_v18610"] = str(card.get("market") or "")
                st.session_state["live_banner_selected_label_v18610"] = str(card.get("label") or card.get("ticker") or "")
                st.session_state["ai_control_center_active_panel_v1863aj"] = ""

    selected_ticker = st.session_state.get("live_banner_selected_ticker_v18610")
    if selected_ticker:
        _render_banner_ticker_detail_v18610(
            selected_ticker,
            st.session_state.get("live_banner_selected_market_v18610", ""),
            st.session_state.get("live_banner_selected_label_v18610", ""),
        )
