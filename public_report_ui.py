"""Unauthenticated bridge from durable report tokens to a mobile-friendly viewer."""
from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
import os


_RETURN_NAV_TARGETS = {
    "dashboard", "portfolio", "long_engine", "autonomy", "reports", "market",
    "jobs", "approvals", "paper_trading", "fx_alerts", "alerts",
    "drift_center", "system", "overview", "quality", "quality_valuation",
}
_SPECIAL_RETURN_TARGETS = {"quality_reports"}


def _safe_return_nav(value: str) -> str:
    nav = str(value or "").strip().lower().replace("-", "_")
    if nav in _SPECIAL_RETURN_TARGETS:
        return nav
    return nav if nav in _RETURN_NAV_TARGETS else "reports"


def _return_query(value: str) -> dict[str, str]:
    nav = _safe_return_nav(value)
    if nav == "quality_reports":
        return {"aa_nav": "quality_valuation", "qv_reports": "1"}
    if nav in {"quality", "quality_valuation"}:
        return {"aa_nav": "quality_valuation"}
    return {"aa_nav": nav}


def _return_label(value: str) -> str:
    nav = _safe_return_nav(value)
    if nav == "quality_reports":
        return "← Tilbake til rapportvalg"
    if nav in {"quality", "quality_valuation"}:
        return "← Tilbake til Kvalitet"
    if nav == "overview":
        return "← Tilbake til Oversikt"
    return "← Tilbake"


def _report_return_href(value: str) -> str:
    return "/?" + urlencode(_return_query(value))


def _absolute_report_return_url(value: str) -> str:
    """Build the same-origin absolute URL required by mobile PDF viewers."""
    query = urlencode(_return_query(value))
    for candidate in (os.getenv("RENDER_EXTERNAL_URL"), os.getenv("REPORT_PUBLIC_BASE_URL")):
        parsed = urlsplit(str(candidate or "").strip())
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return urlunsplit((parsed.scheme, parsed.netloc, "/", query, ""))
    return "https://aksje-app.onrender.com/?" + query


def with_report_return(url: str, return_to: str) -> str:
    """Attach an allowlisted in-app return route to a public report URL."""
    parsed = urlsplit(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["return_to"] = _safe_return_nav(return_to)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _hydrate_static_pdf(token: str, report: dict) -> tuple[Path, str]:
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
        stamped = bytes(report["data"])
    temporary.write_bytes(stamped)
    temporary.replace(target)
    return target, f"/app/static/reports/{quote(target.name)}"


def _hydrate_static_file(token: str, artifact: dict) -> tuple[Path, str]:
    from report_delivery import PUBLIC_REPORT_DIR

    safe = "".join(ch for ch in str(token or "") if ch.isalnum() or ch in "-_")
    suffix = Path(str(artifact.get("filename") or "nedlasting.bin")).suffix.lower()
    if len(safe) < 32 or suffix not in {".json", ".txt", ".zip"}:
        raise ValueError("Ugyldig filtoken")
    target = PUBLIC_REPORT_DIR / f"public_file_{safe}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{suffix}.tmp")
    temporary.write_bytes(bytes(artifact["data"]))
    temporary.replace(target)
    return target, f"/app/static/reports/{quote(target.name)}"


