"""Manual shadow screen with bounded acquisition, PDF and diagnostic export."""
from __future__ import annotations

from io import BytesIO
from datetime import datetime, timezone
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from quality_valuation import GROUPS, MAX_SYMBOLS, run_screen
from quality_valuation_data import isolated_financial_snapshot, memory_budget_ok, observed_driver_prices
from quality_valuation_store import load_latest, persist_screen


def _printable(value: Any) -> str:
    return str(value if value is not None else "-").encode("latin-1", errors="replace").decode("latin-1")


def build_screen_pdf(result: Mapping[str, Any]) -> bytes:
    """Plain PDF with no interactive app navigation on printed pages."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    fonts = Path(__file__).parent / "assets" / "fonts"
    regular, bold = "Helvetica", "Helvetica-Bold"
    if (fonts / "NotoSans-Regular.ttf").is_file() and (fonts / "NotoSans-Bold.ttf").is_file():
        pdfmetrics.registerFont(TTFont("QVRegular", str(fonts / "NotoSans-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("QVBold", str(fonts / "NotoSans-Bold.ttf")))
        regular, bold = "QVRegular", "QVBold"
    buffer = BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 48
    page.setFont(bold, 16)
    page.drawString(40, y, "Kvalitet og verdsettelse - observasjon")
    y -= 25
    page.setFont(regular, 9)
    page.drawString(40, y, _printable(f"Tid: {result.get('generated_at')}  Status: {result.get('state')}"))
    y -= 22
    page.drawString(40, y, "Scenariopriser er ingen kjøpsordre. Kontroller regnskapstall mot selskapets rapporter.")
    y -= 28
    for name, data in (result.get("driver_prices") or {}).items():
        page.drawString(40, y, _printable(f"{name}: proxy {data.get('last_price') or '-'} · 1 måned {data.get('one_month_pct') if data.get('one_month_pct') is not None else '-'}% · {data.get('price_date') or '-'}"))
        y -= 13
    if result.get("driver_prices"):
        page.drawString(40, y, "Råvareindikatorer må ikke tolkes som dokumentert prisfølsomhet i selskapet.")
        y -= 20
    for group, items in (result.get("groups") or {}).items():
        if y < 95:
            page.showPage()
            y = height - 48
        page.setFont(bold, 11)
        page.drawString(40, y, _printable(f"{group} ({len(items)})"))
        y -= 20
        page.setFont(regular, 8)
        for item in items:
            if y < 135:
                page.showPage()
                y = height - 48
                page.setFont(regular, 8)
            line = (f"{item.get('ticker')}  {str(item.get('name') or '')[:20]}  "
                    f"Kurs {item.get('price') or '-'} {item.get('currency') or ''}  "
                    f"P/E {item.get('reported_pe') or '-'}  Normalisert {item.get('normalized_pe') or '-'}  "
                    f"Scenario {item.get('entry_range_scenario') or '-'}")
            page.drawString(45, y, _printable(line)[:113])
            y -= 13
            page.drawString(45, y, _printable(
                f"Land {item.get('country') or '-'} · Bransje {item.get('industry') or '-'} · "
                f"ROCE {item.get('roce_pct') if item.get('roce_pct') is not None else '-'}% · "
                f"Regnskap {item.get('financial_date') or '-'}")[:107])
            y -= 13
            for warning in (item.get("warnings") or [])[:2]:
                if y < 60:
                    page.showPage()
                    y = height - 48
                    page.setFont(regular, 8)
                page.drawString(55, y, _printable(str(warning))[:105])
                y -= 13
            y -= 5
        y -= 10
    page.save()
    from pdf_mobile_return import add_pdf_return_links
    from public_report_ui import _absolute_report_return_url
    return add_pdf_return_links(buffer.getvalue(), return_url=_absolute_report_return_url("market"))


def diagnostic_document(result: Mapping[str, Any]) -> bytes:
    """No credentials, database URL or raw provider payloads in the bundle."""
    from runtime_memory import memory_snapshot
    from services.storage_service import get_storage_service
    from storage_retention import load_storage_retention_state

    try:
        health = get_storage_service().health()
        storage = {"backend": str(getattr(health, "backend", "unknown")), "ok": bool(getattr(health, "ok", False))}
    except Exception:
        storage = {"backend": "unknown", "ok": False}
    memory = memory_snapshot()
    try:
        retention = load_storage_retention_state()
    except Exception:
        retention = {"state": "UNAVAILABLE"}
    payload = {
        "run_key": result.get("run_key"), "generated_at": result.get("generated_at"),
        "state": result.get("state"), "stop_reason": result.get("stop_reason"),
        "selected": result.get("selected"), "completed": result.get("completed"),
        "elapsed_seconds": result.get("elapsed_seconds"), "failures": result.get("failures"),
        "cpu_seconds": result.get("cpu_seconds"),
        "groups": {name: [{"ticker": item.get("ticker"), "group": item.get("group"),
                             "warnings": item.get("warnings"), "financial_date": item.get("financial_date"),
                             "source": item.get("source")} for item in items]
                   for name, items in (result.get("groups") or {}).items()},
        "storage": storage,
        "retention": {key: retention.get(key) for key in ("state", "apply_enabled", "planned", "deleted_keys")},
        "memory_mb": {name: memory.get(name) for name in ("process_rss_mb", "cgroup_memory_current_mb", "cgroup_memory_limit_mb")},
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def required_report_busy() -> bool:
    """Read-only advisory guard; never acquire or block the scheduler's lock."""
    from execution_coordination import report_execution_owner
    owner = report_execution_owner()
    try:
        observed = datetime.fromisoformat(str(owner.get("heartbeat_at") or "").replace("Z", "+00:00"))
        fresh = 0 <= (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds() < 35
    except (ValueError, TypeError):
        fresh = False
    return bool(fresh and str(owner.get("state") or "").upper() == "ACTIVE")


def render_quality_valuation(st: Any, market_tickers: Sequence[str] = (), *, expanded: bool = False) -> None:
    with st.expander("Kvalitet, prising og inngangskurs · shadow", expanded=expanded):
        st.caption("Manuell observasjonsanalyse. Starter ingen handel og sender ikke Pushover. Finansdata må kontrolleres i selskapsrapporten.")
        source = st.radio("Aksjer", ["Skriv tickere", "Bruk valgt markedsutvalg"], horizontal=True, key="qv_source")
        raw = st.text_input("Tickere, adskilt med komma", placeholder="EQNR.OL, NHY.OL, YAR.OL", key="qv_tickers") if source == "Skriv tickere" else ""
        selected = [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()] if raw else list(market_tickers)[:MAX_SYMBOLS]
        if source == "Bruk valgt markedsutvalg":
            st.caption(f"Valgte aksjer: {', '.join(selected) if selected else 'Ingen aksjer valgt'} · maks {MAX_SYMBOLS} per kjøring.")
        use_scenario = st.checkbox("Vis priseksempel med P/E jeg velger", value=False, key="qv_use_assumption")
        assumed_pe = st.number_input("P/E-forutsetning (analytisk scenario, ikke fast verdi)", 4.0, 40.0, 15.0, 0.5, key="qv_assumption") if use_scenario else None
        if use_scenario:
            st.warning("Samme P/E på tvers av bransjer er kun et illustrert scenario. Det gir ikke en bekreftet inngangskurs eller automatisk kjøpssignal.")
        if st.button("Kjør kvalitetsvurdering", key="qv_run", type="primary", disabled=not bool(selected)):
            from services.storage_service import get_storage_service
            health = get_storage_service().health()
            if not bool(getattr(health, "ok", False)) or (os.getenv("DATABASE_URL") and getattr(health, "backend", "") != "postgres"):
                st.error("Lagringen er ikke tilgjengelig. Kjører ikke uten en fungerende database.")
                return
            if required_report_busy():
                st.info("En obligatorisk rapport kjører. Prøv søket igjen når den er ferdig.")
                return
            bar = st.progress(0, text=f"Starter · 0/{len(selected)}")
            def update(row: dict[str, Any]) -> None:
                bar.progress(min(100, round(100 * row["completed"] / len(selected))),
                             text=f"{row['stage']} {row['ticker']} · {row['completed']}/{row['total']}")
            try:
                from quality_valuation_control import single_manual_screen
                last_report_check = [0.0]
                def workload_safe() -> bool:
                    if not memory_budget_ok():
                        return False
                    if time.monotonic() - last_report_check[0] > 10:
                        last_report_check[0] = time.monotonic()
                        return not required_report_busy()
                    return True
                with single_manual_screen() as acquired:
                    if not acquired:
                        st.info("Et annet manuelt kvalitetssøk pågår. Prøv igjen når det er ferdig.")
                        return
                    result = run_screen(selected, isolated_financial_snapshot, assumed_pe=assumed_pe,
                                        progress=update, memory_guard=workload_safe)
                    if result["elapsed_seconds"] < 140 and workload_safe():
                        names = [name for items in result["groups"].values() for item in items
                                 for name in item.get("market_drivers") or []]
                        if names:
                            bar.progress(100, text="Henter tilgjengelige råvareindikatorer · ingen automatisk prisjustering")
                            result["driver_prices"] = observed_driver_prices(names)
                    result["run_key"] = persist_screen(result)
                    st.session_state["qv_result"] = result
                    bar.progress(round(100 * result["completed"] / max(result["selected"], 1)),
                                 text=f"{result['state']} · {result['completed']}/{result['selected']}")
            except Exception as exc:
                st.error(f"Kunne ikke fullføre vurderingen: {type(exc).__name__}. Kontroller diagnose og markedstilgang.")
        result = st.session_state.get("qv_result") or load_latest()
        if not result:
            st.info("Ingen kvalitetsvurdering kjørt ennå.")
            return
        st.caption(f"Sist lagret: {result.get('generated_at')} · {result.get('state')} · {result.get('completed')}/{result.get('selected')} · {result.get('elapsed_seconds') or 0}s · CPU {result.get('cpu_seconds') or 0}s")
        st.caption("Varsling: avventes. Tredjeparts nøkkeltall og et manuelt valgt P/E-scenario er ikke kontrollert mot primærkilder; disse resultatene sender derfor ingen Pushover.")
        if result.get("stop_reason") or result.get("failures"):
            st.warning(f"Ufullstendig kjøring. {result.get('stop_reason') or ''} Feil: {len(result.get('failures') or [])}")
        if result.get("driver_prices"):
            st.markdown("**Råvareindikatorer (markedspriser, ikke selskapets oppnådde priser)**")
            for name, data in result["driver_prices"].items():
                st.caption(f"{name}: {data.get('last_price') or 'mangler'} · 1 md. {data.get('one_month_pct') if data.get('one_month_pct') is not None else '-'}% · dato {data.get('price_date') or '-'}")
        for group in (*GROUPS, "Ufullstendig / krever vurdering"):
            items = (result.get("groups") or {}).get(group) or []
            st.markdown(f"#### {group} ({len(items)})")
            if not items:
                st.caption("Ingen dokumenterte treff.")
                continue
            visible = items if st.toggle("Vis alle", key=f"qv_all_{group}", value=False) else items[:5]
            for item in visible:
                st.markdown(f"**{item['ticker']} · {item['name']}** · {item.get('country') or '-'} · {item.get('industry') or '-'}")
                st.caption(f"Kurs {item.get('price') or '-'} {item.get('currency') or ''} · ROCE {item.get('roce_pct') or '-'}% · P/E {item.get('reported_pe') or '-'} · normalisert P/E {item.get('normalized_pe') or '-'} · scenario {item.get('entry_range_scenario') or '-'}")
                if item.get("entry_range_scenario"):
                    st.caption(f"Grunnlag: {item.get('valuation_basis') or 'P/E-forutsetning valgt manuelt'} · margin {item.get('entry_buffer_pct')}% basert på resultatvariasjon. {item.get('capital_return_method')}")
                for warning in (item.get("warnings") or [])[:3]:
                    st.caption(f"⚠ {warning}")
        st.download_button("Last ned PDF", build_screen_pdf(result), "kvalitet_verdsettelse.pdf", "application/pdf", key="qv_pdf")
        st.download_button("Last ned diagnose", diagnostic_document(result), "kvalitet_verdsettelse_diagnose.json", "application/json", key="qv_diagnosis")
        st.link_button("← Tilbake til programmet", "/?aa_nav=market")
