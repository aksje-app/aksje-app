"""Renderer module extracted from app.py in v19.2.0.

Business calculations remain in the established services; this module owns only
the Streamlit presentation workflow and uses a compatibility context during the
transition away from the legacy monolith.
"""
from __future__ import annotations
from ui.legacy_context import bind_legacy_context

_PRESERVE = {'render_paper_trading_dashboard'}

def render_paper_trading_dashboard(_legacy_context):
    bind_legacy_context(globals(), _legacy_context, preserve=_PRESERVE)
    st.subheader("💼 Handel – Paper Trading")
    st.caption("Paper Trading profileres med render-tider. Kjøp og salg lagrer forklaringsgrunnlag for revisjon og replay.")
    st.session_state.pop("paper_manual_override_v1871", None)
    _paper_manual_override_state_v18674a()
    portfolio = load_portfolio()
    _paper_rules = load_rules()
    paper_gate_v19143 = paper_trading_decision()
    if not paper_gate_v19143.allowed:
        st.warning("Paper Trading er slått av i Driftssenter (steg 4). Simulert portefølje beholdes, men nye kjøp og salg er deaktivert.")
        if st.button("🧭 Åpne Driftssenter", key="paper_open_drift_center_v19170rc5", type="primary"):
            st.session_state["active_nav_target_v18674c"] = "drift_center"
            st.session_state["ai_control_center_force_nav_v18663"] = "drift_center"
            st.rerun()
        st.caption("Detaljert blokkdiagnostikk skjules mens hovedfunksjonen er av. Den vises automatisk igjen når Paper Trading aktiveres.")
        return

    status_cols = st.columns([1.0, 1.3, 1.7])
    with status_cols[0]:
        refresh_prices = st.button("Oppdater kurser", key="paper_refresh_prices_v1871", type="primary", width="content")
    with status_cols[1]:
        st.markdown("<div class='v18-dark-row'><b>Ekte handel:</b> Ikke aktiv</div>", unsafe_allow_html=True)
    with status_cols[2]:
        st.markdown("<div class='v18-dark-row'><b>Simulert handel.</b> Ingen ordre sendes til broker.</div>", unsafe_allow_html=True)

    portfolio, refreshed_prices, refresh_errors, refreshed_at = _refresh_paper_portfolio_prices_v1863v(portfolio, fetch_live=bool(refresh_prices), rules=_paper_rules)
    if refresh_prices:
        st.session_state["paper_price_refresh_status_v1863v"] = {"time": refreshed_at, "updated": len(refreshed_prices), "errors": refresh_errors[:8]}
    refresh_status = st.session_state.get("paper_price_refresh_status_v1863v") or {}
    if refresh_status:
        st.caption(f"Sist oppdatert: {refresh_status.get('time', '-')} · kurser oppdatert: {refresh_status.get('updated', 0)}")
        if refresh_status.get("errors"):
            st.warning("Noen kurser ble ikke oppdatert: " + " | ".join(refresh_status.get("errors", [])[:5]))

    latest_prices = {ticker: pos.get("last_price", pos.get("avg_price", pos.get("entry_price", 0))) for ticker, pos in (portfolio.get("positions", {}) or {}).items()}
    # v18.6.75: build position rows once for this render and reuse in Portefølje/Varsler/cards.
    paper_position_rows_cache = paper_position_rows(portfolio, latest_prices, rules=_paper_rules)
    total_value = portfolio_value(portfolio, latest_prices, rules=_paper_rules)
    liq = paper_liquidity_snapshot(portfolio, latest_prices, rules=_paper_rules)
    stats = performance_stats(portfolio, latest_prices, rules=_paper_rules)

    render_compact_stat_grid([
        ("Cash/kjøpekraft", _format_nok_no_decimals_v1827(liq.get('buying_power', portfolio.get('cash', 0)))),
        ("Posisjoner", _format_nok_no_decimals_v1827(liq.get('positions_value', 0))),
        ("Porteføljeverdi", _format_nok_no_decimals_v1827(liq.get('total_value', total_value))),
        ("Urealisert P/L", _format_nok_no_decimals_v1827(liq.get('unrealized_pnl', 0))),
        ("Kjøp i dag", f"{stats.get('buys_today', stats.get('trades_today', 0))}/{stats.get('max_buys_per_day', stats.get('max_trades_per_day', 0))}"),
    ], columns=5)

    active_paper_tab_slug = _paper_trading_active_tab_v18674c()

    if active_paper_tab_slug == "handel":
        _render_paper_rule_badges_v1871(_paper_rules)
        selected_position = st.session_state.get("paper_selected_position_v1863by") or {}
        if selected_position.get("ticker"):
            st.info(
                f"Valgt posisjon: {selected_position.get('ticker')} | siste kurs {float(selected_position.get('price') or 0.0):,.2f} | "
                f"antall {float(selected_position.get('units') or 0.0):,.4f}. Kontroller pris og trykk kjøp eller salg."
            )

        stock_tab, fund_tab = st.tabs(["Aksjer", "Fond / ETF"])
        with stock_tab:
            st.session_state.setdefault("paper_stock_price_input_v1863y", 0.0)
            st.session_state.setdefault("paper_stock_confidence_v1863y", 0)
            st.session_state.setdefault("paper_stock_amount_input_v18615", 10000)

            stock_symbol = str(st.session_state.get("paper_stock_symbol_v1863y", "") or "").strip().upper()
            stock_price_current = float(st.session_state.get("paper_stock_price_input_v1863y", 0.0) or 0.0)
            stock_amount_current = int(st.session_state.get("paper_stock_amount_input_v18615", 10000) or 0)
            stock_confidence_current = int(st.session_state.get("paper_stock_confidence_v1863y", 0) or 0)
            estimated_stock_shares_current = (float(stock_amount_current or 0) / float(stock_price_current or 0)) if float(stock_price_current or 0) > 0 else 0.0
            st.markdown(
                f"""
                <div class="paper-trade-summary-row">
                    <span class="paper-pill">💵 Beløp <b>{float(stock_amount_current or 0):,.0f}</b></span>
                    <span class="paper-pill">💲 Kurs <b>{float(stock_price_current or 0):,.2f}</b></span>
                    <span class="paper-pill">📦 Antall <b>{estimated_stock_shares_current:,.4f}</b></span>
                    <span class="paper-pill">🎯 Confidence <b>{stock_confidence_current}%</b></span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            buy_col, sell_col = st.columns([1, 1], gap="large")
            with buy_col:
                st.markdown("### 🟢 Kjøp aksje")
                with st.container(border=True):
                    r1a, r1b, r1c = st.columns([1.55, 0.62, 0.72], gap="small")
                    with r1a:
                        stock_symbol = st.text_input("Aksjesymbol", value=st.session_state.get("paper_stock_symbol_v1863y", ""), key="paper_stock_symbol_v1863y", on_change=_paper_stock_symbol_changed_v1863ac, placeholder="MEDI, AAPL, SUBC.OL").strip().upper()
                    with r1b:
                        stock_price = st.number_input("Kjøpspris", min_value=0.0, max_value=1_000_000.0, value=float(st.session_state.get("paper_stock_price_input_v1863y", 0.0) or 0.0), step=0.01, key="paper_stock_price_input_v1863y")
                    with r1c:
                        stock_amount = st.number_input("Beløp", min_value=0, max_value=10_000_000, value=int(st.session_state.get("paper_stock_amount_input_v18615", 10000) or 0), step=500, key="paper_stock_amount_input_v18615")
                    pr1, pr2 = st.columns(2, gap="small")
                    with pr1:
                        stock_target_price = st.number_input("Målpris (0 = ingen)", min_value=0.0, max_value=1_000_000.0, value=float(st.session_state.get("paper_stock_target_price_v18678", 0.0) or 0.0), step=0.01, key="paper_stock_target_price_v18678")
                    with pr2:
                        stock_risk_amount = st.number_input("Planlagt risiko, kr (0 = beregn)", min_value=0.0, max_value=10_000_000.0, value=float(st.session_state.get("paper_stock_risk_amount_v18678", 0.0) or 0.0), step=100.0, key="paper_stock_risk_amount_v18678")
                    estimated_stock_shares = (float(stock_amount or 0) / float(stock_price or 0)) if float(stock_price or 0) > 0 else 0.0
                    stock_confidence = int(st.session_state.get("paper_stock_confidence_v1863y", 0) or 0)
                    model_signal_v19143 = str(st.session_state.get("paper_stock_model_signal_v19143", "IKKE BEREGNET") or "IKKE BEREGNET")
                    trade_permission_v19143 = "TILLATT" if paper_gate_v19143.allowed else "BLOKKERT"
                    final_action_v19143 = model_signal_v19143 if paper_gate_v19143.allowed else "INGEN HANDEL"
                    st.markdown(
                        f"""
                        <div class="paper-compact-info-row">
                            <span class="paper-info-badge">📦 Antall: <b>{estimated_stock_shares:,.4f}</b></span>
                            <span class="paper-info-badge">🎯 Confidence: <b>{stock_confidence}%</b></span>
                            <span class="paper-info-badge">🧠 Modellsignal: <b>{model_signal_v19143}</b></span>
                            <span class="paper-info-badge">🔐 Handelstillatelse: <b>{trade_permission_v19143}</b></span>
                            <span class="paper-info-badge">✅ Endelig handling: <b>{final_action_v19143}</b></span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    manual_override = _render_paper_manual_override_readonly_v18674a()
                    existing_stock_pos = (portfolio.get("positions", {}) or {}).get(stock_symbol)
                    if existing_stock_pos:
                        old_units = _safe_float_v18581(existing_stock_pos.get("shares", existing_stock_pos.get("units", 0)), 0.0)
                        old_avg = _safe_float_v18581(existing_stock_pos.get("avg_price", existing_stock_pos.get("entry_price", 0)), 0.0)
                        add_units = estimated_stock_shares
                        new_units = old_units + add_units
                        new_avg = (((old_units * old_avg) + float(stock_amount or 0.0)) / new_units) if new_units else old_avg
                        st.info(f"Eksisterende posisjon funnet: {stock_symbol}. Kjøpet vil øke beholdningen fra {old_units:,.4f} til ca. {new_units:,.4f} aksjer. Estimert ny snittkurs: {new_avg:,.2f}.")
                    _render_paper_buy_decision_context_v18674a(
                        portfolio,
                        _paper_rules,
                        ticker=stock_symbol,
                        price=float(stock_price or 0.0),
                        amount=float(stock_amount or 0.0),
                        confidence=int(stock_confidence or 0),
                        manual_override=manual_override,
                    )
                    a1, a2 = st.columns([0.95, 1.05], gap="small")
                    with a1:
                        st.button("🔎 Hent kurs", key="paper_stock_fetch_price_v1871", width="stretch", on_click=_paper_fetch_stock_price_v1863z)
                    with a2:
                        if _paper_manual_override_state_v18674a() == "REVIEW_ONLY":
                            buy_stock_label_v18674c = "🟡 LEGG TIL VURDERING"
                        elif stock_symbol and stock_symbol in (portfolio.get("positions", {}) or {}):
                            buy_stock_label_v18674c = "🟢 ØK BEHOLDNING"
                        else:
                            buy_stock_label_v18674c = "🟢 PAPER-KJØP"
                        review_only_v19143 = _paper_manual_override_state_v18674a() == "REVIEW_ONLY"
                        buy_stock_disabled_v19143 = (not paper_gate_v19143.allowed) and not review_only_v19143
                        buy_stock_clicked = st.button(
                            buy_stock_label_v18674c,
                            key="paper_stock_buy_v1871",
                            type="primary",
                            width="stretch",
                            disabled=buy_stock_disabled_v19143,
                            help=paper_gate_v19143.reason if buy_stock_disabled_v19143 else None,
                        )
                        if buy_stock_disabled_v19143:
                            st.caption(f"Ingen handel: {paper_gate_v19143.reason}")
                    _render_paper_fetch_status_v1863z("paper_stock_fetch_status_v1863z")
                    if buy_stock_clicked:
                        if not stock_symbol:
                            st.error("Skriv inn aksjesymbol først.")
                        elif float(stock_amount or 0.0) <= 0:
                            st.error("Skriv inn kjøpsbeløp først.")
                        elif float(stock_price or 0.0) <= 0:
                            st.error("Skriv inn kjøpspris eller hent aksjekurs først.")
                        else:
                            manual_override_state = _paper_manual_override_state_v18674a()
                            if manual_override_state == "REVIEW_ONLY":
                                ok, msg = _paper_add_review_candidate_v18674c(
                                    symbol=stock_symbol,
                                    price=float(stock_price),
                                    amount=float(stock_amount or 0.0),
                                    confidence=int(stock_confidence or 0),
                                    asset_type="Aksje",
                                    source="Paper Trading",
                                    reason="REVIEW_ONLY fra Handel-fanen",
                                    extra={"rule_rows": _paper_buy_decision_rows_v18674a(portfolio, _paper_rules, ticker=stock_symbol, price=float(stock_price or 0.0), amount=float(stock_amount or 0.0), confidence=int(stock_confidence or 0), manual_override=manual_override_state)},
                                )
                                if ok:
                                    st.warning(msg)
                                    st.session_state["paper_trading_active_tab_slug_v18674c"] = "hypoteser"
                                    st.session_state["paper_trading_active_tab_label_v18674c"] = "🧪 Hypoteser/Test"
                                    set_global_navigation_state(st, nav="paper_trading", group="Testing og portefolje", panel="Paper Trading og kontroll", tab="hypoteser")
                                    st.rerun()
                                else:
                                    st.error(msg)
                            else:
                                ok, msg = paper_buy(stock_symbol, float(stock_price), int(stock_confidence or 0), "UI paper aksjekjøp", amount_override=float(stock_amount or 0.0), manual_override=manual_override_state, target_price=float(stock_target_price or 0.0), initial_risk_amount=float(stock_risk_amount or 0.0))
                                if ok:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)
                                    _render_paper_block_reason_v1871(msg, portfolio, _paper_rules, stock_symbol, stock_confidence, float(stock_amount or 0.0), manual_override_state)
            with sell_col:
                st.markdown("### 🔴 Selg aksje")
                stock_positions = {k: v for k, v in (portfolio.get("positions", {}) or {}).items() if str((v or {}).get("asset_type", "Aksje")) == "Aksje"}
                with st.container(border=True):
                    s1a, s1b = st.columns([1.45, 0.58], gap="small")
                    with s1a:
                        sell_stock_symbol = st.selectbox("Velg aksje", list(stock_positions.keys()) or ["Ingen"], key="paper_stock_sell_symbol_v1871")
                    with s1b:
                        sell_stock_price = st.number_input("Salgspris", min_value=0.0, max_value=1_000_000.0, value=0.0, step=0.01, key="paper_stock_sell_price_v1871")
                    if sell_stock_symbol != "Ingen":
                        pos = stock_positions.get(sell_stock_symbol, {}) or {}
                        st.markdown(
                            f"""
                            <div class="paper-compact-info-row">
                                <span class="paper-info-badge">📊 Beholdning: <b>{float(pos.get('units') or pos.get('shares') or 0.0):,.4f}</b></span>
                                <span class="paper-info-badge">Snitt: <b>{float(pos.get('avg_price') or pos.get('entry_price') or 0.0):,.2f}</b></span>
                                <span class="paper-info-badge">Sist: <b>{float(pos.get('last_price') or 0.0):,.2f}</b></span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown("<div class='paper-compact-info-row'><span class='paper-info-badge'>Ingen aksjeposisjon valgt</span></div>", unsafe_allow_html=True)
                    sell_stock_pct = st.select_slider("Andel som skal selges", options=[25, 50, 75, 100], value=100, key="paper_stock_sell_pct_v18678", format_func=lambda x: f"{x}%")
                    sell_stock_disabled_v19143 = (sell_stock_symbol == "Ingen") or (not paper_gate_v19143.allowed)
                    sell_stock_clicked = st.button(
                        f"🔴 PAPER-SELG {sell_stock_pct}%",
                        key="paper_stock_sell_v1871",
                        width="stretch",
                        disabled=sell_stock_disabled_v19143,
                        help=paper_gate_v19143.reason if not paper_gate_v19143.allowed else None,
                    )
                    if sell_stock_clicked:
                        price_to_use = float(sell_stock_price or (stock_positions.get(sell_stock_symbol, {}) or {}).get("last_price", 0.0) or (stock_positions.get(sell_stock_symbol, {}) or {}).get("avg_price", 0.0) or 0.0)
                        if price_to_use <= 0:
                            st.error("Skriv inn salgspris først.")
                        else:
                            ok, msg = paper_sell(sell_stock_symbol, price_to_use, "UI paper aksjesalg", sell_pct=float(sell_stock_pct))
                            if ok:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

        with fund_tab:
            st.markdown("### 💼 Fond / ETF")
            st.caption("Fond/ETF ligger i Handel-fanen, men adskilt fra aksjer for å unngå feilkjøp.")
            fund_buy_col, fund_sell_col = st.columns([1.05, 0.95], gap="large")
            with fund_buy_col:
                st.markdown("#### 🟢 Kjøp fond / ETF")
                f1, f2 = st.columns([1.05, 0.95])
                with f1:
                    fund_symbol = st.text_input("Fondnavn / ISIN / ETF-symbol", value=st.session_state.get("paper_fund_symbol_v18545", "VOO"), key="paper_fund_symbol_v18545", on_change=_paper_fund_symbol_changed_v1863ac, placeholder="VOO, QQQ, LU2075955943, DNB Disruptive").strip().upper()
                with f2:
                    fund_asset_type = st.selectbox("Type", ["ETF", "Indeksfond", "Aktivt fond", "Rente-/obligasjonsfond", "High yield-fond", "Pengemarkedsfond", "Kombinasjonsfond", "Fond"], key="paper_fund_type_v18545", on_change=_paper_fund_symbol_changed_v1863ac)
                f3, f4 = st.columns([1.0, 0.8])
                with f3:
                    fund_amount = st.number_input("Beløp", min_value=100, max_value=10_000_000, value=10_000, step=500, key="paper_fund_amount_v18545")
                with f4:
                    fund_currency = st.selectbox("Valuta", ["NOK", "USD", "EUR", "SEK"], key="paper_fund_currency_v18545")
                pf1, pf2 = st.columns([1.0, 1.0])
                with pf1:
                    default_price = float(st.session_state.get("paper_fund_price_v18545", 0.0) or 0.0)
                    fund_price = st.number_input("Pris / NAV", min_value=0.0, max_value=1_000_000.0, value=default_price, step=0.01, key="paper_fund_price_input_v18545")
                with pf2:
                    purchase_mode = st.selectbox("Kjøpstype", ["Engangskjøp", "Månedlig spareplan"], key="paper_fund_purchase_mode_v18545")
                h1, h2 = st.columns([1.0, 1.0])
                with h1:
                    st.button("🔎 Hent pris/NAV", key="paper_fund_fetch_price_v1871", width="stretch", on_click=_paper_fetch_fund_price_v1863z)
                with h2:
                    buy_fund_label_v18674c = "🟡 LEGG TIL VURDERING" if _paper_manual_override_state_v18674a() == "REVIEW_ONLY" else "🟢 PAPER-KJØP FOND/ETF"
                    fund_review_only_v19143 = _paper_manual_override_state_v18674a() == "REVIEW_ONLY"
                    buy_fund_disabled_v19143 = (not paper_gate_v19143.allowed) and not fund_review_only_v19143
                    buy_fund_clicked = st.button(
                        buy_fund_label_v18674c,
                        key="paper_fund_buy_v1871",
                        type="primary",
                        width="stretch",
                        disabled=buy_fund_disabled_v19143,
                        help=paper_gate_v19143.reason if buy_fund_disabled_v19143 else None,
                    )
                _render_paper_fetch_status_v1863z("paper_fund_fetch_status_v1863z")
                if buy_fund_clicked:
                    price_to_use = float(fund_price or st.session_state.get("paper_fund_price_v18545", 0.0) or 0.0)
                    manual_override_state = _paper_manual_override_state_v18674a()
                    if manual_override_state == "REVIEW_ONLY":
                        ok, msg = _paper_add_review_candidate_v18674c(
                            symbol=fund_symbol,
                            price=price_to_use,
                            amount=float(fund_amount or 0),
                            confidence=75,
                            asset_type=fund_asset_type,
                            currency=fund_currency,
                            source="Paper Trading Fond/ETF",
                            reason=f"REVIEW_ONLY fra Handel-fanen: {purchase_mode}",
                            extra={"purchase_mode": purchase_mode},
                        )
                        if ok:
                            st.warning(msg)
                            st.session_state["paper_trading_active_tab_slug_v18674c"] = "hypoteser"
                            st.session_state["paper_trading_active_tab_label_v18674c"] = "🧪 Hypoteser/Test"
                            set_global_navigation_state(st, nav="paper_trading", group="Testing og portefolje", panel="Paper Trading og kontroll", tab="hypoteser")
                            st.rerun()
                        else:
                            st.error(msg)
                    else:
                        ok, msg = paper_buy_instrument(fund_symbol, price_to_use, float(fund_amount or 0), asset_type=fund_asset_type, confidence=75, reason=f"UI paper {fund_asset_type}: {purchase_mode}", currency=fund_currency, nav_date=datetime.now().date().isoformat(), purchase_mode=purchase_mode, manual_override=manual_override_state)
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                            _render_paper_block_reason_v1871(msg, portfolio, _paper_rules, fund_symbol, 75, float(fund_amount or 0.0), _paper_manual_override_state_v18674a())
                if purchase_mode == "Månedlig spareplan":
                    if st.button("💾 Lagre spareplan", key="paper_fund_save_plan_v1871", width="stretch"):
                        plan = {"symbol": fund_symbol, "asset_type": fund_asset_type, "monthly_amount": float(fund_amount or 0), "currency": fund_currency, "created_at": datetime.now().isoformat(timespec="seconds"), "status": "Simulert"}
                        portfolio.setdefault("fund_savings_plans", []).append(plan)
                        save_portfolio(portfolio)
                        st.success("Spareplan lagret som simulering ✅")
                        st.rerun()
            with fund_sell_col:
                st.markdown("#### 🔴 Selg fond / ETF")
                fund_positions = {k: v for k, v in (portfolio.get("positions", {}) or {}).items() if str((v or {}).get("asset_type", "Aksje")) in {"ETF", "Fond", "Indeksfond", "Aktivt fond", "Rente-/obligasjonsfond", "High yield-fond", "Pengemarkedsfond", "Kombinasjonsfond"}}
                sell_symbol = st.selectbox("Velg fond/ETF", list(fund_positions.keys()) or ["Ingen"], key="paper_fund_sell_symbol_v1871")
                sell_price = st.number_input("Salgspris/NAV", min_value=0.0, max_value=1_000_000.0, value=0.0, step=0.01, key="paper_fund_sell_price_v1871")
                sell_amount = st.number_input("Salgsbeløp (0 = alt)", min_value=0, max_value=10_000_000, value=0, step=500, key="paper_fund_sell_amount_v1871")
                if st.button("🔴 PAPER-SELG FOND/ETF", key="paper_fund_sell_v1871", width="stretch", disabled=(sell_symbol == "Ingen")):
                    price_to_use = float(sell_price or (fund_positions.get(sell_symbol, {}) or {}).get("last_price", 0.0) or 0.0)
                    ok, msg = paper_sell_instrument(sell_symbol, price_to_use, sell_amount=None if int(sell_amount or 0) <= 0 else float(sell_amount), reason="UI paper fond/ETF-salg", currency=fund_currency, nav_date=datetime.now().date().isoformat())
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                plans = list(portfolio.get("fund_savings_plans") or [])
                if plans:
                    st.markdown("#### Simulerte spareplaner")
                    for plan in plans[-5:]:
                        st.markdown(f"<div class='v18-dark-row'><b>{html.escape(str(plan.get('symbol','-')))}</b> · {html.escape(str(plan.get('asset_type','Fond')))} · {float(plan.get('monthly_amount') or 0):,.0f} {html.escape(str(plan.get('currency','NOK')))} / mnd · {html.escape(str(plan.get('status','Simulert')))}</div>", unsafe_allow_html=True)

    if active_paper_tab_slug == "portefolje":
        st.markdown("### 📊 Portefølje")
        _render_paper_portfolio_control_overview_v1868(portfolio, latest_prices, stats, total_value, position_rows=paper_position_rows_cache, rules=_paper_rules)
        pro_summary = portfolio_professional_summary(portfolio)
        pc1, pc2, pc3, pc4 = st.columns(4)
        pc1.metric("Investert", f"{pro_summary['invested']:,.0f}")
        pc2.metric("Kontanter", f"{pro_summary['cash']:,.0f}")
        pc3.metric("Kapitalbinding", f"{pro_summary['capital_binding_pct']:.1f}%")
        pc4.metric("Ledig kapital", f"{pro_summary['free_capital_pct']:.1f}%")
        _render_manual_paper_nav_update_v18621(portfolio)
        with st.expander("Juster startverdier / porteføljeverdi", expanded=False):
            c_start, c_value = st.columns(2)
            with c_start:
                new_start_cash = st.number_input("Startkapital / reset-verdi", min_value=10_000, max_value=50_000_000, value=int(float(_paper_rules.get("start_cash", 100000))), step=10_000, key="paper_start_cash_v1871")
            with c_value:
                new_portfolio_value = st.number_input("Porteføljeverdi", min_value=0, max_value=50_000_000, value=int(float(total_value)), step=10_000, key="paper_total_value_v1871")
            c_apply, c_reset = st.columns(2)
            with c_apply:
                if st.button("Bruk porteføljeverdi", key="paper_apply_total_value_v1871", width="content"):
                    target_value = _safe_float_v18581(new_portfolio_value, total_value)
                    current_cash = _safe_float_v18581(portfolio.get("cash", 0), 0.0)
                    positions_value = _safe_float_v18581(liq.get("positions_value", 0), 0.0)
                    new_cash = round(target_value - positions_value, 2)
                    if new_cash < 0:
                        st.error(f"Kan ikke sette porteføljeverdi lavere enn åpne posisjoner ({positions_value:,.0f}).")
                    else:
                        portfolio["cash"] = new_cash
                        _paper_rules["start_cash"] = _safe_float_v18581(new_start_cash, current_cash)
                        save_rules(_paper_rules)
                        save_portfolio(portfolio)
                        st.success(f"Porteføljeverdi oppdatert til ca. {target_value:,.0f}. Cash/kjøpekraft er nå ca. {new_cash:,.0f} ✅")
                        st.rerun()
            with c_reset:
                if st.button("Reset til startkapital", key="restore_reset_paper_portfolio_v1871", width="content"):
                    target_start = _safe_float_v18581(new_start_cash, 100000.0)
                    _paper_rules["start_cash"] = target_start
                    save_rules(_paper_rules)
                    reset_portfolio(target_start)
                    st.success(f"Paper portfolio nullstilt til {target_start:,.0f} ✅")
                    st.rerun()
        st.markdown("#### Åpne posisjoner")
        if portfolio.get("positions", {}):
            _render_paper_positions_cards_v1863ac(portfolio, latest_prices, position_rows=paper_position_rows_cache, rules=_paper_rules)
            with st.expander("Exit-simulering (påvirker ikke handler)", expanded=False):
                sim_symbol = st.selectbox("Posisjon", list((portfolio.get("positions", {}) or {}).keys()), key="paper_exit_sim_symbol_v18678")
                sim_rows = exit_simulation((portfolio.get("positions", {}) or {}).get(sim_symbol, {}))
                if sim_rows:
                    st.dataframe(pd.DataFrame(sim_rows), width="stretch", hide_index=True)
        else:
            st.info("Ingen åpne paper trading-posisjoner.")
        st.markdown("#### Handelslogg")
        trades = portfolio.get("trades", [])
        if trades:
            st.dataframe(pd.DataFrame(paper_trade_display_rows(trades, limit=50)), width="stretch", hide_index=True)
        else:
            st.info("Ingen handler ennå.")

    if active_paper_tab_slug == "regler":
        st.markdown("### ⚙ Trading-regler")
        _render_paper_rule_badges_v1871(_paper_rules)
        st.caption("Hold- og cooldown-regler er synlige her. Systemet skiller hardvalidering, myke regler, manuell overstyring, vurderingskø og trailing stop per posisjon.")
        _render_paper_manual_override_control_v18674a()
        _render_paper_trading_control_toolbar_v1864p()
        render_auto_trading_workspace()
        render_trading_rules_workspace()

    if active_paper_tab_slug == "varsler":
        st.markdown("### 🔔 Varsler")
        _render_paper_trailing_stop_alerts_v18674d(portfolio, latest_prices, position_rows=paper_position_rows_cache, rules=_paper_rules)
        st.divider()
        render_paper_alert_control_workspace_v18611()
        st.markdown("#### 💰 Klar for ekte trading senere")
        st.info("Systemet er strukturert for paper trading med risikoregler. Ekte handel er IKKE aktivert.")

    if active_paper_tab_slug == "hypoteser":
        st.markdown("### 🧪 Hypoteser / Test")
        st.caption("Inkommende paper-hypoteser, testgrunnlag og gule flagg ligger her for å redusere støy i Handel-fanen.")
        _render_paper_review_queue_v18674c(load_portfolio(), _paper_rules)
        st.divider()
        try:
            paper_flow_rows = _pipeline_input_rows_from_package_v1864h(_analysis_pipeline_service_v1863bw().load_stage_input("paper_trading"))
        except Exception:
            paper_flow_rows = []
        _render_incoming_paper_hypotheses_v1868(paper_flow_rows, portfolio)
