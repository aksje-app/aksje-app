"""Renderer module extracted from app.py in v19.2.0.

Business calculations remain in the established services; this module owns only
the Streamlit presentation workflow and uses a compatibility context during the
transition away from the legacy monolith.
"""
from __future__ import annotations
from ui.legacy_context import bind_legacy_context

_PRESERVE = {'render_long_engine_control_center_v18653'}

def render_long_engine_control_center_v18653(_legacy_context):
    """Visible UI for Long Engine Alpha.

    v18.6.53 makes the engine testable from the app:
    - run Long Engine Alpha on USA universe
    - show Top Long USA Alpha
    - show overlap against existing Top Picks cache
    """
    bind_legacy_context(globals(), _legacy_context, preserve=_PRESERVE)
    st.subheader("🚀 Long Engine Alpha")
    st.caption(
        "Smart Money-basert Long Alpha. Bruker Ownership, Insider, Earnings og Analyst. "
        "Momentum er bevisst utelatt for å unngå å kopiere dagens Top Picks."
    )

    c1, c2, c3 = st.columns([1.0, 1.0, 1.35])
    with c1:
        market = st.selectbox("Marked", ["USA"], key="long_engine_market_v18653")
    with c2:
        limit = st.slider("Antall kandidater", 5, 50, 20, 5, key="long_engine_limit_v18653")
    with c3:
        st.markdown("**Modell**")
        st.caption("Ownership 35 % · Insider 30 % · Earnings 25 % · Analyst 10 %")

    hcol1, hcol2 = st.columns([1.0, 1.5])
    with hcol1:
        active_horizon = st.radio(
            "Aktiv horisont",
            ["1M", "3M", "6M"],
            index=["1M", "3M", "6M"].index(_long_engine_active_horizon_v18662()),
            horizontal=True,
            key="long_engine_active_horizon_v18662",
            help="Standard er 3M. Rangering og valgt score styres av valgt horisont.",
        )
    with hcol2:
        with st.expander("Terskler / manuell overstyring", expanded=False):
            st.slider("Grønn confidence fra", 50, 100, int(st.session_state.get("long_engine_conf_green_v18662", 85)), 1, key="long_engine_conf_green_v18662")
            st.slider("Gul confidence fra", 0, 99, int(st.session_state.get("long_engine_conf_yellow_v18662", 70)), 1, key="long_engine_conf_yellow_v18662")
            green_t, yellow_t = _long_engine_conf_thresholds_v18662()
            st.caption(f"Aktiv standard: 🟢 ≥ {green_t}% · 🟡 {yellow_t}-{green_t-1}% · 🔴 < {yellow_t}%")

    if market != "USA":
        st.info("v18.6.53 støtter USA først. Norge/Sverige legges inn etter at Alpha er verifisert.")
        return

    try:
        universe_limit = max(int(max_count or 100), int(limit or 20))
    except Exception:
        universe_limit = max(100, int(limit or 20))
    try:
        universe = resolve_universe_tickers(["USA"], max_count=universe_limit)
    except Exception:
        universe = list(globals().get("tickers_us") or [])[:universe_limit]
    universe = [normalize_user_ticker(x) for x in (universe or []) if normalize_user_ticker(x)]

    st.caption(f"USA-univers klart: {len(universe)} tickere. Eksempel: {', '.join(universe[:8]) if universe else '-'}")

    run_clicked = st.button(
        "Kjør Long Engine Alpha",
        key="long_engine_run_alpha_v18653",
        type="primary",
        use_container_width=True,
        disabled=not bool(universe),
    )

    if run_clicked and universe:
        progress_slot = st.empty()
        status_slot = st.empty()
        progress_bar = progress_slot.progress(0)

        def _long_engine_progress_v18663(done: int, total: int, ticker: str | None = None) -> None:
            total = max(1, int(total or 1))
            pct = min(1.0, max(0.0, float(done or 0) / float(total)))
            try:
                progress_bar.progress(pct)
            except Exception:
                pass
            try:
                status_slot.info(f"Kjører Long Engine Alpha: {int(done or 0)} av {total} tickere" + (f" · {ticker}" if ticker else ""))
            except Exception:
                pass

        with st.spinner(f"Kjører Long Engine Alpha på {len(universe)} USA-tickere..."):
            try:
                from engines.long_engine import run_top_long_usa_alpha

                rows = run_top_long_usa_alpha(universe, top_n=int(limit), save=True, progress_callback=_long_engine_progress_v18663)
                st.session_state["long_engine_alpha_rows_v18653"] = list(rows or [])
                try:
                    progress_bar.progress(1.0)
                    status_slot.success(f"Long Engine Alpha ferdig: {len(rows or [])} kandidater.")
                except Exception:
                    pass
                st.success(f"Long Engine Alpha ferdig: {len(rows or [])} kandidater.")
            except Exception as exc:
                st.error(f"Long Engine Alpha feilet: {type(exc).__name__}: {exc}")

    rows = st.session_state.get("long_engine_alpha_rows_v18653") or _long_engine_load_cached_rows_v18653()
    rows = [dict(x) for x in rows if isinstance(x, dict)]
    rows = _long_engine_rank_by_horizon_v18662(rows, _long_engine_active_horizon_v18662())

    if not rows:
        st.info("Ingen Long Engine-resultater ennå. Trykk «Kjør Long Engine Alpha» for å lage Top Long USA Alpha.")
        return

    top = rows[0]
    top_picks_rows = _long_engine_latest_top_picks_rows_v18653(limit=max(20, int(limit or 20)))
    overlap = {}
    try:
        from engines.long_engine import overlap_score

        overlap = overlap_score(rows, top_picks_rows, top_n=min(20, len(rows)))
    except Exception:
        overlap = {"overlap_pct": 0, "overlap_count": 0, "overlap_tickers": []}

    m1, m2, m3, m4 = st.columns(4)
    active_h = _long_engine_active_horizon_v18662()
    m1.metric("Top Long #1", str(top.get("ticker") or "-"))
    m2.metric(f"Score {active_h}", str(top.get("active_horizon_score") or _long_engine_active_horizon_score_v18662(top, active_h) or "-"))
    m3.metric("Kandidater", len(rows))
    m4.metric("Overlap mot Top Picks", f"{float(overlap.get('overlap_pct') or 0):.1f}%")

    if overlap.get("overlap_tickers"):
        st.caption("Overlap-tickere: " + ", ".join(overlap.get("overlap_tickers", [])[:12]))
    elif top_picks_rows:
        st.caption("Ingen overlap i topputvalget mot siste synlige Top Picks-cache.")
    else:
        st.caption("Kjør Top Picks først for å måle overlap mot eksisterende motor.")

    overlap_tickers = set(overlap.get("overlap_tickers") or [])

    # v18.6.56: professional filters before candidate cards/table.
    enriched_rows = []
    for row in rows:
        meta = _long_engine_meta_v18656(row)
        clean = dict(row)
        clean["_country"] = meta.get("country")
        clean["_sector"] = meta.get("sector")
        clean["_risk"] = _long_engine_risk_label_v18654(row)
        clean["_exclusive"] = str(clean.get("ticker") or "").upper().strip() not in overlap_tickers
        enriched_rows.append(clean)

    f1, f2, f3, f4 = st.columns([0.9, 1.1, 0.9, 1.0])
    countries = ["Alle"] + sorted({str(x.get("_country") or "Ukjent") for x in enriched_rows})
    sectors = ["Alle"] + sorted({str(x.get("_sector") or "Ukjent") for x in enriched_rows})
    with f1:
        country_filter = st.selectbox("Land", countries, key="long_engine_country_filter_v18656")
    with f2:
        sector_filter = st.selectbox("Sektor", sectors, key="long_engine_sector_filter_v18656")
    with f3:
        risk_filter = st.selectbox("Risiko", ["Alle", "Lav", "Middels", "Høy"], key="long_engine_risk_filter_v18656")
    with f4:
        exclusive_only = st.checkbox("Kun Long Exclusive", value=False, key="long_engine_exclusive_filter_v18656")

    filtered_rows = []
    for row in enriched_rows:
        if country_filter != "Alle" and row.get("_country") != country_filter:
            continue
        if sector_filter != "Alle" and row.get("_sector") != sector_filter:
            continue
        if risk_filter != "Alle" and row.get("_risk") != risk_filter:
            continue
        if exclusive_only and not row.get("_exclusive"):
            continue
        filtered_rows.append(row)

    st.caption(f"Viser {len(filtered_rows)} av {len(rows)} kandidater etter filter. Rangering styres av aktiv horisont: {_long_engine_active_horizon_v18662()}.")

    view_mode = st.radio(
        "Visning",
        ["Kompakt", "Detalj"],
        horizontal=True,
        key="long_engine_view_mode_v18657",
        help="Kompakt viser flere kandidater raskt. Detalj viser kandidatkort med forklaring.",
    )

    display_df = pd.DataFrame(_long_engine_display_rows_v18653(filtered_rows, overlap_tickers=overlap_tickers))

    if view_mode == "Detalj":
        st.markdown("#### Viktigste kandidater")
        for row in filtered_rows[: min(5, len(filtered_rows))]:
            _long_engine_render_candidate_card_v18654(row, overlap_tickers=overlap_tickers)
    else:
        st.markdown("#### Kompakt beslutningsliste")
        st.caption("Bruk tabellen til rask sortering på valgt score, 1M, 3M, 6M, confidence, sektor og risiko.")

    st.markdown(f"#### Top Long USA Alpha – beslutningstabell ({_long_engine_active_horizon_v18662()})")
    try:
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    except Exception:
        st.write(_long_engine_display_rows_v18653(filtered_rows, overlap_tickers=overlap_tickers))

    if view_mode == "Kompakt" and filtered_rows:
        selected = st.selectbox(
            "Åpne kandidatdetaljer",
            [str(x.get("ticker") or "") for x in filtered_rows],
            key="long_engine_selected_detail_v18657",
        )
        selected_row = next((x for x in filtered_rows if str(x.get("ticker") or "") == selected), None)
        if selected_row:
            _long_engine_render_candidate_card_v18654(selected_row, overlap_tickers=overlap_tickers)

    st.markdown("#### Rapport / eksport")
    st.caption("Print/PDF HTML kan åpnes i nettleser og lagres som PDF fra utskriftsdialogen.")
    basename = f"long_engine_usa_alpha_{datetime.now().strftime('%Y%m%d_%H%M')}"
    e1, e2, e3, e4 = st.columns(4)
    with e1:
        st.download_button("CSV", data=_long_engine_csv_v18654(filtered_rows), file_name=f"{basename}.csv", mime="text/csv", use_container_width=True)
    with e2:
        st.download_button("Excel", data=_long_engine_excel_v18654(filtered_rows), file_name=f"{basename}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    with e3:
        st.download_button("Print/PDF HTML", data=_long_engine_html_report_v18654(filtered_rows, overlap), file_name=f"{basename}_rapport.html", mime="text/html", use_container_width=True)
    with e4:
        st.download_button("JSON", data=json.dumps({"rows": filtered_rows, "overlap": overlap}, indent=2, ensure_ascii=False), file_name=f"{basename}.json", mime="application/json", use_container_width=True)

    with st.expander("Tekniske detaljer / datakobling", expanded=False):
        st.caption("Kun for kontroll og feilsøking. Skjules i normal bruk.")
        st.code(
            "ownership_score.py -> alpha_radar_ownership.py\n"
            "insider_score.py   -> insider.py / FMP fallback\n"
            "earnings_score.py  -> earnings.py / FMP fallback\n"
            "analyst_score.py   -> analyst.py / FMP fallback"
        )
        st.json({
            "weights": {"ownership": 0.35, "insider": 0.30, "earnings": 0.25, "analyst": 0.10},
            "cache": "data/long_engine/top_long_usa_alpha.json",
            "overlap": overlap,
        })
