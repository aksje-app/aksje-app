"""Minimal unauthenticated renderer for an unlisted durable report token."""
from __future__ import annotations


def render_public_report(st) -> bool:
    token = str(st.query_params.get("public_report_token") or "").strip()
    if not token:
        return False
    from public_report_store import load_public_pdf

    report = load_public_pdf(token)
    if not report:
        st.error("Rapportlenken er ugyldig eller utløpt.")
        st.stop()
    st.markdown("### 📄 AI Aksje Analyzer · rapport")
    st.caption(f"Rapport-ID: {report.get('report_id') or '-'}")
    if hasattr(st, "pdf"):
        st.pdf(report["data"], height=900)
    else:
        st.info("PDF-visning støttes ikke av denne Streamlit-versjonen. Bruk nedlastingsknappen under.")
    st.download_button(
        "Last ned PDF", data=report["data"], file_name=str(report.get("filename") or "rapport.pdf"),
        mime="application/pdf", type="primary", width="stretch",
    )
    return True
