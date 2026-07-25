"""Renderer module extracted from app.py in v19.2.0.

Business calculations remain in the established services; this module owns only
the Streamlit presentation workflow and uses a compatibility context during the
transition away from the legacy monolith.
"""
from __future__ import annotations
from ui.legacy_context import bind_legacy_context

_PRESERVE = {'render_top_picks_control_center_v1863s'}

def render_top_picks_control_center_v1863s(_legacy_context):
    """Top Picks as a first-class AI Kontrollsenter panel."""
    bind_legacy_context(globals(), _legacy_context, preserve=_PRESERVE)
    st.subheader("Top Picks Top Picks")
    st.caption("Bygger Top Picks fra samme universmotor som rangering, analyse, varsler og testpaneler.")

    try:
        from autonomi_core.learning_reporting import load_canonical_top_picks
        canonical_package = load_canonical_top_picks()
    except Exception:
        canonical_package = {}
    canonical_label = "Autonomi – siste gyldige"
    scope_options = ([canonical_label] if canonical_package.get("published") else []) + [NO_UNIVERSE_SELECTION_LABEL, "Analyseflyt input", "Aktivt univers"] + market_scope_options(include_aggregate=True) + ["Watchlist", "Manuell liste"]
    try:
        from autonomi_core.configuration.application_centered import application_centered_enabled
        if application_centered_enabled() and canonical_package.get("published"):
            st.session_state["cc_top_picks_scope_v1863s"] = canonical_label
    except Exception:
        pass
    c1, c2 = st.columns([1.25, 1])
    with c1:
        scope = st.selectbox(
            "Univers / marked",
            scope_options,
            key="cc_top_picks_scope_v1863s",
        )
    with c2:
        input_count = _pipeline_candidate_count_for_stage_v1864("top_picks") if scope == "Analyseflyt input" else 0
        limit_max = max(1, input_count) if input_count > 0 else 100
        limit_min = 1 if limit_max < 5 else 5
        limit_default = min(max(int(max_count or 30), limit_min), limit_max)
        limit_key = "cc_top_picks_limit_v1863s"
        limit_default = _clamp_slider_state_v1864e(limit_key, limit_min, limit_max, limit_default)
        limit = st.slider("Maks kandidater", limit_min, limit_max, limit_default, 1, key=limit_key)
        if input_count > 0:
            st.caption(f"Maks er låst til inputpakken fra Test 3: {input_count} kandidater.")

    manual_text = ""
    if scope == "Manuell liste":
        manual_text = st.text_area(
            "Manuelle tickere",
            value="",
            placeholder="EQNR.OL, VOLV-B.ST, NOVO-B.CO, NOKIA.HE, PETR4.SA",
            key="cc_top_picks_manual_v1863s",
            height=90,
        )

    source_tickers = ([str(x.get("ticker") or "") for x in canonical_package.get("top_picks") or []]
                      if scope == canonical_label else _resolve_control_center_scope_tickers_v1863s(scope, int(limit), manual_text=manual_text))
    storage_scope = re.sub(r"[^A-Za-z0-9]+", "_", scope).strip("_") or "Aktivt"
    storage_key = f"TopPicks_{storage_scope}"
    latest = st.session_state.setdefault("latest_rankings_v148", {})
    if scope == canonical_label:
        storage_key = "TopPicks_Canonical"
        latest[storage_key] = list(canonical_package.get("top_picks") or [])[:int(limit)]
        st.info(
            f"Kanonisk Autonomi-resultat {canonical_package.get('result_id')} · oppdrag {canonical_package.get('mission_id') or '-'} · "
            f"{canonical_package.get('created_at_local') or canonical_package.get('created_at') or '-'}"
        )
        n1, n2, n3 = st.columns(3)
        n1.metric("Nye", len(canonical_package.get("new_candidates") or []))
        n2.metric("Gjentatte", len(canonical_package.get("repeated_candidates") or []))
        n3.metric("Falt ut", len(canonical_package.get("dropped_candidates") or []))
    if source_tickers:
        st.caption(f"Univers: {len(source_tickers)} tickere. Eksempel: {', '.join(source_tickers[:8])}")
        guard = market_guard_summary(source_tickers)
        if guard:
            st.caption(guard)
    else:
        st.info("Velg univers/marked og trykk Kjør Top Picks. Panelet starter tomt og bruker ingen gammel AAPL/STB.OL-cache.")
        return

    run_clicked = False if scope == canonical_label else st.button(
        f"Kjør Top Picks for {scope}",
        key="cc_top_picks_run_v1863s",
        type="primary",
        use_container_width=True,
        disabled=not bool(source_tickers),
    )
    if run_clicked and source_tickers:
        with st.spinner(f"Rangerer {scope} via felles universmotor..."):
            ranked = cached_auto_rank_market(
                storage_key,
                source_tickers,
                max_count=int(limit),
                use_news=False,
                force_manual_fetch=True,
                include_insider=True,
            )
        top_rows = _ranked_for_display(build_top_picks(ranked, min_score=min_top_pick_score, max_items=int(limit)))
        latest[storage_key] = top_rows or []
        st.session_state["dashboard2026_force_rows_v18635"] = list(top_rows or [])
        if scope in MARKET_SCOPE_OPTIONS:
            latest[scope] = ranked or []
        try:
            from services.analysis_pipeline_service import get_analysis_pipeline_service
            from services.state_service import get_state_service
            from services.storage_service import get_storage_service

            get_analysis_pipeline_service(
                state_service=get_state_service(st.session_state),
                storage_service=get_storage_service(),
            ).save_stage_output(
                "top_picks",
                top_rows or [],
                source_label=f"Top Picks {scope}",
                context={"scope": scope, "storage_key": storage_key, "source_count": len(source_tickers)},
                max_items=len(top_rows or []) or 15,
                auto_handoff=True,
            )
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)
        st.success(f"Top Picks ferdig: {len(top_rows or [])} kandidater fra {scope}.")

    top_picks = _ranked_for_display(latest.get(storage_key, []) or [])
    if top_picks:
        # v18.6.36: KPI-kortene ligger over Kontrollsenteret og må kunne lese data
        # som panelet akkurat nå viser. Dette lagrer kun eksisterende rows; ingen ny henting.
        st.session_state["dashboard2026_force_rows_v18635"] = list(top_picks or [])
    buy_now_picks = (_ranked_for_display(list(canonical_package.get("buy_now") or [])[:int(limit)])
                     if scope == canonical_label else _ranked_for_display([x for x in top_picks if is_buy_now_item(x)]))
    # v18.6.38: dashboard header uses these exact rows after this panel renders.
    st.session_state["dashboard2026_visible_rows_v18638"] = list(top_picks or [])
    st.session_state["dashboard2026_buy_now_rows_v18638"] = list(buy_now_picks or [])
    _dashboard2026_store_visible_kpi_snapshot_v18642(top_picks or [], buy_now_picks or [])
    view = st.radio("Visning", ["Top Picks", "Kjøp nå"], horizontal=True, key="cc_top_picks_view_v1863s")
    if top_picks:
        st.markdown(
            f"<div class='v18-dark-row'>Top Picks funnet: <b>{len(top_picks)}</b> | Kjøp nå-signaler: <b>{len(buy_now_picks)}</b>. Kjøp nå er et strengere teknisk timingfilter.</div>",
            unsafe_allow_html=True,
        )
        if scope == canonical_label:
            metadata_rows = [{
                "Ticker": x.get("ticker"), "Oppdrag": x.get("mission_id"),
                "Strategi": x.get("strategy"), "Datakvalitet": x.get("canonical_data_quality"),
                "Hvorfor valgt": x.get("selection_reason"),
                "Endring": x.get("score_delta_since_previous"), "Status": ux_status_label_v19022(x.get("candidate_state"), str(x.get("candidate_state") or "")),
            } for x in top_picks]
            st.dataframe(pd.DataFrame(metadata_rows), use_container_width=True, hide_index=True)

    if view == "Top Picks":
        render_ranking(top_picks, f"Top Picks Top Picks {scope}")
        if top_picks:
            render_analysis(top_picks, f"TopPicks_{storage_scope}")
    else:
        if buy_now_picks:
            saved = save_latest_buy_now_candidates(buy_now_picks, scope)
            st.info(f"{len(saved)} kjøp-nå-kandidater er lagret til Cron-prioritering. Auto-kjøp skjer fortsatt bare via reglene dine.")
            if st.button(f"Paper-kjøp alle Kjøp nå ({len(buy_now_picks)})", key="cc_top_picks_paper_buy_all_v1863s"):
                messages = []
                for item in buy_now_picks:
                    ticker = item.get("ticker")
                    price, _change = get_item_price_change(item)
                    decision = card_decision_for_item(item)
                    if price is None:
                        messages.append(f"{ticker}: mangler pris")
                        continue
                    _ok, msg = paper_buy(ticker, price, int(decision.get("confidence", 0) or 0), f"AI Kontrollsenter Kjøp nå: {scope}")
                    messages.append(msg)
                joined = " | ".join(messages[:8])
                if any("blokkert" in str(m).lower() or "ikke nok" in str(m).lower() or "mangler" in str(m).lower() for m in messages):
                    st.warning(joined)
                else:
                    st.success(joined)
                st.rerun()
            render_ranking(buy_now_picks, f"🟢 Kjøp nå {scope}")
            render_analysis(buy_now_picks, f"KjopNa_{storage_scope}")
        else:
            st.warning(f"Top Picks finnes ({len(top_picks)}), men ingen har grønt teknisk Kjøp nå-signal akkurat nå. Bytt til Top Picks for å se kandidatene.")
