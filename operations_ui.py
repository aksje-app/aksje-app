"""Streamlit operations panel for structured telemetry v19.1.0."""
from __future__ import annotations

from typing import Any


def _local(value: Any) -> str:
    text = str(value or "")
    return text.replace("T", " ")[:19] if text else "-"


def render_operations_trace_panel() -> None:
    import streamlit as st
    from operational_telemetry import list_operational_errors, list_run_traces, source_health_snapshot
    from news_source_registry import SOURCE_REGISTRY

    st.markdown("#### Sporbar drift")
    st.caption("Kildehelse, stabile feilkoder og hele kjøringsforløpet. Panelet starter ingen nye markedskall.")

    sources = source_health_snapshot(SOURCE_REGISTRY)
    traces = list_run_traces(40)
    errors = list_operational_errors(80)
    alerts = [row for row in sources if row.get("alert")]
    running = [row for row in traces if row.get("status") == "RUNNING"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Kilder", len(sources))
    c2.metric("Kildevarsler", len(alerts))
    c3.metric("Aktive kjøringer", len(running))
    c4.metric("Registrerte feil", len(errors))

    with st.expander("Kildehelse", expanded=bool(alerts)):
        rows = []
        for row in sources:
            rows.append({
                "Kilde": row.get("publisher") or row.get("source_id"),
                "Marked": row.get("market") or "-",
                "Helse": row.get("health_score", 0),
                "Status": "Varsel" if row.get("alert") else ("OK" if row.get("last_success_at") else "Ikke testet"),
                "Siste suksess": _local(row.get("last_success_at")),
                "Responstid ms": row.get("last_response_ms"),
                "Feil på rad": row.get("consecutive_failures", 0),
                "Reserve": "Ja" if row.get("fallback_used") else "Nei",
                "Parser": row.get("parser_status") or "-",
                "Artikler": row.get("article_count", 0),
                "Relevante": row.get("relevant_count", 0),
                "Duplikater": row.get("duplicate_count", 0),
                "Kommersielle filtrert": row.get("filtered_commercial_count", 0),
                "Feilkode": row.get("error_code") or "",
                "Siste feil": row.get("last_error") or "",
            })
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("Ingen kildehelse er registrert ennå.")

    with st.expander("Kjøringsspor", expanded=False):
        rows = [{
            "Trace-ID": row.get("trace_id"),
            "Kjøring": row.get("run_id") or "-",
            "Type": row.get("kind") or "-",
            "Trigger": row.get("trigger") or "-",
            "Status": row.get("status") or "-",
            "Steg": row.get("current_stage") or "-",
            "Start": _local(row.get("started_at")),
            "Slutt": _local(row.get("completed_at")),
            "Varighet s": row.get("duration_seconds"),
            "Feilkode": row.get("error_code") or "",
            "Feil": row.get("error") or "",
        } for row in traces]
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("Ingen strukturerte kjøringsspor er registrert ennå.")

    with st.expander("Feil og advarsler", expanded=False):
        rows = [{
            "Tid": _local(row.get("at")),
            "Alvor": row.get("severity"),
            "Feilkode": row.get("error_code") or "-",
            "Komponent": row.get("component"),
            "Steg": row.get("stage") or "-",
            "Kjøring": row.get("run_id") or "-",
            "Kilde": row.get("source_id") or "-",
            "Melding": row.get("message") or "",
            "Feil": row.get("error") or "",
        } for row in reversed(errors)]
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.success("Ingen strukturerte feil er registrert.")
