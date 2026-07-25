"""Renderer module extracted from app.py in v19.2.0.

Business calculations remain in the established services; this module owns only
the Streamlit presentation workflow and uses a compatibility context during the
transition away from the legacy monolith.
"""
from __future__ import annotations
from ui.legacy_context import bind_legacy_context

_PRESERVE = {'render_analysis'}

def render_analysis(_legacy_context, results, label):
    bind_legacy_context(globals(), _legacy_context, preserve=_PRESERVE)
    st.subheader("📊 Interaktiv analyse")

    # V14.8 / Oppgave 73: Interaktiv analyse kan hente fra siste lagrede dynamiske rangering,
    # uten å starte en ny scan/rangering bare fordi menyen åpnes.
    source_choice = st.selectbox(
        "Aksjekilde",
        ["Aktuell liste", "Smart Universe Picker", "Dynamisk watchlist / best rangerte", "Top Picks", "USA", "Norge", "Sverige", "Finland", "Danmark", "Brasil", "Norden", "Alle"],
        index=0,
        key=f"analysis_source_{label}_v148",
        help="Bruker siste lagrede/godkjente rangering. Manuell ticker overstyrer alltid listen.",
    )
    source_results = _latest_ranked_results_for_source(source_choice, results or [], current_label=label)

    # Oppgave 76/76B + 78/79: dynamiske, rangerte valg etter valgt aksjekilde.
    # Panelet starter tomt. Kilder må ha lagret rangering eller bygges eksplisitt
    # med egen knapp. Ingen stille fallback til AAPL.
    def _build_options(_source_results):
        result_options = [normalize_user_ticker(r.get("ticker")) for r in (_source_results or []) if isinstance(r, dict) and r.get("ticker")]
        _options = []
        _labels = {}
        for r in (_source_results or []):
            if not isinstance(r, dict):
                continue
            t = normalize_user_ticker(r.get("ticker"))
            if t:
                score = r.get("score", "N/A")
                try:
                    score_txt = f"{float(score):.2f}"
                except Exception:
                    score_txt = str(score)
                try:
                    action = card_decision_for_item(r).get("action_now", "")
                except Exception:
                    action = ""
                _labels[t] = f"{t} · score {score_txt}" + (f" · {action}" if action else "")
        for _t in result_options:
            if _t and _t not in _options:
                _options.append(_t)
        return _options, _labels

    options, option_labels = _build_options(source_results)
    if not options and source_choice == "Aktuell liste":
        st.info("Aktuell liste er tom. Kjør en rangering, velg et marked, eller skriv én ticker manuelt.")

    # V14.10: hvis valgt dynamisk kilde mangler liste, gi eksplisitt knapp for å bygge akkurat denne kilden.
    if not options and source_choice != "Aktuell liste":
        st.info(f"Ingen lagret dynamisk rangering for {source_choice}. Bygg listen nå, eller skriv én ticker manuelt.")
        build_cols = st.columns([1, 2])
        with build_cols[0]:
            if st.button(f"🔄 Oppdater {source_choice}-liste nå", key=f"build_interactive_source_{label}_{source_choice}_v1410", use_container_width=True):
                with st.spinner(f"Bygger dynamisk {source_choice}-liste..."):
                    source_results = _build_interactive_source_ranking_now(source_choice)
                options, option_labels = _build_options(source_results)
                if options:
                    st.success(f"{source_choice}-listen er oppdatert med {len(options)} aksjer ✅")
                else:
                    st.markdown(f"""<div class='visual-truth-empty-state'><b>Ingen data for {source_choice}.</b><br/>Prøv Global oppdatering / Scan watchlist, sjekk marked/filter, eller skriv ticker manuelt.</div>""", unsafe_allow_html=True)
        with build_cols[1]:
            st.caption("Knappen kjører bare valgt kilde. Den skal ikke starte AAPL-fallback eller skjulte markedspaneler.")

    source_key = re.sub(r"[^A-Za-z0-9]+", "_", source_choice).strip("_") or "source"
    manual_key = f"manual_ticker_{label}_v1410"
    clear_key = f"clear_manual_ticker_{label}_v1410"
    if manual_key not in st.session_state:
        st.session_state[manual_key] = ""
    if st.session_state.get(clear_key):
        st.session_state[manual_key] = ""
        st.session_state[clear_key] = False

    s0, s1, s2 = st.columns([1.05, 2.0, 1.25])
    with s0:
        st.caption(f"Aktiv kilde: {source_choice}")
    with s1:
        selected_from_list = ""
        if options:
            selected_from_list = st.selectbox(
                f"Velg aksje fra valgt kilde ({source_choice})",
                options,
                index=0,
                key=f"select_{label}_{source_key}_v1410",
                format_func=lambda x: option_labels.get(x, x),
            )
        else:
            st.caption("Ingen listevalg tilgjengelig for valgt kilde ennå.")
    with s2:
        manual_ticker_raw = st.text_input(
            "Eller skriv ticker",
            placeholder="Skriv én ticker, f.eks. EQNR.OL",
            key=manual_key,
            help="Manuell ticker overstyrer valgt kilde. For flere tickere bruker du Strategi-test.",
        )
        if st.button("Tøm manuell ticker", key=f"manual_ticker_clear_btn_{label}_v1410", use_container_width=True):
            st.session_state[manual_key] = ""
            st.rerun()
        st.caption("Eksempel: EQNR.OL, VOLV-B.ST, NOVO-B.CO, NOKIA.HE eller PETR4.SA")

    manual_ticker_clean = _clean_manual_ticker_input(manual_ticker_raw)
    if manual_ticker_raw and manual_ticker_clean != normalize_user_ticker(manual_ticker_raw):
        st.caption(f"Manuell input er tolket som én ticker: {manual_ticker_clean or 'ingen'}")

    selected = active_ticker_from_inputs(manual_ticker_raw, selected_from_list)
    if manual_ticker_clean:
        st.caption(f"Aktiv tickerkilde: Manuell ticker · Bruker ticker: {selected}")
    elif selected:
        st.caption(f"Aktiv tickerkilde: {source_choice} · Bruker ticker: {selected}")
    else:
        st.warning("Velg en ticker fra listen, bygg valgt kilde, eller skriv én ticker manuelt.")
        return

    item = next((r for r in (source_results or []) if normalize_user_ticker(r.get("ticker")) == selected), None)
    if item is None or not isinstance(item, dict) or "hist" not in item:
        with st.spinner(f"Henter analyse for {selected}..."):
            fetched_item = cached_score_stock_manual(selected, use_news=False)
        if fetched_item:
            merged_item = dict(fetched_item)
            if isinstance(item, dict):
                merged_item.update({k: v for k, v in item.items() if v not in (None, "")})
                merged_item.setdefault("hist", fetched_item.get("hist"))
            item = merged_item

    if not item:
        if _manual_update_mode_enabled():
            st.info("Manuell modus er aktiv og det finnes ingen lagret analyse for valgt ticker. Trykk Oppdater hele appen for å hente data.")
        else:
            st.warning("Fant ikke data for valgt ticker. Sjekk ticker-symbol, f.eks. EQNR.OL, VOLV-B.ST, NOVO-B.CO, NOKIA.HE eller PETR4.SA.")
        return

    _sync_timeframe, _sync_period = get_selected_time_settings(label, selected)
    _synced_df = cached_timeframe_data_manual(selected, _sync_timeframe, _sync_period)
    if _synced_df is not None and not _synced_df.empty:
        df = _synced_df.copy()
    else:
        df = item["hist"].copy()

    # v18.6.70: nøkkeltall vises som kompakte badges, ikke fire store metrickort.
    pe_value_v18669 = item.get("forward_pe") or item.get("trailing_pe") or "N/A"
    growth_value_v18669 = f"{item['revenue_growth']*100:.1f}%" if isinstance(item.get("revenue_growth"), (int,float)) else "N/A"
    dd_value_v18669 = f"{item['max_drawdown']*100:.1f}%" if isinstance(item.get("max_drawdown"), (int,float)) else "N/A"
    st.markdown(
        "<div class='ia-hero-row'>"
        f"<div class='ia-hero-chip'><span class='k'>Score</span><span class='v'>{_safe_html_value(item.get('score','N/A'))}/10</span></div>"
        f"<div class='ia-hero-chip'><span class='k'>P/E</span><span class='v'>{_safe_html_value(pe_value_v18669)}</span></div>"
        f"<div class='ia-hero-chip'><span class='k'>Revenue growth</span><span class='v'>{_safe_html_value(growth_value_v18669)}</span></div>"
        f"<div class='ia-hero-chip'><span class='k'>Max drawdown</span><span class='v'>{_safe_html_value(dd_value_v18669)}</span></div>"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown("#### 📈 Teknisk analyse")

    chart_readability_mode_v18667 = st.radio(
        "Grafmodus",
        ["Standard", "Teknisk", "Avansert"],
        index=0,
        horizontal=True,
        key=f"chart_readability_mode_{label}_{selected}_v18667",
        help="Standard viser færre indikatorer og tydelig trend. Teknisk legger til MACD/RSI. Avansert viser flere støtte-/motstands- og pattern-detaljer.",
    )

    rsi = calculate_rsi(df)
    macd, macd_signal, macd_hist = calculate_macd(df)
    bb_ma, bb_upper, bb_lower = calculate_bollinger(df)
    trend = detect_trend(df)

    latest_rsi = rsi.dropna().iloc[-1] if not rsi.dropna().empty else 50
    latest_macd = macd.dropna().iloc[-1] if not macd.dropna().empty else 0
    latest_macd_signal = macd_signal.dropna().iloc[-1] if not macd_signal.dropna().empty else 0
    latest_close = df["Close"].iloc[-1]
    latest_upper = bb_upper.dropna().iloc[-1] if not bb_upper.dropna().empty else latest_close
    latest_lower = bb_lower.dropna().iloc[-1] if not bb_lower.dropna().empty else latest_close

    hs = detect_head_shoulders(df)
    inv_hs = detect_inverse_head_shoulders(df)
    breakout = breakout_scanner(df)
    alerts = build_signal_alerts(latest_rsi, latest_macd, latest_macd_signal, breakout, hs, inv_hs)

    technical_context = {
        "rsi": latest_rsi,
        "macd_bullish": latest_macd > latest_macd_signal,
        "breakout_type": breakout.get("type", "neutral"),
        "head_shoulders_found": hs.get("found", False),
        "inverse_head_shoulders_found": inv_hs.get("found", False),
    }

    decision = build_trading_decision(item, technical_context)
    adj_score = adjusted_score(item, decision)

    insider = _cached_external_signal_manual("insider", selected, get_insider_data, default={"score": 0.5, "label": "Cache/ikke hentet"})
    analyst = _cached_external_signal_manual("analyst", selected, get_analyst_trend, default={})
    earnings = _cached_external_signal_manual("earnings", selected, get_earnings, default={})

    signal_intelligence = calculate_signal_intelligence(
        item,
        technical_context=technical_context,
        insider=insider,
        analyst=analyst,
        earnings=earnings,
    ) if use_signal_intelligence else None

    if signal_intelligence:
        decision["decision"] = signal_intelligence["decision"]
        decision["emoji"] = signal_intelligence["emoji"]
        decision["confidence"] = signal_intelligence.get("confidence", 0)
        decision["decision_score"] = signal_intelligence.get("final_score", signal_intelligence.get("decision_score", 0))
        decision["reasons"] = decision.get("reasons", []) + signal_intelligence.get("reasons", [])

    # MOBILE_ANALYSIS_STEP3_TRADING_PANEL_V1
    render_mobile_analysis_view(
        item,
        selected,
        label,
        decision=decision,
        technical_context=technical_context,
        chart_renderer=render_interactive_chart,
        chart_mode=chart_readability_mode_v18667,
    )

    st.markdown("---")

    # UI-signalvarsler er deaktivert for å hindre dobbelvarsling.
    # Varsler styres nå fra Varselkontroll:
    # - faktisk paper BUY/SELL via trading_engine/notifier
    # - watchlist signalendring via scan_watchlist_and_alert

    st.markdown("#### 🤖 Trading engine")
    render_decision_banner(decision, item, adj_score)

    if signal_intelligence:
        st.markdown("#### Signal Intelligence")
        if APP_VIEW_MODE == "Full":
            si1, si2, si3, si4 = st.columns(4)
            si1.metric("Smart score", f"{signal_intelligence.get('final_score', signal_intelligence.get('decision_score', 0))}/10")
            si2.metric("Confidence", f"{signal_intelligence.get('confidence', 0)}%")
            si3.metric("Risk", signal_intelligence.get("risk", "Middels"))
            si4.metric("Confidence", f"{signal_intelligence.get('confidence', 0)}%")
        else:
            render_compact_stat_grid([
                ("Smart score", f"{signal_intelligence.get('final_score', signal_intelligence.get('decision_score', 0))}/10"),
                ("Confidence", f"{signal_intelligence.get('confidence', 0)}%"),
                ("Risk", signal_intelligence.get("risk", "Middels")),
            ], columns=3)

        render_intelligence_cards(insider, analyst, earnings)

    with st.expander("Hvorfor dette signalet?"):
        for reason in decision["reasons"]:
            st.write("•", reason)

    chart_currency = currency_suffix(selected)
    def _level_with_currency_v1863ae(value):
        try:
            return f"{float(value):.2f} {chart_currency}"
        except Exception:
            return "N/A"

    render_compact_stat_grid([
        ("RSI", f"{latest_rsi:.1f}"),
        ("Trend", trend),
        ("MACD", "Bullish 🟢" if latest_macd > latest_macd_signal else "Bearish 🔴"),
        ("Breakout", breakout.get("signal", "N/A")),
        ("Motstand", _level_with_currency_v1863ae(breakout.get("resistance"))),
        ("Støtte", _level_with_currency_v1863ae(breakout.get("support"))),
        ("Volum boost", breakout.get("volume_boost", "N/A")),
    ], columns=7)

    render_rsi_box(latest_rsi)

    alert_items_v18667 = []
    for title, desc, kind in alerts:
        icon = "🟢" if kind == "bullish" else ("🔴" if kind == "bearish" else "⚪")
        alert_items_v18667.append(f"<span class='density-badge'>{icon} {_safe_html_value(title)}</span>")
    if alert_items_v18667:
        st.markdown("<div class='density-badge-row'>" + "".join(alert_items_v18667) + "</div>", unsafe_allow_html=True)

    with st.expander("Pattern detection og signal-alerts", expanded=False):
        for title, desc, kind in alerts:
            st.write(f"• {title}: {desc}")
        st.write("•", hs.get("label", "Ingen tydelig hode/skulder"))
        st.write("•", inv_hs.get("label", "Ingen tydelig invertert hode/skulder"))

    fig_ta = go.Figure()
    fig_ta.add_trace(go.Scatter(x=df.index, y=df["Close"], name="Pris", mode="lines", line=dict(width=2.4)))
    fig_ta.add_trace(go.Scatter(x=df.index, y=bb_ma, name="Trend/MA", mode="lines", line=dict(width=1.5, dash="dot")))
    if chart_readability_mode_v18667 in ("Teknisk", "Avansert"):
        fig_ta.add_trace(go.Scatter(x=df.index, y=bb_upper, name="Kanal øvre", mode="lines", line=dict(dash="dot", width=1.0), opacity=0.55))
        fig_ta.add_trace(go.Scatter(x=df.index, y=bb_lower, name="Kanal nedre", mode="lines", line=dict(dash="dot", width=1.0), opacity=0.55))

    if chart_readability_mode_v18667 in ("Teknisk", "Avansert") and breakout.get("support") != "N/A":
        fig_ta.add_hline(y=breakout.get("support"), line_dash="dash", annotation_text="Støtte")
    if chart_readability_mode_v18667 in ("Teknisk", "Avansert") and breakout.get("resistance") != "N/A":
        fig_ta.add_hline(y=breakout.get("resistance"), line_dash="dash", annotation_text="Motstand")

    if chart_readability_mode_v18667 == "Avansert" and hs.get("found"):
        fig_ta = add_pattern_markers(fig_ta, hs, "Hode/skulder")
    if chart_readability_mode_v18667 == "Avansert" and inv_hs.get("found"):
        fig_ta = add_pattern_markers(fig_ta, inv_hs, "Invertert hode/skulder")

    fig_ta.update_layout(
        title=f"{selected} - Prisgraf ({chart_readability_mode_v18667})",
        template="plotly_dark",
        height=420 if chart_readability_mode_v18667 == "Standard" else 470,
        paper_bgcolor="#0b111c",
        plot_bgcolor="#0b111c",
    )
    try:
        last_x_ta = df.index[-1]
        last_price_ta = float(df["Close"].dropna().iloc[-1])

        fig_ta.add_hline(
            y=last_price_ta,
            line_dash="dot",
            line_color="rgba(255,255,255,0.45)",
        )

        add_right_side_price_label(
            fig_ta,
            last_x_ta,
            last_price_ta,
            f"Pris: {last_price_ta:.2f} {chart_currency}",
            color="white",
            yshift=0,
        )

        # Bollinger labels on right side if available
        try:
            bb_mid_val = float(bb_ma.dropna().iloc[-1])
            bb_upper_val = float(bb_upper.dropna().iloc[-1])
            bb_lower_val = float(bb_lower.dropna().iloc[-1])

            add_right_side_price_label(fig_ta, last_x_ta, bb_mid_val, f"BB midt: {bb_mid_val:.2f} {chart_currency}", color="#ff6b4a")
            add_right_side_price_label(fig_ta, last_x_ta, bb_upper_val, f"BB øvre: {bb_upper_val:.2f} {chart_currency}", color="#00e6a8")
            add_right_side_price_label(fig_ta, last_x_ta, bb_lower_val, f"BB nedre: {bb_lower_val:.2f} {chart_currency}", color="#b56cff")
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)

        fig_ta.update_layout(
            margin=dict(l=20, r=110 if chart_readability_mode_v18667 == "Standard" else 150, t=70, b=28),
            legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
            annotations=[
                *fig_ta.layout.annotations,
                dict(
                    text=f"💹 Gjeldende kurs: <b>{last_price_ta:.2f} {chart_currency}</b>",
                    xref="paper",
                    yref="paper",
                    x=0.01,
                    y=1.14,
                    showarrow=False,
                    align="left",
                    font=dict(size=15, color="white"),
                    bgcolor="rgba(30,41,59,0.9)",
                    bordercolor="rgba(255,255,255,0.25)",
                    borderwidth=1,
                )
            ],
        )
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
    render_interactive_chart(fig_ta, use_container_width=True, key=f"ta_chart_{label}_{selected}_{chart_readability_mode_v18667}")
    if chart_readability_mode_v18667 in ("Teknisk", "Avansert"):
        render_graph_explanation("ta")

    if chart_readability_mode_v18667 == "Standard":
        return

    fig_macd = go.Figure()

    macd_clean = macd.dropna()
    macd_signal_clean = macd_signal.dropna()
    macd_hist_clean = macd_hist.dropna()

    macd_last = float(macd_clean.iloc[-1]) if len(macd_clean) else 0.0
    signal_last = float(macd_signal_clean.iloc[-1]) if len(macd_signal_clean) else 0.0
    hist_last = float(macd_hist_clean.iloc[-1]) if len(macd_hist_clean) else 0.0
    last_x = df.index[-1]

    hist_colors = ["#22c55e" if float(v) >= 0 else "#ef4444" for v in macd_hist.fillna(0)]

    fig_macd.add_trace(
        go.Scatter(
            x=df.index,
            y=macd,
            name="🔵 MACD-linje",
            mode="lines",
            line=dict(color="#3b82f6", width=2.6),
            hovertemplate="<b>🔵 MACD-linje</b><br>Dato: %{x}<br>Verdi: %{y:.2f}<extra></extra>",
        )
    )

    fig_macd.add_trace(
        go.Scatter(
            x=df.index,
            y=macd_signal,
            name="🔴 Signallinje",
            mode="lines",
            line=dict(color="#ef4444", width=2.4),
            hovertemplate="<b>🔴 Signallinje</b><br>Dato: %{x}<br>Verdi: %{y:.2f}<extra></extra>",
        )
    )

    fig_macd.add_trace(
        go.Bar(
            x=df.index,
            y=macd_hist,
            name="🟢/🔴 Histogram",
            marker=dict(color=hist_colors),
            opacity=0.78,
            hovertemplate="<b>🟢/🔴 Histogram</b><br>Dato: %{x}<br>MACD - signal: %{y:.2f}<extra></extra>",
        )
    )

    fig_macd.add_hline(
        y=0,
        line_width=1,
        line_dash="dot",
        line_color="rgba(255,255,255,0.55)",
        annotation_text="0-linje",
        annotation_position="right",
    )

    fig_macd.add_annotation(
        x=last_x,
        y=macd_last,
        text=f"🔵 MACD {macd_last:.2f}",
        showarrow=True,
        arrowhead=2,
        ax=42,
        ay=-26,
        bgcolor="rgba(59,130,246,0.18)",
        bordercolor="#3b82f6",
        borderwidth=1,
        font=dict(color="#dbeafe", size=12),
    )

    fig_macd.add_annotation(
        x=last_x,
        y=signal_last,
        text=f"🔴 Signal {signal_last:.2f}",
        showarrow=True,
        arrowhead=2,
        ax=42,
        ay=26,
        bgcolor="rgba(239,68,68,0.18)",
        bordercolor="#ef4444",
        borderwidth=1,
        font=dict(color="#fee2e2", size=12),
    )

    fig_macd.add_annotation(
        xref="paper",
        yref="paper",
        x=0.01,
        y=1.15,
        text=f"Histogram nå: {'🟢 positiv' if hist_last >= 0 else '🔴 negativ'} ({hist_last:.2f})",
        showarrow=False,
        align="left",
        bgcolor="rgba(15,23,42,0.88)",
        bordercolor="rgba(148,163,184,0.45)",
        borderwidth=1,
        font=dict(color="#f8fafc", size=12),
    )

    fig_macd.update_layout(
        title=f"{selected} - MACD: blå linje / rød signal / grønt-rødt histogram",
        template="plotly_dark",
        height=330,
        paper_bgcolor="#0b111c",
        plot_bgcolor="#0b111c",
        margin=dict(l=40, r=90, t=95, b=35),
        legend=dict(
            title="Forklaring",
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
            bgcolor="rgba(15,23,42,0.75)",
            bordercolor="rgba(148,163,184,0.35)",
            borderwidth=1,
        ),
    )
    render_interactive_chart(fig_macd, use_container_width=True, key=f"macd_chart_{label}_{selected}_{chart_readability_mode_v18667}")

    if chart_readability_mode_v18667 == "Avansert":
        render_macd_explanation()

    fig_rsi = go.Figure()
    fig_rsi.add_trace(go.Scatter(x=df.index, y=rsi, name="RSI", mode="lines"))
    fig_rsi.add_hline(y=80, line_dash="dot", annotation_text="80 ekstremt overkjøpt", annotation_position="right")
    fig_rsi.add_hline(y=70, line_dash="dash", annotation_text="Overkjøpt")
    fig_rsi.add_hline(y=30, line_dash="dash", annotation_text="Oversolgt")
    fig_rsi.update_layout(
        title=f"{selected} - RSI",
        template="plotly_dark",
        height=260,
        paper_bgcolor="#0b111c",
        plot_bgcolor="#0b111c",
        yaxis=dict(range=[0, 100]),
    )
    render_interactive_chart(add_rsi_level_labels(fig_rsi, rsi), use_container_width=True, key=f"rsi_chart_{label}_{selected}_{chart_readability_mode_v18667}")
    if chart_readability_mode_v18667 == "Avansert":
        render_graph_explanation("rsi")

    # v18.5.30 Legacy cleanup: standalone strategy testing and strategy
    # optimization were removed from per-ticker analysis cards. Use
    # AI Kontrollsenter -> Testing & Learning as the single source for
    # Strategi-test, Strategi-test Pro and learning history.

    parts = item.get("score_parts", {})
    with st.expander("Score-forklaring", expanded=False):
        if parts:
            st.caption("Åpne/lukk denne seksjonen etter behov. Verdiene er normalisert fra 0 til 1.")
            for k, v in parts.items():
                try:
                    _score_value = max(0.0, min(1.0, float(v)))
                except Exception:
                    _score_value = 0.0
                _label = str(k).replace("_", " ").title()
                st.progress(_score_value)
                st.caption(f"{_label}: {_score_value:.3f}")
        else:
            st.caption("Ingen score-detaljer tilgjengelig for denne aksjen.")

    st.markdown("#### 📰 Nyheter")
    st.caption("For å spare NewsAPI-kall hentes nyheter bare for valgt aksje når du trykker knappen.")

    if not use_news:
        st.info("Nyheter/sentiment er slått av i sidepanelet.")
    elif st.button(f"Hent nyheter for {selected}", key=f"news_btn_{label}_{selected}"):
        articles, error = get_news(selected.replace(".OL", ""), limit=6, source="manual", force=True)

        if error:
            st.warning(f"Nyheter midlertidig utilgjengelig: {error}")
        elif not articles:
            st.info("Ingen relevante nyheter funnet.")
        else:
            live_sentiment = simple_finance_sentiment(articles)
            st.metric("Live nyhets-sentiment", live_sentiment)

            for a in articles:
                st.markdown(
                    f"- **{a.get('title','Uten tittel')}**  \n"
                    f"  <span class='small'>{a.get('source','')} · {a.get('published','')}</span>",
                    unsafe_allow_html=True,
                )
    else:
        st.info("Trykk på knappen over for å hente nyheter for valgt aksje.")
