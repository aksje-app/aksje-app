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
    """Return mobile-safe actions without replacing the application tab."""
    safe_pdf = escape(str(static_url or ""), quote=True)
    return (
        '<div style="display:grid;gap:.75rem;margin:.75rem 0 1rem">'
        f'<a href="{safe_pdf}" target="_blank" rel="noopener noreferrer" '
        'style="display:block;text-align:center;padding:.8rem 1rem;border-radius:.5rem;'
        'background:#0b6efd;color:white;text-decoration:none;font-weight:700">'
        'Åpne PDF i ny fane</a>'
        '<a href="/" target="_self" '
        'style="display:block;text-align:center;padding:.8rem 1rem;border-radius:.5rem;'
        'border:1px solid #789;color:inherit;text-decoration:none;font-weight:700">'
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
    st.info("Rapporten åpnes ikke automatisk. Programfanen beholdes slik at du alltid kan gå tilbake.")
    st.markdown(_report_landing_actions(static_url), unsafe_allow_html=True)
    st.download_button(
        "Last ned PDF til enheten", data=report["data"], file_name=str(report.get("filename") or "rapport.pdf"),
        mime="application/pdf", type="primary", width="stretch",
    )
    return True