def _report_landing_actions(static_url: str, *, return_href: str, return_label: str) -> str:
    """Aurora-style actions with no technical path exposed to the user."""
    safe_pdf = escape(str(static_url or ""), quote=True)
    safe_return = escape(str(return_href or "/?aa_nav=reports"), quote=True)
    safe_label = escape(str(return_label or "← Tilbake"))
    return (
        '<section data-testid="public-report-mobile-shell" '
        'style="margin:.65rem 0 1rem;padding:.85rem;border:1px solid #24445c;'
        'border-radius:1rem;background:linear-gradient(180deg,#081827,#06111d);box-shadow:0 14px 32px rgba(0,0,0,.18)">'
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:.65rem;margin-bottom:.8rem">'
        f'<a href="{safe_return}" target="_self" style="display:flex;align-items:center;justify-content:center;'
        'min-height:52px;padding:.75rem .65rem;border:1px solid #2b7182;border-radius:.8rem;'
        'background:#0c2735;color:#e6f7fb;text-decoration:none;font-weight:800;text-align:center">'
        f'{safe_label}</a>'
        f'<a href="{safe_pdf}" target="_blank" rel="noopener noreferrer" '
        'style="display:flex;align-items:center;justify-content:center;min-height:52px;padding:.75rem .65rem;'
        'border:1px solid #277aa7;border-radius:.8rem;background:#0b3550;color:#f3fbff;'
        'text-decoration:none;font-weight:800;text-align:center">Del / åpne PDF</a>'
        f'<a href="{safe_pdf}#toolbar=1" target="_blank" rel="noopener noreferrer" '
        'title="På iPhone: åpne PDF, trykk Del og velg Skriv ut" '
        'style="grid-column:1/-1;display:flex;align-items:center;justify-content:center;min-height:54px;'
        'padding:.78rem;border:1px solid #2dd4bf;border-radius:.8rem;background:#0f766e;'
        'color:white;text-decoration:none;font-weight:850;text-align:center">Skriv ut PDF</a>'
        '</div>'
        '<p style="margin:.05rem .2rem .85rem;color:#9fb4c5;font-size:.88rem;line-height:1.35">'
        'På iPhone åpner «Skriv ut PDF» selve PDF-en. Bruk Del-menyen og velg «Skriv ut».</p>'
        f'<iframe title="Rapportvisning" src="{safe_pdf}#view=FitH" '
        'style="width:100%;height:78vh;min-height:620px;border:1px solid #31526a;border-radius:.8rem;background:white" '
        'loading="eager"></iframe>'
        '</section>'
    )


def _file_landing_actions(static_url: str, *, return_href: str, return_label: str, filename: str) -> str:
    safe_url = escape(str(static_url or ""), quote=True)
    safe_return = escape(str(return_href or "/?aa_nav=reports"), quote=True)
    safe_label = escape(str(return_label or "← Tilbake"))
    safe_name = escape(str(filename or "fil"), quote=True)
    return (
        '<section data-testid="public-file-mobile-shell" '
        'style="display:grid;gap:.7rem;margin:.65rem 0;padding:.9rem;border:1px solid #24445c;'
        'border-radius:1rem;background:linear-gradient(180deg,#081827,#06111d)">'
        f'<a href="{safe_return}" target="_self" style="display:block;padding:.8rem;border:1px solid #2b7182;'
        'border-radius:.8rem;background:#0c2735;color:#e6f7fb;text-decoration:none;font-weight:800;text-align:center">'
        f'{safe_label}</a>'
        f'<a href="{safe_url}" download="{safe_name}" target="_blank" rel="noopener noreferrer" '
        'style="display:block;padding:.9rem;border:1px solid #2dd4bf;border-radius:.8rem;background:#0f766e;'
        'color:white;text-decoration:none;font-weight:850;text-align:center">Last ned fil</a>'
        '</section>'
    )


def render_public_report(st) -> bool:
    return_to = str(st.query_params.get("return_to") or "reports")
    return_href = _report_return_href(return_to)
    return_label = _return_label(return_to)

    file_token = str(st.query_params.get("public_file_token") or "").strip()
    if file_token:
        from public_report_store import load_public_file

        artifact = load_public_file(file_token)
        if not artifact:
            st.error("Fillenken er ugyldig eller utløpt.")
            st.stop()
        _, static_url = _hydrate_static_file(file_token, artifact)
        filename = str(artifact.get("filename") or "nedlasting")
        st.markdown("### Filen er klar")
        st.caption("Last ned filen, eller gå tilbake til rapportvalgene.")
        st.markdown(
            _file_landing_actions(
                static_url,
                return_href=return_href,
                return_label=return_label,
                filename=filename,
            ),
            unsafe_allow_html=True,
        )
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
    _, static_url = _hydrate_static_pdf(token, report)

    st.markdown("### Rapport")
    st.caption("Les rapporten under, del den, skriv den ut eller gå tilbake til rapportvalgene.")
    st.markdown(
        _report_landing_actions(
            static_url,
            return_href=return_href,
            return_label=return_label,
        ),
        unsafe_allow_html=True,
    )
    return True
