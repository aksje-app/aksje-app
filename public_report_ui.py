"""Unauthenticated bridge from durable report tokens to a mobile-friendly viewer."""
from __future__ import annotations

from html import escape
from pathlib import Path
import io
import json
import zipfile
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
import os
import re


_RETURN_NAV_TARGETS = {
    "dashboard", "portfolio", "long_engine", "autonomy", "reports", "market",
    "jobs", "approvals", "paper_trading", "fx_alerts", "alerts",
    "drift_center", "system", "overview", "quality", "quality_valuation", "super_portfolio",
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
    if nav == "super_portfolio":
        return {"aa_nav": "super_portfolio"}
    return {"aa_nav": nav}


def _return_label(value: str) -> str:
    nav = _safe_return_nav(value)
    if nav == "quality_reports":
        return "← Tilbake til rapportvalg"
    if nav in {"quality", "quality_valuation"}:
        return "← Tilbake til Kvalitet"
    if nav == "overview":
        return "← Tilbake til Oversikt"
    if nav == "super_portfolio":
        return "← Tilbake til Super Portfolio"
    return "← Tilbake"


def _return_context(value: str, run_key: str = "") -> dict[str, str]:
    query = _return_query(value)
    if value == "quality_reports" and re.fullmatch(r"quality_valuation/runs/\d{8}T\d{12}", str(run_key or "")):
        query["qv_report_run"] = run_key
    return query


def _report_return_href(value: str, run_key: str = "") -> str:
    return "/?" + urlencode(_return_context(value, run_key))


def _absolute_report_return_url(value: str, run_key: str = "") -> str:
    """Build the same-origin absolute URL required by mobile PDF viewers."""
    query = urlencode(_return_context(value, run_key))
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
            return_url=_absolute_report_return_url(str(report.get("_return_to") or "reports"), str(report.get("_run_key") or "")),
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


def _report_landing_actions(static_url: str, *, return_href: str, return_label: str = "← Tilbake") -> str:
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
        'text-decoration:none;font-weight:800;text-align:center">Åpne PDF</a>'
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


def _share_controls_html(static_url: str) -> str:
    """File sharing on a user click, with an explicit browser fallback.

    srcdoc components share the application origin. Use the top-level
    navigator when accessible so iframe permissions cannot hide the action.
    Pre-fetching the file retains the click's transient user activation.
    """
    parsed = urlsplit(static_url)
    if parsed.scheme or parsed.netloc or not re.fullmatch(r"/app/static/reports/[A-Za-z0-9_-]+\.pdf", parsed.path):
        raise ValueError("Invalid static report path")
    url = json.dumps(static_url)
    return '''<!doctype html><html lang="nb"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{margin:0;font:16px system-ui;color:#cbd5e1}button,a{display:inline-block;padding:14px 20px;border-radius:12px;border:1px solid #2dd4bf;background:#0f766e;color:white;font-weight:700;margin:4px;text-decoration:none}p{margin:8px 4px}</style>
<button id="share" disabled>Forbereder deling …</button><a id="download" download="rapport.pdf">Last ned PDF</a>
<p id="status" role="status">Henter rapportfilen for deling.</p>
<script>
const url = ''' + url + ''';
const button=document.getElementById('share'), status=document.getElementById('status');
document.getElementById('download').href=url;
let file=null, shareNav=navigator;
try { if(window.parent.navigator.share) shareNav=window.parent.navigator; } catch (_) {}
fetch(url).then(async response=>{
 if(!response.ok) throw new Error('download');
 const blob=await response.blob();
 if(blob.size>20*1024*1024 || !blob.size) throw new Error('size');
 file=new File([blob],'rapport.pdf',{type:'application/pdf'});
 button.disabled=false; button.textContent='Del rapport'; status.textContent='Velg Del rapport eller Last ned PDF.';
}).catch(()=>{button.textContent='Del rapport';button.disabled=false;status.textContent='Bruk Last ned PDF hvis direkte deling ikke er tilgjengelig.';});
button.onclick=async()=>{
 try {
  if(!file || !shareNav.share || !shareNav.canShare || !shareNav.canShare({files:[file]})) {
   status.textContent='Direkte fildeling støttes ikke her. Velg Last ned PDF, og del filen fra nettleserens Del-meny. Åpne i Safari hvis du bruker en innebygd appnettleser.'; return;
  }
  await shareNav.share({files:[file],title:'Aksje-app rapport'});
  status.textContent='Rapporten er delt.';
 } catch(error) {
  status.textContent=error.name==='AbortError'?'Deling avbrutt.':'Deling kunne ikke fullføres. Last ned PDF og del filen fra nettleseren.';
 }
};
</script></html>'''


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


def _return_to_report_choices(st, return_to: str) -> None:
    if st.button(_return_label(return_to), key="public_file_back", use_container_width=True):
        st.query_params.clear()
        for key, value in _return_query(return_to).items():
            st.query_params[key] = value
        st.rerun()


def _render_in_app_file(st, artifact: dict, *, return_to: str, static_url: str) -> None:
    """Keep diagnostic/package navigation inside Aurora until explicit download."""
    filename = str(artifact.get("filename") or "nedlasting")
    mime = str(artifact.get("mime") or "application/octet-stream")
    data = bytes(artifact.get("data") or b"")
    suffix = Path(filename).suffix.lower()

    st.markdown("### Fil og diagnose")
    st.caption("Du blir på denne siden til du selv velger å laste ned filen.")
    _return_to_report_choices(st, return_to)

    if suffix == ".json":
        st.markdown("#### Diagnose")
        try:
            parsed = json.loads(data.decode("utf-8"))
            pretty = json.dumps(parsed, ensure_ascii=False, indent=2)
        except Exception:
            pretty = data.decode("utf-8", errors="replace")
        st.caption("Diagnosen kan leses og kopieres her uten å åpne en ekstern filviser.")
        st.code(pretty, language="json")
    elif suffix == ".txt":
        st.markdown("#### Innhold")
        st.code(data.decode("utf-8", errors="replace"))
    elif suffix == ".zip":
        st.markdown("#### Kontrollpakke")
        names = []
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = archive.namelist()
        except Exception:
            names = []
        if names:
            st.caption("Pakken inneholder:")
            for name in names[:20]:
                st.markdown(f"- {escape(str(name))}")
        else:
            st.caption("ZIP-pakken er klar for nedlasting.")

    safe_url = escape(str(static_url or ""), quote=True)
    st.markdown(
        '<a href="' + safe_url + '" target="_blank" rel="noopener noreferrer" '
        'style="display:block;padding:.9rem;border:1px solid #2dd4bf;border-radius:.8rem;'
        'background:#0f766e;color:white;text-decoration:none;font-weight:850;text-align:center">'
        'Åpne / del fil i ny visning</a>',
        unsafe_allow_html=True,
    )
    st.caption("Appens rapportvalg blir stående i denne fanen. Lukk filvisningen eller bytt tilbake hit når du er ferdig.")
    with st.expander("Direkte nedlasting", expanded=False):
        st.download_button(
            "Last ned fil",
            data=data,
            file_name=filename,
            mime=mime,
            key="public_file_download",
            use_container_width=True,
        )


def render_public_report(st) -> bool:
    return_to = str(st.query_params.get("return_to") or "reports")
    run_key = str(st.query_params.get("qv_report_run") or "")
    return_href = _report_return_href(return_to, run_key)
    return_label = _return_label(return_to)

    file_token = str(st.query_params.get("public_file_token") or "").strip()
    if file_token:
        from public_report_store import load_public_file
        artifact = load_public_file(file_token)
        if not artifact:
            st.error("Fillenken er ugyldig eller utløpt.")
            st.stop()
        _, static_url = _hydrate_static_file(file_token, artifact)
        _render_in_app_file(st, artifact, return_to=return_to, static_url=static_url)
        return True

    token = str(st.query_params.get("public_report_token") or "").strip()
    if not token:
        return False

    from public_report_store import load_public_pdf
    report = load_public_pdf(token)
    if not report:
        st.error("Rapportlenken er ugyldig eller utløpt.")
        st.stop()
    report = {**report, "_return_to": return_to, "_run_key": run_key}
    _, static_url = _hydrate_static_pdf(token, report)

    st.markdown("### Rapport")
    st.caption("Les rapporten i appen. Åpne/del PDF bare når du trenger systemets PDF-viser.")
    import streamlit.components.v1 as components
    components.html(_share_controls_html(static_url), height=250)
    st.markdown(
        _report_landing_actions(
            static_url,
            return_href=return_href,
            return_label=return_label,
        ),
        unsafe_allow_html=True,
    )
    return True
