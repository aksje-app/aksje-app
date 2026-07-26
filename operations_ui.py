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

    with st.expander("Planlegger og Pushover", expanded=True):
        try:
            from market_intelligence import load_jobs, schedule_timeline, REPORT_NOTIFICATION_RECEIPTS_PATH, _read
            jobs = load_jobs()
            job_rows = []
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            for job in jobs:
                timeline = schedule_timeline(job, now)
                job_rows.append({
                    "Jobb": job.name,
                    "Aktiv": "Ja" if job.enabled else "Nei",
                    "Tidssone": job.timezone_name,
                    "Neste planlagte": _local(timeline.get("next_planned_utc")),
                    "Siste planlagte": _local(job.last_scheduled_at),
                    "Siste forsøk": _local(job.last_attempted_at),
                    "Siste fullført": _local(job.last_run_at),
                    "Status": job.last_status or "-",
                    "Pushover": job.last_notification_status or "-",
                })
            if job_rows:
                st.dataframe(job_rows, use_container_width=True, hide_index=True)
            else:
                st.info("Ingen planlagte rapportjobber er konfigurert.")
            try:
                from scheduled_runner import load_unattended_state
                unattended = load_unattended_state()
            except Exception:
                unattended = {}
            u1, u2, u3, u4 = st.columns(4)
            u1.metric("Uovervåket runner", unattended.get("state") or "Ikke registrert")
            u2.metric("Siste start", _local(unattended.get("started_at")))
            u3.metric("Siste fullført", _local(unattended.get("completed_at")))
            u4.metric("Prosess", unattended.get("process") or "-")
            if not unattended:
                st.warning("Ingen heartbeat fra scheduled_runner er funnet. Kontroller at Render Cron-tjenesten er opprettet fra render.yaml.")
            elif unattended.get("state") == "FAILED":
                st.error(f"Siste uovervåkede schedulerkjøring feilet: {unattended.get('error') or 'ukjent feil'}")
            receipts = _read(REPORT_NOTIFICATION_RECEIPTS_PATH, {})
            receipt_rows = []
            if isinstance(receipts, dict):
                for row in list(receipts.values())[-100:][::-1]:
                    receipt_rows.append({
                        "Rapport/kjøring": row.get("run_id") or row.get("report_id") or "-",
                        "Rapport": row.get("report_label") or row.get("report_type") or "-",
                        "Opprettet": _local(row.get("created_at")),
                        "Planlagt": _local(row.get("scheduled_at")),
                        "Forsøkt": _local(row.get("attempted_at")),
                        "Sendt": _local(row.get("sent_at")),
                        "Status": row.get("status") or ("SENT" if row.get("sent") else "SKIPPED"),
                        "Utløst av": row.get("triggered_by") or "-",
                        "Detalj": row.get("detail") or row.get("skipped_reason") or "",
                    })
            if receipt_rows:
                st.markdown("##### Siste Pushover-leveranser")
                st.dataframe(receipt_rows, use_container_width=True, hide_index=True)
            else:
                st.caption("Ingen rapportvarsler er registrert ennå.")
        except Exception as exc:
            st.warning(f"Planlegger- og varslingsstatus kunne ikke leses: {exc}")

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
