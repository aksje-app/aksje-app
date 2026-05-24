from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

import streamlit as st

from finansavisen_bjellesau import (
    PERIOD_OPTIONS,
    build_finansavisen_priority_views,
    build_finansavisen_report,
    build_finansavisen_report_html,
    build_finansavisen_report_pdf,
    decision_rows_from_finansavisen,
    finansavisen_status,
    finansavisen_transactions_to_csv,
    finansavisen_transactions_to_json,
    format_nok,
    infer_period_from_filename,
    load_finansavisen_transactions,
    merge_finansavisen_transactions,
    parse_finansavisen_transaction_xlsx,
    save_finansavisen_transactions,
    sort_periods,
    summarize_finansavisen_transactions,
    sync_finansavisen_actors_to_registry,
)
from decision_engine import DECISION_QUEUE_KEY, add_decision_rows


PERIOD_LABELS = {
    "1D": "1D - ferskeste handler",
    "1U": "1U - siste uke",
    "1M": "1M - kort trend",
    "3M": "3M - trend",
    "6M": "6M - hovedvindu",
    "YTD": "YTD",
    "1Y": "1Y",
    "3Y": "3Y",
    "ALLE": "ALLE - historikk/arkiv",
}

PERIOD_PRESETS = {
    "Fersk": ["1D", "1U", "1M"],
    "Trend": ["1M", "3M", "6M"],
    "Lang": ["6M", "YTD", "1Y", "3Y", "ALLE"],
    "Alle": list(PERIOD_OPTIONS),
}


def _period_index(period: str) -> int:
    try:
        return list(PERIOD_OPTIONS).index(period)
    except Exception:
        return list(PERIOD_OPTIONS).index("6M")


def _file_period_key(upload: Any, idx: int) -> str:
    name = str(getattr(upload, "name", f"file_{idx}") or f"file_{idx}")
    size = int(getattr(upload, "size", 0) or 0)
    safe_name = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:70] or f"file_{idx}"
    return f"finansavisen_bjellesau_period_{safe_name}_{size}_{idx}_v1863bl"


def _filter_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    periods: Sequence[str],
    query: str = "",
    match_filter: str = "Alle",
) -> list[dict[str, Any]]:
    wanted = {str(period) for period in periods}
    needle = str(query or "").strip().lower()
    out: list[dict[str, Any]] = []
    for row in rows:
        row_periods = {str(period) for period in (row.get("source_periods") or [row.get("source_period")])}
        if wanted and not (row_periods & wanted):
            continue
        if needle:
            blob = " ".join(
                str(row.get(key) or "")
                for key in ("investor", "stock_name", "matched_ticker", "performed_by", "source_file")
            ).lower()
            if needle not in blob:
                continue
        ticker = str(row.get("matched_ticker") or "").strip()
        if match_filter == "Radar-klar ticker" and not ticker:
            continue
        if match_filter == "Mangler ticker-match" and ticker:
            continue
        out.append(dict(row))
    return out


