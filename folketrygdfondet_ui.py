from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

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


def _infer_as_of_from_name(filename: str) -> str:
    match = re.search(r"(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)", str(filename or ""))
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    year = re.search(r"\b(20\d{2})\b", str(filename or ""))
    return f"{year.group(1)}-12-31" if year else ""


def _matched_tickers(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    tickers = [
        str(row.get("matched_ticker") or row.get("ticker") or "").strip().upper()
        for row in rows or []
    ]
    return list(dict.fromkeys(ticker for ticker in tickers if ticker))


def _filter_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    query: str = "",
    match_filter: str = "Alle",
) -> list[dict[str, Any]]:
    needle = str(query or "").strip().lower()
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, Mapping):
            continue
        ticker = str(row.get("matched_ticker") or row.get("ticker") or "").strip().upper()
        if match_filter == "Ticker-match" and not ticker:
            continue
        if match_filter == "Mangler ticker-match" and ticker:
            continue
        if needle:
            blob = " ".join(
                str(row.get(key) or "")
                for key in (
                    "ticker",
                    "matched_ticker",
                    "name",
                    "country",
                    "isin",
                    "sheet",
                    "ticker_match_alias",
                    "ticker_match_quality",
                )
            ).lower()
            if needle not in blob:
                continue
        out.append(dict(row))
    return out


