from __future__ import annotations

import csv
import io
from typing import Any, Mapping, Sequence

import streamlit as st

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
        "nbim_priority_score",
        "nbim_priority_reason",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in changes:
        writer.writerow(dict(row))
    return buffer.getvalue().encode("utf-8-sig")


def _render_change_table(rows: Sequence[Mapping[str, Any]]) -> None:
    display_rows = nbim_changes_to_display_rows(rows)
    if display_rows:
        st.dataframe(display_rows, use_container_width=True, hide_index=True)
    else:
        st.info("Ingen rader i denne visningen.")


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

    if not current_file:
        st.info("Last opp nyeste beholdningsfil for aa analysere. Ingen nettverkskall kjores automatisk.")
        return

    try:
        current_rows = read_nbim_csv_bytes(current_file.getvalue())
        previous_rows = read_nbim_csv_bytes(previous_file.getvalue()) if previous_file else []
    except Exception as exc:
        st.warning(f"Kunne ikke lese NBIM-fil: {exc}")
        return

    if not current_rows:
        st.warning(
            "NBIM-filen ble lest, men inneholder 0 beholdningsrader. Bruk NBIM Aksjer CSV, for eksempel eq_YYYYMMDD.csv."
        )
        return

    changes = compare_nbim_holdings(previous_rows, current_rows)
    annotated_changes = annotate_nbim_changes(changes)
    overlay = build_nbim_overlay(annotated_changes)
    diagnostics = nbim_file_diagnostics(current_rows, overlay)
    summary = {
        "Ny": sum(1 for row in annotated_changes if row.get("change_type") == "Ny"),
        "Okt": sum(1 for row in annotated_changes if row.get("change_type") == "Okt"),
        "Redusert": sum(1 for row in annotated_changes if row.get("change_type") == "Redusert"),
        "Solgt ut": sum(1 for row in annotated_changes if row.get("change_type") == "Solgt ut"),
        "Uendret": sum(1 for row in annotated_changes if row.get("change_type") == "Uendret"),
    }
    current_value_nok = sum(
        (row.get("market_value_nok") or 0.0)
        for row in annotated_changes
        if row.get("change_type") != "Solgt ut"
    )

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Ny", summary["Ny"])
    m2.metric("Okt", summary["Okt"])
    m3.metric("Redusert", summary["Redusert"])
    m4.metric("Solgt ut", summary["Solgt ut"])
    m5.metric("Ticker-overlay", len(overlay))
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
        "Storste beholdninger",
        "Storste nye kjop",
        "Storste okninger",
        "Redusert med restverdi",
        "Solgt ut",
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

    b1, b2, b3 = st.columns(3)
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


__all__ = ["render_nbim_radar_panel"]
