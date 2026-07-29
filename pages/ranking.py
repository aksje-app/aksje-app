"""Renderer module extracted from app.py in v19.2.0.

Business calculations remain in the established services; this module owns only
the Streamlit presentation workflow and uses a compatibility context during the
transition away from the legacy monolith.
"""
from __future__ import annotations
from ui.legacy_context import bind_legacy_context

_PRESERVE = {'render_ranking'}

def render_ranking(_legacy_context, results, title):
    bind_legacy_context(globals(), _legacy_context, preserve=_PRESERVE)
    st.subheader(title)
    results = _ranked_for_display(results)
    try:
        if results:
            st.session_state["dashboard2026_last_rendered_rankings_v18635"] = list(results or [])
    except Exception:
        pass

    if not results:
        st.markdown("""
        <div class='visual-truth-empty-state'>
            <b>Ingen rangeringsdata tilgjengelig.</b><br/>
            Mulige årsaker: markedet er ikke oppdatert, scan/watchlist er ikke kjørt, eller aktivt filter gir ingen treff.
            Trykk <b>Global oppdatering</b> eller velg/skriv en ticker manuelt.
        </div>
        """, unsafe_allow_html=True)
        return

    best = results[0]
    best_price, best_change = get_item_price_change(best)
    best_decision = card_decision_for_item(best)

    if APP_VIEW_MODE == "Full":
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Beste kandidat", f"{best.get('ticker', best.get('symbol', '-'))} {best.get('score', 0)}/10")
        c2.metric("Analyserte", len(results))
        c3.metric(
            "Siste kurs",
            f"{best_price:.2f} {currency_suffix(best['ticker'])}" if best_price else "N/A",
            delta=f"{best_change:+.2f}%" if best_change is not None else None,
        )
        c4.metric("Beste handling", best_decision.get("action_now", "VENT"))
    else:
        render_compact_stat_grid([
            ("Beste kandidat", f"{best['ticker']} {best.get('score', 0)}/10"),
            ("Analyserte", len(results)),
            ("Siste kurs", f"{best_price:.2f} {currency_suffix(best['ticker'])}" if best_price else "N/A", f"{best_change:+.2f}%" if best_change is not None else None),
            ("Beste handling", best_decision.get("action_now", "VENT")),
        ], columns=4)

    st.markdown("#### ⚡ Hurtigliste med kurs")
    st.caption("Top Picks = sterk kandidat totalt. Handling nå = teknisk timing akkurat nå.")

    display_choice, display_limit = _ranking_display_limit_choice_v1864(title, len(results))
    display_rows = results[:display_limit]
    if len(display_rows) < len(results):
        st.caption(f"Viser {display_choice.lower()} av {len(results)}. Hele kandidatpakken beholdes for send videre.")
    else:
        st.caption(f"Viser alle {len(results)} kandidater. Hele kandidatpakken beholdes for send videre.")

    for idx, item in enumerate(display_rows, start=1):
        ticker = item.get("ticker", "N/A")
        score = item.get("score", 0)
        pe_text = _display_pe_v1863ad(item)
        pe_value_text = pe_text.replace("Forward P/E ", "").replace("Trailing P/E ", "")
        latest_price, change_pct = get_item_price_change(item)
        card_decision = card_decision_for_item(item)
        meta = resolve_security_metadata(ticker, item)
        listing = infer_security_listing(ticker, item)

        price_text = "N/A"
        delta_text = None
        direction_icon = "⚪"

        if latest_price is not None:
            price_text = f"{latest_price:.2f} {currency_suffix(ticker)}"
            delta_text = f"{change_pct:+.2f}%"
            direction_icon = "🟢" if change_pct >= 0 else "🔴"

        with st.container(border=True):
            left, mid, right = st.columns([1.35, 1.05, 2.35])

            with left:
                st.markdown(f"<div class='v18574-quick-title'>{direction_icon} {ticker}</div>", unsafe_allow_html=True)
                display_name = meta.get("name") or item.get("name") or "Navn ikke funnet"
                insider_score = item.get("insider_score")
                try:
                    insider_value = float(insider_score)
                    insider_chip = f"<span>Insider {insider_value * 100:.0f}%</span>" if insider_value <= 1 else f"<span>Insider {insider_value:.0f}%</span>"
                except Exception:
                    insider_chip = ""
                st.markdown(f"<div class='v18574-quick-sub'>#{idx} · {html.escape(str(display_name))}</div>", unsafe_allow_html=True)
                st.markdown(
                    "<div class='v1863m-quick-meta'>"
                    f"<span>{html.escape(str(listing.get('country', 'Ukjent')))}</span>"
                    f"<span>{html.escape(str(listing.get('exchange', 'Ukjent')))}</span>"
                    f"<span>{html.escape(str(meta.get('sector', 'Unknown')))}</span>"
                    f"{insider_chip}"
                    "</div>",
                    unsafe_allow_html=True,
                )
                render_action_chips(card_decision)

            with mid:
                if APP_VIEW_MODE == "Full":
                    st.metric("Total score", f"{score}/10")
                    st.metric("P/E", pe_value_text)
                    st.metric("Kurs", price_text, delta=delta_text)
                else:
                    render_compact_stat_grid([
                        ("Score", f"{score}/10"),
                        ("P/E", pe_value_text),
                        ("Kurs", price_text, delta_text),
                    ], columns=1)

            with right:
                st.markdown("<div class='v1863m-quick-action'>", unsafe_allow_html=True)
                st.progress(min(float(score) / 10, 1.0))
                st.caption(
                    f"1y: {item.get('ret_1y', 0)*100:.1f}% · "
                    f"6m: {item.get('ret_6m', 0)*100:.1f}% · "
                    f"3m: {item.get('ret_3m', 0)*100:.1f}% · "
                    f"Vol: {item.get('volatility', 0):.4f} · "
                    f"DD: {item.get('max_drawdown', 0)*100:.1f}% · "
                    f"{pe_text}"
                )

                score_bits = []
                try:
                    ret_6m = float(item.get("ret_6m", 0) or 0)
                    ret_3m = float(item.get("ret_3m", 0) or 0)
                    volatility = float(item.get("volatility", 0) or 0)
                    drawdown = float(item.get("max_drawdown", 0) or 0)
                    if ret_6m >= 0.15:
                        score_bits.append(f"sterk 6m momentum {ret_6m * 100:.1f}%")
                    elif ret_3m >= 0.08:
                        score_bits.append(f"positiv 3m momentum {ret_3m * 100:.1f}%")
                    else:
                        score_bits.append("momentum er moderat")
                    if volatility <= 0.035:
                        score_bits.append("risiko/volatilitet er lav til moderat")
                    else:
                        score_bits.append(f"volatilitet trekker opp risiko ({volatility:.3f})")
                    if drawdown < -0.20:
                        score_bits.append(f"drawdown trekker ned ({drawdown * 100:.1f}%)")
                    if pe_value_text not in {"-", "N/A", ""}:
                        score_bits.append(f"verdsettelse P/E {pe_value_text}")
                except Exception:
                    score_bits = []
                if not score_bits:
                    score_bits = ["score bygger paa momentum, risiko, teknisk timing og verdsettelse"]
                st.markdown(
                    "<div class='v18611-score-explain'><b>Scoreforklaring:</b> "
                    + html.escape("; ".join(score_bits[:4]))
                    + ".</div>",
                    unsafe_allow_html=True,
                )

                warnings = card_decision.get("warnings", [])
                reasons = card_decision.get("reasons", [])

                if warnings:
                    st.markdown(f"<div class='v1863m-quick-action-note'>! {html.escape(str(warnings[0]))}</div>", unsafe_allow_html=True)
                elif reasons:
                    st.markdown(f"<div class='v1863m-quick-action-note'>✅ {html.escape(str(reasons[0]))}</div>", unsafe_allow_html=True)
                else:
                    st.markdown("<div class='v1863m-quick-action-note'>Ingen ekstra varseltekst.</div>", unsafe_allow_html=True)

                # Direkte paper-trading fra kortet
                try:
                    _portfolio = load_portfolio()
                    _owns = ticker in _portfolio.get("positions", {})
                    _action_now = str(card_decision.get("action_now", "VENT")).upper()
                    _conf = int(card_decision.get("confidence", 0) or 0)
                    _btn_key_base = safe_widget_key(f"{title}_{ticker}_{idx}")

                    _paper_gate_v19143 = paper_trading_decision()
                    if latest_price is not None and _action_now == "KJØP NÅ":
                        if _owns:
                            st.caption("📌 Allerede i paper-porteføljen")
                        elif st.button(
                            f"Paper-kjøp {ticker}",
                            key=f"paper_buy_{_btn_key_base}",
                            use_container_width=False,
                            disabled=not _paper_gate_v19143.allowed,
                            help=_paper_gate_v19143.reason if not _paper_gate_v19143.allowed else None,
                        ):
                            _ok, _msg = paper_buy(ticker, latest_price, _conf, f"UI Kjøp nå: {title}")
                            if _ok:
                                st.success(_msg)
                                st.rerun()
                            else:
                                st.warning(_msg)

                    elif latest_price is not None and ("UNNGÅ" in _action_now or "SELL" in _action_now):
                        if _owns and st.button(
                            f"Paper-selg {ticker}",
                            key=f"paper_sell_{_btn_key_base}",
                            use_container_width=False,
                            disabled=not _paper_gate_v19143.allowed,
                            help=_paper_gate_v19143.reason if not _paper_gate_v19143.allowed else None,
                        ):
                            _ok, _msg = paper_sell(ticker, latest_price, f"UI teknisk signal: {_action_now}")
                            if _ok:
                                st.success(_msg)
                                st.rerun()
                            else:
                                st.warning(_msg)
                except Exception as _e:
                    st.caption(f"Paper-knapp ikke tilgjengelig: {_e}")
                _render_candidate_actions_v19022(item, card_decision, title, idx)
                st.markdown("</div>", unsafe_allow_html=True)