def _render_exports(rows: Sequence[Mapping[str, Any]]) -> None:
    st.markdown("#### Eksport / print")
    e1, e2, e3, e4 = st.columns(4)
    with e1:
        st.download_button(
            "CSV",
            data=folketrygdfondet_rows_to_csv(rows),
            file_name="folketrygdfondet-import.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with e2:
        st.download_button(
            "JSON snapshot",
            data=folketrygdfondet_rows_to_json(rows),
            file_name="folketrygdfondet-import.json",
            mime="application/json",
            use_container_width=True,
        )
    with e3:
        st.download_button(
            "Print/PDF HTML",
            data=build_folketrygdfondet_report_html(rows),
            file_name="folketrygdfondet-rapport.html",
            mime="text/html",
            use_container_width=True,
        )
    with e4:
        st.download_button(
            "Last ned PDF",
            data=build_folketrygdfondet_report_pdf(rows),
            file_name="folketrygdfondet-rapport.pdf",
            mime="application/pdf",
            use_container_width=True,
        )


def _render_ai_candidate_actions(rows: Sequence[Mapping[str, Any]]) -> None:
    st.markdown("#### Send til AI Kandidattest")
    tickers = _matched_tickers(rows)
    if not tickers:
        st.info("Ingen ticker-match ennå. Importen er lagret, men AI Kandidattest trenger matchede tickere for direkte kjøring.")
        return

    selected = st.multiselect(
        "Velg tickere til AI Kandidattest",
        tickers,
        default=tickers[: min(60, len(tickers))],
        key="folketrygdfondet_ai_candidate_tickers_v1864p",
        help="Valgte tickere åpnes i AI Kandidattest som manuell liste med Folketrygdfondet-evidens fra lagret overlay.",
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button(
            "Send valgte til AI Kandidattest",
            key="folketrygdfondet_send_selected_ai_candidate_v1864p",
            type="primary",
            use_container_width=True,
            disabled=not selected,
        ):
            open_ai_candidate_test(tickers=selected, market="Alle")
            st.rerun()
    with c2:
        if st.button(
            "Send alle matchede til AI Kandidattest",
            key="folketrygdfondet_send_all_ai_candidate_v1864p",
            use_container_width=True,
            disabled=not tickers,
        ):
            open_ai_candidate_test(tickers=tickers, market="Alle")
            st.rerun()
    with c3:
        if st.button(
            "Åpne AI Kandidattest med Folketrygdfondet",
            key="folketrygdfondet_open_ai_candidate_source_v1864p",
            use_container_width=True,
            disabled=not tickers,
        ):
            open_ai_candidate_test(source="Folketrygdfondet", market="Alle")
            st.rerun()


def _render_saved_rows(rows: Sequence[Mapping[str, Any]], *, label: str) -> list[dict[str, Any]]:
    st.markdown(f"#### {label}")
    f1, f2 = st.columns([1.3, 0.8])
    with f1:
        query = st.text_input(
            "Søk i Folketrygdfondet-import",
            key="folketrygdfondet_search_v1864p",
            placeholder="Ticker, selskap, land, ISIN eller ark",
        )
    with f2:
        match_filter = st.selectbox(
            "Ticker-match",
            ["Alle", "Ticker-match", "Mangler ticker-match"],
            key="folketrygdfondet_match_filter_v1864p",
        )
    visible_rows = _filter_rows(rows, query=query, match_filter=match_filter)
    tickers = _matched_tickers(visible_rows)
    c1, c2, c3 = st.columns(3)
    c1.metric("Viste rader", len(visible_rows))
    c2.metric("Tickere med match", len(tickers))
    c3.metric("Umatchede", sum(1 for row in visible_rows if not (row.get("matched_ticker") or row.get("ticker"))))
    if visible_rows:
        st.dataframe(folketrygdfondet_display_rows(visible_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Ingen rader matcher filteret.")
    return visible_rows


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
        key="folketrygdfondet_xls_upload_v1864p",
        help="Velg filen først, kontroller forhåndsvisningen og trykk Importer og lagre.",
    )

    parsed_rows: list[dict[str, Any]] = []
    overlay: dict[str, dict[str, Any]] = {}
    if uploaded:
        try:
            rows = read_folketrygdfondet_xls_bytes(uploaded.getvalue(), uploaded.name)
            parsed_rows = annotate_folketrygdfondet_holdings(rows)
            overlay = build_folketrygdfondet_overlay(parsed_rows)
        except Exception as exc:
            st.warning(str(exc))
            st.info("Filen er bare valgt i nettleseren. Den blir ikke lagret før importen er lest og du trykker Importer og lagre.")

    if uploaded and parsed_rows:
        c1, c2, c3 = st.columns(3)
        c1.metric("Input Folketrygdfondet", f"{len(parsed_rows)} rader")
        c2.metric("Ticker-match", len(_matched_tickers(parsed_rows)))
        c3.metric("Klar til AI Kandidattest", f"{len(overlay)} tickere")
        source_as_of = st.text_input(
            "Kildedato/as-of for Folketrygdfondet-filen",
            value=_infer_as_of_from_name(uploaded.name),
            key="folketrygdfondet_source_as_of_v1864s",
            placeholder="2025-12-31",
            help="Bruk datoen beholdningsfilen gjelder for. AI Kandidattest bruker denne til ferskhetsvurdering.",
        )
        st.dataframe(folketrygdfondet_display_rows(parsed_rows), use_container_width=True, hide_index=True)
        if not overlay:
            st.warning("Importen har 0 ticker-match. Du kan likevel lagre radene, søke i dem og bruke dem som kildegrunnlag senere.")
        if st.button(
            "Importer og lagre Folketrygdfondet",
            key="folketrygdfondet_save_overlay_v1864p",
            type="primary",
            use_container_width=True,
            disabled=not parsed_rows,
        ):
            saved = save_folketrygdfondet_overlay(overlay, parsed_rows, source_as_of=source_as_of, source_file=uploaded.name)
            st.success(f"Lagret Folketrygdfondet-import med {len(parsed_rows)} rader og {saved} ticker-match.")
            st.rerun()
    elif uploaded and not parsed_rows:
        st.info("Filen er valgt, men ingen beholdningsrader ble lest. Kontroller at arket har selskapsnavn, ticker eller ISIN.")

    snapshot = load_folketrygdfondet_snapshot()
    saved_rows = list(snapshot.get("rows") or [])
    active_rows = parsed_rows or saved_rows
    if not active_rows:
        st.info("Importer data først. Da åpnes søk, tabell, eksport, print/PDF og sending til AI Kandidattest.")
        return

    label = "Forhåndsvisning fra valgt fil" if parsed_rows else "Lagret Folketrygdfondet-import"
    visible_rows = _render_saved_rows(active_rows, label=label)
    if visible_rows:
        _render_exports(visible_rows)
        _render_ai_candidate_actions(visible_rows)


__all__ = ["render_folketrygdfondet_panel"]
