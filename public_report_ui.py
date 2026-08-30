"""Unauthenticated bridge from a durable token to the browser's raw PDF viewer."""
from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import quote


def _hydrate_static_pdf(token: str, report: dict) -> tuple[Path, str]:
    """Materialise a durable PDF on the web instance before redirecting.

    Render Cron and the Streamlit web service do not share local files.  The
    token request therefore hydrates the web instance from durable storage
    first; only then is Streamlit's enabled static server allowed to serve it.
    """
    from report_delivery import PUBLIC_REPORT_DIR

    safe_token = "".join(ch for ch in str(token or "") if ch.isalnum() or ch in "-_")
    if len(safe_token) < 32:
        raise ValueError("Ugyldig rapporttoken")
    target = PUBLIC_REPORT_DIR / f"public_report_{safe_token}.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".pdf.tmp")
    temporary.write_bytes(bytes(report["data"]))
    temporary.replace(target)
    return target, f"/app/static/reports/{quote(target.name)}"


def _report_landing_actions(static_url: str) -> str:
    """Return a mobile report viewer that always retains an app return path."""
    safe_pdf = escape(str(static_url or ""), quote=True)
    return (
        '<div data-testid="public-report-mobile-shell" style="display:grid;gap:.75rem;margin:.75rem 0 1rem">'
        '<div style="position:sticky;top:0;z-index:20;display:grid;grid-template-columns:1fr 1fr;gap:.5rem;'
        'padding:.5rem;background:#07111f;border:1px solid #334155;border-radius:.65rem">'
        '<a href="/" target="_self" '
        'style="display:block;text-align:center;padding:.8rem .5rem;border-radius:.5rem;'
        'background:#0f766e;color:white;text-decoration:none;font-weight:800">'
        '← Tilbake til programmet</a>'
        f'<a href="{safe_pdf}" target="_blank" rel="noopener noreferrer" '
        'style="display:block;text-align:center;padding:.8rem 1rem;border-radius:.5rem;'
        'background:#0b6efd;color:white;text-decoration:none;font-weight:700">'
        'Åpne PDF i ny fane</a>'
        f'<a href="{safe_pdf}" download target="_blank" rel="noopener noreferrer" '
        'style="grid-column:1/-1;display:block;text-align:center;padding:.8rem 1rem;border-radius:.5rem;'
        'background:#0284c7;color:white;text-decoration:none;font-weight:800">'
        'Last ned / del PDF</a></div>'
        f'<iframe title="Rapportvisning" src="{safe_pdf}#view=FitH" '
        'style="width:100%;height:78vh;min-height:620px;border:1px solid #475569;border-radius:.65rem;background:white" '
        'loading="eager"></iframe>'
        '<a href="/" target="_self" style="display:block;text-align:center;padding:.9rem 1rem;'
        'border:1px solid #789;border-radius:.5rem;color:inherit;text-decoration:none;font-weight:800">'
        'Tilbake til AI Aksje Analyzer</a>'
        '</div>'
    )


def render_public_report(st) -> bool:
    token = str(st.query_params.get("public_report_token") or "").strip()
    if not token:
        return False
    from public_report_store import load_public_pdf

    report = load_public_pdf(token)
    if not report:
        st.error("Rapportlenken er ugyldig eller utløpt.")
        st.stop()
    _, static_url = _hydrate_static_pdf(token, report)
    st.markdown("### 📄 Rapporten er klar")
    st.caption(f"Rapport-ID: {report.get('report_id') or '-'}")
    st.info("Rapporten vises på denne siden. Bruk «Tilbake til programmet» over rapporten for å gå direkte tilbake.")
    action_columns = st.columns(2)
    with action_columns[0]:
        st.link_button("← Tilbake til programmet", "/", width="stretch")
    with action_columns[1]:
        st.link_button("Åpne PDF i ny fane", static_url, width="stretch")
    from mobile_file_delivery import render_mobile_file_delivery
    render_mobile_file_delivery(
        st, url=static_url, filename=str(report.get("filename") or "rapport.pdf"),
        label="Åpne PDF for nedlasting eller deling", mime="application/pdf",
        data=bytes(report["data"]), key=f"public_pdf_{token}",
    )
    st.markdown(_report_landing_actions(static_url), unsafe_allow_html=True)
    return True
