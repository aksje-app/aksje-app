from __future__ import annotations

import csv
import io
from typing import Any, Mapping, Sequence

import streamlit as st

from ai_candidate_navigation import open_ai_candidate_test
from nbim_radar import (
    annotate_nbim_changes,
    build_nbim_overlay,
    build_nbim_priority_views,
    compare_nbim_holdings,
    format_nbim_amount,
    nbim_changes_to_display_rows,
    nbim_file_diagnostics,
    nbim_group_summary,
    nbim_changes_to_json,
    read_nbim_csv_bytes,
    save_nbim_overlay,
)


def _changes_to_csv(changes: Sequence[Mapping[str, Any]]) -> bytes:
    fields = [
        "ticker",
        "matched_ticker",
        "ticker_match_quality",
        "ticker_match_alias",
        "name",
        "country",
        "region",
        "sector",
        "change_type",
        "change_pct",
        "change_metric",
        "previous_value",
        "current_value",
        "market_value_nok",
        "market_value_usd",
        "ownership_pct",
        "voting_pct",
        "shares",
        "shares_change_pct",
        "ownership_pct_change_pct",
        "voting_pct_change_pct",
        "market_value_nok_change_pct",
        "market_value_usd_change_pct",
        "nbim_priority_score",
        "nbim_conviction_score",
        "nbim_signals",
        "radar_overlap",
        "nbim_priority_reason",
        "watchlist_reason",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in changes:
        writer.writerow(dict(row))
    return buffer.getvalue().encode("utf-8-sig")


def _nbim_report_html(changes: Sequence[Mapping[str, Any]]) -> bytes:
    rows = nbim_changes_to_display_rows(changes)[:250]
    if rows:
        cols = list(rows[0].keys())
        head = "".join(f"<th>{col}</th>" for col in cols)
        body = "".join(
            "<tr>" + "".join(f"<td>{row.get(col, '')}</td>" for col in cols) + "</tr>"
            for row in rows
        )
        table = f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    else:
        table = "<p>Ingen rader.</p>"
    return f"""<!doctype html>
<html lang="no">
<head>
  <meta charset="utf-8">
  <title>Oljefond/NBIM - rapport</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 28px; color: #111827; }}
    button {{ border: 1px solid #0284c7; background: #0ea5e9; color: white; border-radius: 8px; padding: 9px 14px; font-weight: 700; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 5px 7px; text-align: left; font-size: 12px; vertical-align: top; }}
    th {{ background: #f3f4f6; }}
    @media print {{ button {{ display:none; }} body {{ margin:16mm; }} tr {{ page-break-inside: avoid; }} }}
  </style>
</head>
<body>
  <button onclick="window.print()">Skriv ut / lagre som PDF</button>
  <h1>Oljefond/NBIM - rapport</h1>
  <p>Rader: {len(changes or [])}</p>
  {table}
</body>
</html>""".encode("utf-8")


def _render_change_table(rows: Sequence[Mapping[str, Any]]) -> None:
    display_rows = nbim_changes_to_display_rows(rows)
    if display_rows:
        st.dataframe(display_rows, use_container_width=True, hide_index=True)
    else:
        st.info("Ingen rader i denne visningen.")


def _latest_radar_tickers_from_state() -> set[str]:
    latest: Mapping[str, Any] | None = None
    latest_key = ""
    for key, value in st.session_state.items():
        if not str(key).startswith("alpha_radar_last_result_"):
            continue
        if not isinstance(value, Mapping) or not value.get("candidates"):
            continue
        created = str(value.get("created_at") or "")
        marker = f"{created}|{key}"
        if marker >= latest_key:
            latest_key = marker
            latest = value
    tickers: set[str] = set()
    for row in (latest or {}).get("candidates") or []:
        if not isinstance(row, Mapping):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        if ticker:
            tickers.add(ticker)
    return tickers


def render_nbim_radar_panel() -> None:
    st.subheader("Oljefond Radar")
    st.caption(
        "Importer offentlig NBIM/Oljefondet-beholdning som CSV. Panelet finner nye posisjoner, okninger, reduksjoner og exits, "
        "og lagrer et ticker-overlay som Beslutningsgrunnlag kan bruke sammen med Alpha Radar/Early Warning."
    )

    c1, c2 = st.columns(2)
    with c1:
        current_file = st.file_uploader("Nyeste NBIM CSV", type=["csv", "txt"], key="nbim_current_csv_v1863bd")
    with c2:
        previous_file = st.file_uploader("Forrige NBIM CSV (valgfri)", type=["csv", "txt"], key="nbim_previous_csv_v1863bd")

    progress = st.progress(0, text="Venter på filer")
    if not current_file:
        st.info("Last opp nyeste beholdningsfil for aa analysere. Ingen nettverkskall kjores automatisk.")
        return

    try:
        progress.progress(20, text="Leser ny NBIM-fil")
        current_rows = read_nbim_csv_bytes(current_file.getvalue())
        progress.progress(40, text="Leser forrige NBIM-fil")
        previous_rows = read_nbim_csv_bytes(previous_file.getvalue()) if previous_file else []
    except Exception as exc:
        progress.progress(0, text="Stoppet")
        st.warning(f"Kunne ikke lese NBIM-fil: {exc}")
        return

    if not current_rows:
        progress.progress(0, text="Stoppet")
        st.warning(
            "NBIM-filen ble lest, men inneholder 0 beholdningsrader. Bruk NBIM Aksjer CSV, for eksempel eq_YYYYMMDD.csv."
        )
        return

    progress.progress(60, text="Sammenligner beholdninger")
    changes = compare_nbim_holdings(previous_rows, current_rows)
    radar_tickers = _latest_radar_tickers_from_state()
    progress.progress(80, text="Matcher tickere / bygger overlay")
    annotated_changes = annotate_nbim_changes(changes, radar_tickers=sorted(radar_tickers))
    overlay = build_nbim_overlay(annotated_changes)
    diagnostics = nbim_file_diagnostics(current_rows, overlay)
    summary = {
        "Ny": sum(1 for row in annotated_changes if row.get("change_type") == "Ny"),
        "Okt": sum(1 for row in annotated_changes if row.get("change_type") == "Okt"),
        "Redusert": sum(1 for row in annotated_changes if row.get("change_type") == "Redusert"),
        "Solgt ut": sum(1 for row in annotated_changes if row.get("change_type") == "Solgt ut"),
        "Uendret": sum(1 for row in annotated_changes if row.get("change_type") == "Uendret"),
    }
    radar_overlap_count = sum(1 for row in annotated_changes if row.get("radar_overlap"))
    current_value_nok = sum(
        (row.get("market_value_nok") or 0.0)
        for row in annotated_changes
        if row.get("change_type") != "Solgt ut"
    )
    progress.progress(100, text=f"Klar: {len(current_rows)} rader, {len(changes)} endringer, {len(overlay)} ticker-matcher")

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Ny", summary["Ny"])
    m2.metric("Okt", summary["Okt"])
    m3.metric("Redusert", summary["Redusert"])
    m4.metric("Solgt ut", summary["Solgt ut"])
    m5.metric("Ticker-overlay", len(overlay))
    m6.metric("Radar-overlap", radar_overlap_count)
    st.caption(
        f"NBIM-fil lest: {diagnostics['rows']} rader. Matchet {diagnostics['matched_tickers']} tickere mot appens tickerregister. "
        f"Umatchede NBIM-rader: {diagnostics['unmatched_rows']}. Aktiv markedsverdi i listen: {format_nbim_amount(current_value_nok, 'NOK')}."
    )
    if current_rows and not overlay:
        st.warning("NBIM-data er lest, men 0 tickere ble matchet. Sjekk om filen er aksje-CSV og om ticker-/navnregisteret dekker markedene.")

    st.caption(
        "Tabellene under er sortert for beslutningsverdi. Raa current_value er oversatt per rad: eierandel/stemmeandel vises som %, "
        "aksjer som aksjer og markedsverdi som NOK/USD."
    )
    views = build_nbim_priority_views(annotated_changes, limit=75)
    tab_names = [
        "Topp signaler",
        "Overbevisning",
        "NBIM-watchlist",
        "Storste beholdninger",
        "Storste nye kjop",
        "Storste okninger",
        "Akkumulering svakhet",
        "Redusert med restverdi",
        "Solgt ut",
        "Hoy eierandel",
        "Stemmerett-avvik",
        "Unmatched verdi",
        "Radar-overlap",
        "Ticker-match",
        "Land/sektor",
        "Radata",
    ]
    tabs = st.tabs(tab_names)
    for tab, name in zip(tabs, tab_names):
        with tab:
            if name == "Land/sektor":
                st.markdown("**Land**")
                st.dataframe(nbim_group_summary(annotated_changes, "country")[:25], use_container_width=True, hide_index=True)
                st.markdown("**Sektor**")
                st.dataframe(nbim_group_summary(annotated_changes, "sector")[:25], use_container_width=True, hide_index=True)
            else:
                _render_change_table(views.get(name, []))

    st.caption("NBIM-markedsverdi kan flytte seg med kurs og valuta. Endring i aksjer/eierandel er sterkere signal der filen inneholder dette.")

    b1, b2, b3, b4 = st.columns(4)
    with b1:
        if st.button("Lagre NBIM-overlay", key="nbim_save_overlay_v1863bd", type="primary", use_container_width=True, disabled=not overlay):
            saved = save_nbim_overlay(overlay)
            st.success(f"Lagret NBIM-overlay for {saved} tickere.")
    with b2:
        st.download_button(
            "Last ned CSV",
            data=_changes_to_csv(annotated_changes),
            file_name="olje-fond-radar-endringer.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with b3:
        st.download_button(
            "Last ned JSON",
            data=nbim_changes_to_json(annotated_changes),
            file_name="olje-fond-radar-endringer.json",
            mime="application/json",
            use_container_width=True,
        )
    with b4:
        st.download_button(
            "Print/PDF HTML",
            data=_nbim_report_html(annotated_changes),
            file_name="olje-fond-radar-rapport.html",
            mime="text/html",
            use_container_width=True,
        )

    matched_tickers = list(dict.fromkeys(
        str(row.get("matched_ticker") or row.get("ticker") or "").strip().upper()
        for row in annotated_changes
        if str(row.get("matched_ticker") or row.get("ticker") or "").strip()
    ))
    a1, a2 = st.columns(2)
    with a1:
        if st.button("Send alle matchede til AI Kandidattest", key="nbim_send_all_ai_candidate_v1864o", use_container_width=True, disabled=not matched_tickers):
            open_ai_candidate_test(tickers=matched_tickers, market="Alle")
            st.rerun()
    with a2:
        if st.button("Åpne AI Kandidattest med Oljefond/NBIM", key="nbim_open_ai_candidate_source_v1864o", use_container_width=True, disabled=not matched_tickers):
            open_ai_candidate_test(source="Oljefond/NBIM", market="Alle")
            st.rerun()


__all__ = ["render_nbim_radar_panel"]
