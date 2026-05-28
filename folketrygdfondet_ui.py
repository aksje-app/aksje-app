from __future__ import annotations

import streamlit as st

from ai_candidate_navigation import open_ai_candidate_test
from folketrygdfondet import (
    annotate_folketrygdfondet_holdings,
    build_folketrygdfondet_overlay,
    build_folketrygdfondet_report_html,
    build_folketrygdfondet_report_pdf,
    folketrygdfondet_display_rows,
    folketrygdfondet_rows_to_csv,
    folketrygdfondet_rows_to_json,
    folketrygdfondet_status,
    load_folketrygdfondet_snapshot,
    read_folketrygdfondet_xls_bytes,
    save_folketrygdfondet_overlay,
)


def _matched_tickers(rows: list[dict]) -> list[str]:
    tickers = [
        str(row.get("matched_ticker") or row.get("ticker") or "").strip().upper()
        for row in rows or []
    ]
    return list(dict.fromkeys(ticker for ticker in tickers if ticker))


def _render_exports(rows: list[dict]) -> None:
    e1, e2, e3, e4 = st.columns(4)
    with e1:
        st.download_button(
            "CSV",
            data=folketrygdfondet_rows_to_csv(rows),
            file_name="folketrygdfondet-import.csv",
            mime="text/csv",
            use_container_width=True,
            disabled=not rows,
        )
    with e2:
        st.download_button(
            "JSON snapshot",
            data=folketrygdfondet_rows_to_json(rows),
            file_name="folketrygdfondet-import.json",
            mime="application/json",
            use_container_width=True,
            disabled=not rows,
        )
    with e3:
        st.download_button(
            "Print/PDF HTML",
            data=build_folketrygdfondet_report_html(rows),
            file_name="folketrygdfondet-rapport.html",
            mime="text/html",
            use_container_width=True,
            disabled=not rows,
        )
    with e4:
        st.download_button(
            "Last ned PDF",
            data=build_folketrygdfondet_report_pdf(rows),
            file_name="folketrygdfondet-rapport.pdf",
            mime="application/pdf",
            use_container_width=True,
            disabled=not rows,
        )


def _render_ai_candidate_actions(rows: list[dict]) -> None:
    tickers = _matched_tickers(rows)
    selected = st.multiselect(
        "Velg tickere til AI Kandidattest",
        tickers,
        default=tickers[: min(60, len(tickers))],
        key="folketrygdfondet_ai_candidate_tickers_v1864o",
        help="Valgte tickere åpnes i AI Kandidattest som manuell liste med Folketrygdfondet-evidens fra lagret overlay.",
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button(
            "Send valgte til AI Kandidattest",
            key="folketrygdfondet_send_selected_ai_candidate_v1864o",
            type="primary",
            use_container_width=True,
            disabled=not selected,
        ):
            open_ai_candidate_test(tickers=selected, market="Alle")
            st.rerun()
    with c2:
        if st.button(
            "Send alle matchede til AI Kandidattest",
            key="folketrygdfondet_send_all_ai_candidate_v1864o",
            use_container_width=True,
            disabled=not tickers,
        ):
            open_ai_candidate_test(tickers=tickers, market="Alle")
            st.rerun()
    with c3:
        if st.button(
            "Åpne AI Kandidattest med Folketrygdfondet",
            key="folketrygdfondet_open_ai_candidate_source_v1864o",
            use_container_width=True,
            disabled=not tickers,
        ):
            open_ai_candidate_test(source="Folketrygdfondet", market="Alle")
            st.rerun()


def render_folketrygdfondet_panel() -> None:
    st.subheader("Folketrygdfondet")
    st.caption(
        "Importer Folketrygdfondet-beholdninger fra .xls/.xlsx. Dataene lagres som institusjonelt eier-overlay "
        "som AI Kandidattest kan bruke som kildeevidens."
    )

    status = folketrygdfondet_status()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Lagret overlay", f"{status.get('overlay_tickers', 0)} tickere")
    m2.metric("Lagrede rader", status.get("rows", 0))
    m3.metric("Umatchede", status.get("unmatched_rows", 0))
    m4.metric("Sist importert", status.get("updated_at") or "Ikke importert")

    uploaded = st.file_uploader(
        "Importer Folketrygdfondet XLS/XLSX",
        type=["xls", "xlsx"],
        key="folketrygdfondet_xls_upload_v1864k",
    )

    parsed_rows: list[dict] = []
    overlay: dict = {}
    if uploaded:
        try:
            rows = read_folketrygdfondet_xls_bytes(uploaded.getvalue(), uploaded.name)
            parsed_rows = annotate_folketrygdfondet_holdings(rows)
            overlay = build_folketrygdfondet_overlay(parsed_rows)
        except Exception as exc:
            st.warning(str(exc))
            st.info("Filen er bare valgt i nettleseren. Den blir ikke lagret før importen er lest og du trykker Importer og lagre.")

    active_rows = parsed_rows or list((load_folketrygdfondet_snapshot().get("rows") or []))
    active_overlay = overlay or dict((load_folketrygdfondet_snapshot().get("overlay") or {}))

    if uploaded and parsed_rows:
        c1, c2, c3 = st.columns(3)
        c1.metric("Input Folketrygdfondet", f"{len(parsed_rows)} rader")
        c2.metric("Ticker-match", len(_matched_tickers(parsed_rows)))
        c3.metric("Klar til AI Kandidattest", f"{len(overlay)} tickere")
        st.dataframe(folketrygdfondet_display_rows(parsed_rows), use_container_width=True, hide_index=True)
        if st.button(
            "Importer og lagre Folketrygdfondet",
            key="folketrygdfondet_save_overlay_v1864o",
            type="primary",
            use_container_width=True,
            disabled=not overlay,
        ):
            saved = save_folketrygdfondet_overlay(overlay, parsed_rows)
            st.success(f"Lagret Folketrygdfondet-overlay for {saved} tickere. AI Kandidattest kan bruke kilden nå.")
            st.rerun()
    elif active_rows:
        st.success(f"Viser lagret Folketrygdfondet-import med {len(active_overlay)} tickere i overlay.")
        st.dataframe(folketrygdfondet_display_rows(active_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Last opp Folketrygdfondet XLS/XLSX og trykk Importer og lagre. Først da blir kilden tilgjengelig i AI Kandidattest.")

    st.markdown("#### Eksport / print")
    _render_exports(active_rows)
    st.markdown("#### Send til AI Kandidattest")
    _render_ai_candidate_actions(active_rows)


__all__ = ["render_folketrygdfondet_panel"]
