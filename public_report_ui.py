"""Unauthenticated bridge from a durable token to the browser's raw PDF viewer."""
from __future__ import annotations

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
    # The component is used only as a zero-height browser redirect.  PDF
    # rendering itself is native to the browser and has no streamlit-pdf
    # dependency.  A visible fallback remains for restrictive mobile browsers.
    try:
        st.components.v1.html(
            f'<script>window.top.location.replace({static_url!r});</script>',
            height=0,
        )
    except Exception:
        pass
    st.markdown("### 📄 Rapporten er klar")
    st.caption(f"Rapport-ID: {report.get('report_id') or '-'}")
    st.link_button("Åpne PDF direkte", static_url, type="primary", width="stretch")
    st.download_button(
        "Last ned PDF", data=report["data"], file_name=str(report.get("filename") or "rapport.pdf"),
        mime="application/pdf", type="primary", width="stretch",
    )
    return True