def _periods_from_rows(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    return sort_periods([period for row in rows for period in (row.get("source_periods") or [row.get("source_period")])])


def _render_report_method(summary: Mapping[str, Any], visible_rows: Sequence[Mapping[str, Any]]) -> None:
    views = build_finansavisen_priority_views(visible_rows, limit=25)
    st.markdown("**Rapport og metode**")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Kjøp", f"{summary.get('buy_count', 0)}", format_nok(summary.get("buy_value_nok")))
    m2.metric("Salg", f"{summary.get('sell_count', 0)}", format_nok(summary.get("sell_value_nok")))
    m3.metric("Ticker-match", summary.get("matched_tickers", 0))
    m4.metric("Netto", format_nok(summary.get("net_value_nok")))
    st.caption(
        "Score forklares i tabellen. Den vekter ferskhet, verdi, netto kjøp/salg, antall bjellesauer, gjentatte handler og ticker-match."
    )
    report_choice = st.selectbox(
        "Rapportvisning",
        ["Sammendrag", "Topp kjøp", "Topp salg", "Flere bjellesauer samme aksje", "Ticker-match", "Rådata"],
        key="finansavisen_bjellesau_report_view_v1863bm",
    )
    view_map = {
        "Sammendrag": views.get("Score per aksje", []),
        "Topp kjøp": views.get("Storste kjop", []),
        "Topp salg": views.get("Storste salg", []),
        "Flere bjellesauer samme aksje": views.get("Flere bjellesauer samme aksje", []),
        "Ticker-match": views.get("Ticker-match", []),
        "Rådata": views.get("Raadata", []),
    }
    data = view_map.get(report_choice) or []
    if data:
        st.dataframe(data, use_container_width=True, hide_index=True)
    else:
        st.info("Ingen rader i denne rapportvisningen.")


def _summary_cards(status: Mapping[str, Any]) -> None:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Handler", status.get("rows", 0))
    c2.metric("Investorer", status.get("investors", 0))
    c3.metric("Aksjer", status.get("stocks", 0))
    c4.metric("Ticker-overlay", status.get("overlay_tickers", status.get("matched_tickers", 0)))
    c5.metric("Netto", format_nok(status.get("net_value_nok")))
    st.caption(
        f"Perioder: {', '.join(status.get('periods') or []) or '-'} | "
        f"datoer: {status.get('first_date') or '-'} til {status.get('last_date') or '-'} | "
        f"kjop {status.get('buy_count', 0)} / salg {status.get('sell_count', 0)}. "
        "Ingen Excel-parse eller nettverkskall kjores ved vanlige menyvalg."
    )


def _render_view(rows: Sequence[Mapping[str, Any]]) -> None:
    views = build_finansavisen_priority_views(rows, limit=120)
    view_name = st.selectbox(
        "Visning",
        list(views),
        key="finansavisen_bjellesau_view_v1863bk",
        help="Visningene bygges fra lagret lokalt snapshot. Ingen nye kall mot Finansavisen.",
    )
    data = views.get(view_name) or []
    if data:
        st.dataframe(data, use_container_width=True, hide_index=True)
    else:
        st.info("Ingen rader i denne visningen.")


def render_finansavisen_bjellesau_panel() -> None:
    st.subheader("Finansavisen Bjellesauer")
    st.caption(
        "Importer XLSX-filer fra Finansavisen Bjellesauer. Panelet holder 1D/1M/3M/6M/ALLE adskilt, "
        "dedupliserer handler og lager et lokalt evidenslag for Alpha Radar og Early Warning."
    )
    st.info(
        "Robusthetsregel: Excel leses bare naar du trykker Importer. Radarene bruker deretter ferdiglagret lokalt snapshot."
    )

    uploads = st.file_uploader(
        "Importer Finansavisen transaction.xlsx",
        type=["xlsx"],
        accept_multiple_files=True,
        key="finansavisen_bjellesau_import_v1863bk",
        help="Last ned Bjellesauer -> Siste handler som XLSX for 1D, 1M, 3M, 6M og/eller ALLE. Velg perioden for hver fil under.",
    )

    file_periods: dict[int, str] = {}
    if uploads:
        st.caption("Velg riktig periode for hver fil. Dette brukes i score og rapport, og filene kan importeres samlet.")
        for idx, upload in enumerate(uploads):
            guessed = infer_period_from_filename(upload.name)
            period = st.selectbox(
                f"Periode for {upload.name}",
                list(PERIOD_OPTIONS),
                index=_period_index(guessed),
                format_func=lambda value: PERIOD_LABELS.get(value, value),
                key=_file_period_key(upload, idx),
            )
            file_periods[idx] = period

    c1, c2, c3 = st.columns([1.2, 1.0, 1.0])
    with c1:
        update_actors = st.checkbox(
            "Oppdater Aktorregister fra import",
            value=True,
            key="finansavisen_bjellesau_sync_actors_v1863bk",
            help="Legger investorene inn som Bjellesau-rolle, uten aa slette eksisterende roller som Insider watch.",
        )
    with c2:
        import_clicked = st.button(
            "Importer valgte filer",
            key="finansavisen_bjellesau_import_button_v1863bk",
            type="primary",
            use_container_width=True,
            disabled=not bool(uploads),
        )
    with c3:
        if st.button("Synk lagret import til Aktorregister", key="finansavisen_bjellesau_sync_saved_v1863bk", use_container_width=True):
            count = sync_finansavisen_actors_to_registry(load_finansavisen_transactions())
            st.success(f"Aktorregister oppdatert: {count} rader lagret.")

    if import_clicked:
        progress = st.progress(0, text="Starter Finansavisen-import")
        existing = load_finansavisen_transactions()
        imported_rows = []
        total = max(1, len(uploads or []))
        for idx, upload in enumerate(uploads or [], start=1):
            upload_index = idx - 1
            progress.progress(int(upload_index / total * 70), text=f"Leser {upload.name}")
            try:
                imported_rows.extend(
                    parse_finansavisen_transaction_xlsx(
                        upload.getvalue(),
                        upload.name,
                        source_period=file_periods.get(upload_index),
                    )
                )
            except Exception as exc:
                st.warning(f"Kunne ikke lese {upload.name}: {exc}")
        progress.progress(75, text="Dedupliserer handler")
        merged = merge_finansavisen_transactions(existing, imported_rows)
        progress.progress(88, text="Lagrer lokalt snapshot")
        saved = save_finansavisen_transactions(merged)
        actor_count = None
        if update_actors:
            progress.progress(94, text="Oppdaterer Aktorregister")
            actor_count = sync_finansavisen_actors_to_registry(merged)
        progress.progress(100, text="Klar")
        msg = f"Importerte {len(imported_rows)} rader, lagret {saved} unike handler."
        if actor_count is not None:
            msg += f" Aktorregister: {actor_count} rader."
        st.success(msg)

    status = finansavisen_status()
    _summary_cards(status)

    rows = load_finansavisen_transactions()
    if not rows:
        st.info("Ingen Finansavisen-data lagret ennaa. Last opp transaction.xlsx og trykk Importer valgte filer.")
        return

    f1, f2, f3 = st.columns([1.35, 1.0, 0.9])
    with f1:
        query = st.text_input(
            "Sok i importerte handler",
            key="finansavisen_bjellesau_search_v1863bk",
            placeholder="Investor, aksje, ticker eller holdingselskap",
        )
    with f2:
        preset = st.radio(
            "Periodehurtigvalg",
            list(PERIOD_PRESETS),
            horizontal=True,
            key="finansavisen_bjellesau_period_preset_v1863bm",
            help="Fersk=1D/1U/1M, Trend=1M/3M/6M, Lang=6M/YTD/1Y/3Y/ALLE.",
        )
    with f3:
        match_filter = st.selectbox(
            "Ticker-match",
            ["Alle", "Radar-klar ticker", "Mangler ticker-match"],
            key="finansavisen_bjellesau_match_filter_v1863bm",
        )
    available_periods = _periods_from_rows(rows) or list(PERIOD_OPTIONS)
    preset_periods = [period for period in PERIOD_PRESETS.get(preset, list(PERIOD_OPTIONS)) if period in available_periods]
    selected_periods = st.multiselect(
        "Perioder",
        list(PERIOD_OPTIONS),
        default=preset_periods or available_periods,
        format_func=lambda value: PERIOD_LABELS.get(value, value),
        key=f"finansavisen_bjellesau_period_filter_v1863bm_{preset}",
    )
    visible_rows = _filter_rows(rows, periods=selected_periods, query=query, match_filter=match_filter)
    st.caption(f"Viser {len(visible_rows)} av {len(rows)} lagrede handler. Periodene beholdes separat i eksport og scoring.")
    _render_view(visible_rows)

    decision_options = [
        row.get("Ticker")
        for row in build_finansavisen_priority_views(visible_rows, limit=40).get("Ticker-match", [])
        if row.get("Ticker")
    ]
    decision_defaults = decision_options[: min(8, len(decision_options))]
    selected_decision_tickers = st.multiselect(
        "Send til Beslutningsgrunnlag",
        decision_options,
        default=decision_defaults,
        key="finansavisen_bjellesau_decision_tickers_v1863bm",
        max_selections=min(20, len(decision_options)) if decision_options else None,
    )

    c_exp1, c_exp2, c_exp3, c_exp4, c_decision, c_clear = st.columns([1, 1, 1, 1, 1.25, 1.25])
    with c_exp1:
        st.download_button(
            "Last ned CSV",
            data=finansavisen_transactions_to_csv(visible_rows),
            file_name="finansavisen-bjellesauer-transaksjoner.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with c_exp2:
        st.download_button(
            "Last ned JSON",
            data=finansavisen_transactions_to_json(visible_rows),
            file_name="finansavisen-bjellesauer-transaksjoner.json",
            mime="application/json",
            use_container_width=True,
        )
    with c_exp3:
        st.download_button(
            "Print/PDF HTML",
            data=build_finansavisen_report_html(visible_rows),
            file_name="finansavisen-bjellesauer-rapport.html",
            mime="text/html",
            use_container_width=True,
        )
    with c_exp4:
        st.download_button(
            "Last ned PDF",
            data=build_finansavisen_report_pdf(visible_rows),
            file_name="finansavisen-bjellesauer-rapport.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    with c_decision:
        if st.button(
            "Send valgte til Beslutningsgrunnlag",
            key="finansavisen_bjellesau_send_decision_v1863bm",
            use_container_width=True,
            disabled=not selected_decision_tickers,
        ):
            decision_rows = decision_rows_from_finansavisen(visible_rows, selected_decision_tickers, limit=20)
            current = st.session_state.get(DECISION_QUEUE_KEY, [])
            st.session_state[DECISION_QUEUE_KEY] = add_decision_rows(current, decision_rows)
            st.success(f"Sendte {len(decision_rows)} Finansavisen-signaler til Beslutningsgrunnlag.")
    with c_clear:
        confirm_clear = st.checkbox("Bekreft tomming", key="finansavisen_bjellesau_confirm_clear_v1863bk")
        if st.button(
            "Tom Finansavisen-data",
            key="finansavisen_bjellesau_clear_v1863bk",
            use_container_width=True,
            disabled=not confirm_clear,
        ):
            save_finansavisen_transactions([])
            st.success("Finansavisen-data er tomt.")
            st.rerun()

    with st.expander("Rapport / metode", expanded=False):
        _render_report_method(summarize_finansavisen_transactions(visible_rows), visible_rows)


__all__ = ["render_finansavisen_bjellesau_panel"]
