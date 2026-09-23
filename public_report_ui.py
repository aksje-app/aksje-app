"""Unauthenticated bridge from a durable token to the browser's raw PDF viewer."""
from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
import os


_RETURN_NAV_TARGETS = {
    "dashboard", "portfolio", "long_engine", "autonomy", "reports",
    "jobs", "approvals", "paper_trading", "fx_alerts", "alerts",
    "drift_center", "system",
}


def _safe_return_nav(value: str) -> str:
    nav = str(value or "").strip().lower().replace("-", "_")
    return nav if nav in _RETURN_NAV_TARGETS else "reports"


def _report_return_href(value: str) -> str:
    return "/?" + urlencode({"aa_nav": _safe_return_nav(value)})


def _absolute_report_return_url(value: str) -> str:
    """Build the same-origin absolute URL required by mobile PDF viewers."""
    nav = _safe_return_nav(value)
    for candidate in (os.getenv("RENDER_EXTERNAL_URL"), os.getenv("REPORT_PUBLIC_BASE_URL")):
        parsed = urlsplit(str(candidate or "").strip())
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return urlunsplit((parsed.scheme, parsed.netloc, "/", urlencode({"aa_nav": nav}), ""))
    # Production's canonical origin is also the documented fallback used by
    # report delivery when Render does not expose its service URL locally.
    return "https://aksje-app.onrender.com/?" + urlencode({"aa_nav": nav})


def with_report_return(url: str, return_to: str) -> str:
    """Attach an allowlisted in-app return route to a public report URL."""
    parsed = urlsplit(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["return_to"] = _safe_return_nav(return_to)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


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
    from pdf_mobile_return import add_pdf_return_links

    try:
        stamped = add_pdf_return_links(
            bytes(report["data"]),
            return_url=_absolute_report_return_url(str(report.get("_return_to") or "reports")),
        )
    except Exception:
        # Keep legacy or minimally valid archived PDFs readable.  Newly
        # generated application PDFs are covered by the PDF regression test.
        stamped = bytes(report["data"])
    temporary.write_bytes(stamped)
    temporary.replace(target)
    return target, f"/app/static/reports/{quote(target.name)}"


def _hydrate_static_file(token: str, artifact: dict) -> tuple[Path, str]:
    from report_delivery import PUBLIC_REPORT_DIR
    safe="".join(ch for ch in str(token or "") if ch.isalnum() or ch in "-_"); suffix=Path(str(artifact.get("filename") or "nedlasting.bin")).suffix.lower()
    if len(safe)<32 or suffix not in {".json",".txt",".zip"}: raise ValueError("Ugyldig filtoken")
    target=PUBLIC_REPORT_DIR/f"public_file_{safe}{suffix}"; target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_suffix(f"{suffix}.tmp"); temporary.write_bytes(bytes(artifact["data"])); temporary.replace(target)
    return target,f"/app/static/reports/{quote(target.name)}"


def _report_landing_actions(static_url: str, *, return_href: str = "/?aa_nav=reports") -> str:
    """Return a mobile report viewer that always retains an app return path."""
    safe_pdf = escape(str(static_url or ""), quote=True)
    safe_return = escape(str(return_href or "/?aa_nav=reports"), quote=True)
    return (
        '<div data-testid="public-report-mobile-shell" style="display:grid;gap:.75rem;margin:.75rem 0 1rem">'
        '<div style="position:sticky;top:0;z-index:20;display:grid;grid-template-columns:1fr 1fr;gap:.5rem;'
        'padding:.5rem;background:#07111f;border:1px solid #334155;border-radius:.65rem">'
        f'<a href="{safe_return}" target="_self" '
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
        '</div>'
    )


def render_public_report(st) -> bool:
    return_to = str(st.query_params.get("return_to") or "reports")
    return_href = _report_return_href(return_to)
    file_token=str(st.query_params.get("public_file_token") or "").strip()
    if file_token:
        from public_report_store import load_public_file
        artifact=load_public_file(file_token)
        if not artifact: st.error("Fillenken er ugyldig eller utløpt."); st.stop()
        _,static_url=_hydrate_static_file(file_token,artifact)
        st.markdown("### 📦 Filen er klar")
        st.link_button("← Tilbake til programmet", return_href, width="stretch")
        st.info("Åpne filen i ny fane for deling. Returknappen tar deg tilbake til riktig programområde.")
        from mobile_file_delivery import render_mobile_file_delivery
        render_mobile_file_delivery(st,url=static_url,filename=str(artifact.get("filename") or "nedlasting"),label="Åpne fil for nedlasting eller deling",mime=str(artifact.get("mime") or "application/octet-stream"),data=bytes(artifact["data"]),key=f"public_file_{file_token}")
        return True
    token = str(st.query_params.get("public_report_token") or "").strip()
    if not token:
        return False
    from public_report_store import load_public_pdf

    report = load_public_pdf(token)
    if not report:
        st.error("Rapportlenken er ugyldig eller utløpt.")
        st.stop()
    report = {**report, "_return_to": return_to}
    target, static_url = _hydrate_static_pdf(token, report)
    mobile_pdf = target.read_bytes()
    st.markdown("### 📄 Rapporten er klar")
    st.caption(f"Rapport-ID: {report.get('report_id') or '-'}")
    from mobile_file_delivery import render_mobile_file_delivery
    render_mobile_file_delivery(
        st, url=static_url, filename=str(report.get("filename") or "rapport.pdf"),
        label="Åpne PDF for nedlasting eller deling", mime="application/pdf",
        data=mobile_pdf, key=f"public_pdf_{token}", show_return=False,
    )
    st.markdown(_report_landing_actions(static_url, return_href=return_href), unsafe_allow_html=True)
    return True
