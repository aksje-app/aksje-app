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
from quality_valuation_store import load_latest_manual, persist_screen


def _printable(value: Any) -> str:
    return str(value if value is not None else "-").encode("latin-1", errors="replace").decode("latin-1")


def build_screen_pdf(result: Mapping[str, Any]) -> bytes:
    """Compact mobile/print PDF with screen-only app return annotation."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
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
    palette = {
        "green": colors.HexColor("#16a34a"),
        "yellow": colors.HexColor("#d97706"),
        "red": colors.HexColor("#dc2626"),
        "blue": colors.HexColor("#2563eb"),
        "grey": colors.HexColor("#64748b"),
        "light": colors.HexColor("#e2e8f0"),
    }

    def heading(title: str, subtitle: str = "") -> float:
        page.setFillColor(colors.black)
        page.setFont(bold, 15)
        page.drawString(36, height - 43, _printable(title)[:82])
        page.setFont(regular, 7.5)
        page.drawString(36, height - 58, _printable(subtitle)[:125])
        page.setStrokeColor(palette["light"])
        page.line(36, height - 66, width - 36, height - 66)
        return height - 86

    def write(y: float, text: str, *, font=regular, size: float = 8, x: float = 40) -> float:
        if y < 55:
            page.showPage()
            y = heading("Kvalitet og verdsettelse", f"Run {result.get('run_key') or '-'}")
        page.setFillColor(colors.black)
        page.setFont(font, size)
        page.drawString(x, y, _printable(text)[:126])
        return y - (size + 4)

    def dot(x: float, y: float, kind: str) -> None:
        color = palette["green"] if kind == "good" else palette["red"] if kind == "bad" else palette["yellow"] if kind == "watch" else palette["blue"]
        page.setFillColor(color)
        page.circle(x, y + 2, 3.4, stroke=0, fill=1)

    def arrow(x: float, y: float, kind: str) -> None:
        color = palette["green"] if kind == "good" else palette["red"] if kind == "bad" else palette["yellow"]
        page.setStrokeColor(color)
        page.setFillColor(color)
        if kind == "good":
            page.line(x, y - 4, x, y + 5)
            page.line(x, y + 5, x - 3, y + 1)
            page.line(x, y + 5, x + 3, y + 1)
        elif kind == "bad":
            page.line(x, y + 5, x, y - 4)
            page.line(x, y - 4, x - 3, y)
            page.line(x, y - 4, x + 3, y)
        else:
            page.line(x - 4, y, x + 4, y)
            page.line(x + 4, y, x, y + 3)
            page.line(x + 4, y, x, y - 3)

    def medal_icon(x: float, y: float, rank: int) -> None:
        if rank not in (1, 2, 3):
            return
        fill = colors.HexColor("#d4af37") if rank == 1 else colors.HexColor("#9ca3af") if rank == 2 else colors.HexColor("#b87333")
        page.setFillColor(fill)
        page.circle(x, y, 7, stroke=0, fill=1)
        page.setFillColor(colors.white)
        page.setFont(bold, 7)
        page.drawCentredString(x, y - 2.5, str(rank))

    def medal(rank: int) -> str:
        return {1: "1. plass", 2: "2. plass", 3: "3. plass"}.get(rank, "")

    y = heading("Kvalitet og verdsettelse - observasjon",
                f"Tid {result.get('generated_at') or '-'} - status {result.get('state') or '-'}")
    y = write(y, "Scenario er sammenligning, ikke kursmål eller kjøpsordre.", font=bold, size=8.5)
    if result.get("market_universe_count") is not None:
        y = write(y, f"Marked: {result.get('market_examined_count') or 0}/{result.get('market_universe_count') or 0} undersøkt - {result.get('market_usable_count') or 0} med brukbare data.")
    y -= 5

    rank = 0
    for group, items in (result.get("groups") or {}).items():
        if y < 100:
            page.showPage()
            y = heading("Kvalitet og verdsettelse", f"Run {result.get('run_key') or '-'}")
        page.setFont(bold, 10)
        page.setFillColor(colors.black)
        page.drawString(40, y, _printable(f"{group} ({len(items)})"))
        y -= 17
        for item in items:
            if y < 125:
                page.showPage()
                y = heading("Kvalitet og verdsettelse", f"Run {result.get('run_key') or '-'}")
            if group == "Attraktivt priset kandidat":
                rank += 1
            label = medal(rank) + " - " if group == "Attraktivt priset kandidat" and rank <= 3 else ""
            state = "good" if item.get("quality_evidence_ready") else "watch" if item.get("quality_state") in {"WATCH", "SECTOR_METRIC_REQUIRED"} else "bad"
            if group == "Attraktivt priset kandidat" and rank <= 3:
                medal_icon(44, y + 1, rank)
            else:
                dot(44, y - 1, state)
            y = write(y, f"{label}{item.get('ticker')} - {item.get('name')}", font=bold, size=8.5, x=52)
            y = write(y, f"Kurs nå {item.get('price') or '-'} {item.get('currency') or ''} - P/E ved dagens kurs {item.get('reported_pe') or '-'} - forward P/E {item.get('forward_pe') or '-'}", size=7.6, x=52)
            y = write(y, f"Normalisert P/E ved dagens kurs {item.get('normalized_pe') or '-'} - normalisert EPS {item.get('normalized_eps') or '-'}", size=7.6, x=52)

            policy = item.get("sector_policy") or "STANDARD"
            if policy == "FINANCIAL":
                trend = str(item.get("roe_trend") or "").upper()
                trend_kind = "good" if trend == "FORBEDRENDE" else "bad" if trend == "SVEKKENDE" else "watch"
                direction = "OPP" if trend_kind == "good" else "NED" if trend_kind == "bad" else "STABIL"
                arrow(55, y + 1, trend_kind)
                y = write(y, f"ROE median {item.get('roe_pct') if item.get('roe_pct') is not None else '-'}% - siste {item.get('roe_latest_pct') if item.get('roe_latest_pct') is not None else '-'}% - retning {direction}", size=7.4, x=64)
            else:
                trend = str(item.get("roce_trend") or "").upper()
                trend_kind = "good" if trend == "FORBEDRENDE" else "bad" if trend == "SVEKKENDE" else "watch"
                direction = "OPP" if trend_kind == "good" else "NED" if trend_kind == "bad" else "STABIL"
                arrow(55, y + 1, trend_kind)
                y = write(y, f"ROCE median {item.get('roce_pct') if item.get('roce_pct') is not None else '-'}% - siste {item.get('roce_latest_pct') if item.get('roce_latest_pct') is not None else '-'}% - retning {direction}", size=7.4, x=64)

            if item.get("entry_range_scenario"):
                y = write(y, f"Scenarioverdi {item.get('fair_price_scenario')} - inngangsscenario {item.get('entry_range_scenario')} - IKKE KURSMÅL", font=bold, size=7.4, x=52)
                if item.get("peer_count"):
                    y = write(y, f"Peer-median P/E {item.get('assumed_pe')} - peers {item.get('peer_count')}: {', '.join(item.get('peer_tickers') or [])}", size=6.8, x=52)
            else:
                y = write(y, f"Scenario: ikke beregnet ({policy}-policy / utilstrekkelig sammenligningsgrunnlag).", size=6.8, x=52)

            if group == "Ufullstendig / krever vurdering":
                y = write(y, f"Årsakstype: {item.get('review_reason_category') or 'UKJENT'}", font=bold, size=7.1, x=52)
            for warning in (item.get("warnings") or [])[:2]:
                y = write(y, f"- {warning}", size=6.4, x=58)
            y -= 4
        y -= 5

    page.save()
    from pdf_mobile_return import add_pdf_return_links
    from public_report_ui import _absolute_report_return_url
    return add_pdf_return_links(buffer.getvalue(), return_url=_absolute_report_return_url("overview"))

def diagnostic_document(result: Mapping[str, Any]) -> bytes:
    """Secret-free reproducibility/audit document for active and shadow quality models."""
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

    audit_fields = (
        "ticker", "name", "country", "industry", "currency", "price", "group",
        "quality_state", "model_version", "sector_policy", "review_reason_category",
        "financial_date", "financial_age_days",
        "reported_pe", "forward_pe", "normalized_pe", "normalized_eps",
        "annual_eps_history", "fiscal_periods", "operating_margin_history", "debt_history",
        "equity_history", "roe_history", "sector", "is_financial",
        "free_cash_flow", "free_cash_flow_history", "fcf_positive_ratio", "roce_pct", "roce_latest_pct", "roce_history_pct",
        "roce_trend", "roe_pct", "roe_latest_pct", "roe_trend",
        "quality_evidence_ready", "evidence_ready", "assumed_pe",
        "fair_price_scenario", "entry_range_scenario", "entry_buffer_pct",
        "peer_count", "peer_tickers", "peer_normalized_pe",
        "valuation_method", "capital_return_method", "market_drivers",
        "verified_exposure", "source", "provider_partial", "warnings", "observed_at",
    )
    payload = {
        "audit_schema": "quality-diagnosis@2.1",
        "app_version": __import__("app_version").APP_VERSION,
        "run_key": result.get("run_key"), "report_id": result.get("report_id"),
        "generated_at": result.get("generated_at"), "run_mode": result.get("run_mode"),
        "state": result.get("state"), "stop_reason": result.get("stop_reason"),
        "selected": result.get("selected"), "selected_symbols": result.get("selected_symbols"),
        "completed": result.get("completed"), "elapsed_seconds": result.get("elapsed_seconds"),
        "cpu_seconds": result.get("cpu_seconds"), "failures": result.get("failures"),
        "market_basis": {key: result.get(key) for key in (
            "markets", "market_universe_count", "market_examined_count", "market_usable_count",
            "market_failed_count", "market_coverage_complete", "market_prescreen_stop_reason",
            "candidate_basis_generated_at", "candidate_basis_source", "prescreen_finalists", "holding_symbols")},
        "active_quality_model": "quality_v1.2@1.2",
        "groups": {name: [{key: item.get(key) for key in audit_fields} for item in items]
                   for name, items in (result.get("groups") or {}).items()},
        "quality_v2_shadow": result.get("quality_v2_shadow") or {},
        "quality_v2_oversight": result.get("quality_v2_oversight") or {},
        "quality_v2_milestone_evaluation": (result.get("quality_v2_oversight") or {}).get("latest_evaluation") or {},
        "driver_prices": result.get("driver_prices") or {},
        "storage": storage,
        "retention": {key: retention.get(key) for key in ("state", "apply_enabled", "planned", "deleted_keys")},
        "memory_mb": {name: memory.get(name) for name in ("process_rss_mb", "cgroup_memory_current_mb", "cgroup_memory_limit_mb")},
        "safety": {"v2_shadow_only": True, "v2_production_effect": False,
                   "raw_provider_payloads_included": False, "credentials_included": False},
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


def _warning_kind(message: str) -> tuple[str, str]:
    """Separate company risk from missing verification and valuation uncertainty."""
    text = str(message or "").lower()
    if any(word in text for word in ("primærkild", "tredjepart", "sammenlignbare", "ikke verifisert", "mangler")):
        return "ⓘ", "Datagrunnlag"
    if any(word in text for word in ("inngangsområde", "kursgrense", "p/e-forutsetning", "scenario")):
        return "◇", "Verdsettelse"
    return "⚠️", "Risiko/kvalitet"


def render_quality_valuation(st: Any, market_tickers: Sequence[str] = (), *, expanded: bool = False) -> None:
    with st.expander("Kvalitet, prising og inngangskurs · shadow", expanded=expanded):
        st.caption("Manuell observasjonsanalyse. Starter ingen handel og sender ikke Pushover. Finansdata må kontrolleres i selskapsrapporten.")
        source = st.radio("Aksjer", ["Skriv tickere", "Bruk valgt markedsutvalg"], horizontal=True, key="qv_source")
        raw = st.text_input("Tickere, adskilt med komma", placeholder="EQNR.OL, NHY.OL, YAR.OL", key="qv_tickers") if source == "Skriv tickere" else ""
        selected = [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()] if raw else list(market_tickers)
        if source == "Bruk valgt markedsutvalg":
            st.caption(f"Hele valgt univers undersøkes først: {len(selected)} aksjer. Deretter går inntil {MAX_SYMBOLS} best rangerte videre til full kvalitets-/prisingsanalyse.")
        use_scenario = st.checkbox("Vis priseksempel med P/E jeg velger", value=False, key="qv_use_assumption")
        assumed_pe = st.number_input("P/E-forutsetning (analytisk scenario, ikke fast verdi)", 4.0, 40.0, 15.0, 0.5, key="qv_assumption") if use_scenario else None
        if use_scenario:
            st.warning("Samme P/E på tvers av bransjer er kun et illustrert scenario. Det gir ikke en bekreftet inngangskurs eller automatisk kjøpssignal.")
        run_attempted = st.button("Kjør kvalitetsvurdering", key="qv_run", type="primary", disabled=not bool(selected))
        if run_attempted:
            st.session_state.pop("qv_result", None)
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
                    analysis_selected = selected
                    if source == "Bruk valgt markedsutvalg":
                        from quality_market_prescreen import full_market_prescreen
                        prescreen_bar = st.progress(0, text=f"Undersøker hele markedet · 0/{len(selected)}")
                        def prescreen_progress(done: int, total: int, ticker: str) -> None:
                            prescreen_bar.progress(
                                min(100, round(100 * done / max(total, 1))),
                                text=f"Undersøker hele markedet · {done}/{total} · {ticker}",
                            )
                        prescreen = full_market_prescreen(selected, MAX_SYMBOLS, progress=prescreen_progress)
                        analysis_selected = list(prescreen.get("finalists") or [])
                        if not analysis_selected:
                            raise RuntimeError("Ingen aksjer med brukbare markedsdata etter full markedsscreening")
                        st.session_state["quality_valuation_prescreen"] = prescreen
                    result = run_screen(analysis_selected, isolated_financial_snapshot, assumed_pe=assumed_pe,
                                        progress=update, memory_guard=workload_safe)
                    if source == "Bruk valgt markedsutvalg":
                        result["market_universe_count"] = int(prescreen.get("universe_count") or 0)
                        result["market_examined_count"] = int(prescreen.get("examined_count") or 0)
                        result["market_usable_count"] = int(prescreen.get("usable_count") or 0)
                        result["market_failed_count"] = int(prescreen.get("failed_count") or 0)
                        result["prescreen_finalists"] = analysis_selected
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
        result = st.session_state.get("qv_result")
        if result is None and not run_attempted:
            result = load_latest_manual()
        if not result:
            st.info("Ingen kvalitetsvurdering kjørt ennå.")
            return
        if result.get("market_universe_count") is not None:
            st.info(
                f"Markedsscreening: {int(result.get('market_examined_count') or 0)}/{int(result.get('market_universe_count') or 0)} undersøkt · "
                f"{int(result.get('market_usable_count') or 0)} med brukbare data · "
                f"{len(result.get('prescreen_finalists') or [])} gikk videre til full analyse."
            )
        st.caption(f"Sist lagret: {result.get('generated_at')} · {result.get('state')} · {result.get('completed')}/{result.get('selected')} · {result.get('elapsed_seconds') or 0}s · CPU {result.get('cpu_seconds') or 0}s")
        st.warning("Pushover: IKKE SENDT. Tredjeparts nøkkeltall og P/E-/peer-scenario er ikke kontrollert mot primærkilder. Resultatet er observasjon, ikke kjøpssignal.")
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
                with st.container(border=True):
                    st.markdown(f"**{item['ticker']} · {item['name']}**  \\n{item.get('country') or '-'} · {item.get('industry') or '-'}")
                    st.write(
                        f"Kurs {item.get('price') or '-'} {item.get('currency') or ''} · "
                        f"ROCE {item.get('roce_pct') or '-'}% · P/E {item.get('reported_pe') or '-'} · "
                        f"normalisert P/E {item.get('normalized_pe') or '-'} · scenario {item.get('entry_range_scenario') or '-'}"
                    )
                    if item.get("entry_range_scenario"):
                        st.write(
                            f"Grunnlag: {item.get('valuation_basis') or 'P/E-forutsetning valgt manuelt'} · "
                            f"margin {item.get('entry_buffer_pct')}% basert på resultatvariasjon."
                        )
                    warnings = list(item.get("warnings") or [])[:3]
                    if warnings:
                        rendered = []
                        for warning in warnings:
                            icon, kind = _warning_kind(str(warning))
                            rendered.append(f"- {icon} **{kind}:** {warning}")
                        st.markdown("\n".join(rendered))
        st.markdown("#### Rapporter og deling")
        st.caption("Åpne rapportene via mobil filsiden. Appen blir tilgjengelig i bakgrunnen, og du får egen retur-, delings- og nedlastingsflyt.")
        short_pdf = build_screen_pdf(result)
        diagnosis = diagnostic_document(result)
        extended_pdf = None
        try:
            from quality_extended_report import build_extended_analysis_pdf
            extended_pdf = build_extended_analysis_pdf(result)
        except Exception:
            st.caption("Utvidet analyse-PDF er midlertidig utilgjengelig; kort PDF og diagnose er fortsatt tilgjengelig.")

        try:
            from public_report_store import publish_durable_file, publish_durable_pdf
            delivery_key = f"qv_delivery_{result.get('run_key') or result.get('generated_at') or 'latest'}"
            delivery = st.session_state.get(delivery_key)
            if not isinstance(delivery, dict):
                report_id = str(result.get("report_id") or result.get("run_key") or "")
                short_meta = {"report_id": report_id, "public_pdf_name": "kvalitet_verdsettelse.pdf"}
                delivery = {
                    "short_pdf": publish_durable_pdf(short_meta, short_pdf),
                    "diagnosis": publish_durable_file(
                        diagnosis,
                        filename="kvalitet_verdsettelse_diagnose.json",
                        mime="application/json",
                        report_id=report_id,
                    ),
                }
                if extended_pdf is not None:
                    extended_meta = {"report_id": report_id, "public_pdf_name": "kvalitet_utvidet_analyse.pdf"}
                    delivery["extended_pdf"] = publish_durable_pdf(extended_meta, extended_pdf)
                try:
                    from quality_report_package import build_manual_report_package
                    delivery["package"] = publish_durable_file(
                        build_manual_report_package(result),
                        filename="kvalitet_siste_manuelle_kjoring.zip",
                        mime="application/zip",
                        report_id=report_id,
                    )
                except Exception:
                    pass
                st.session_state[delivery_key] = delivery

            st.link_button(
                "📄 Åpne / del kort PDF",
                f"/?public_report_token={delivery['short_pdf']}&return_to=overview",
                width="stretch",
            )
            if delivery.get("extended_pdf"):
                st.link_button(
                    "📊 Åpne / del utvidet PDF",
                    f"/?public_report_token={delivery['extended_pdf']}&return_to=overview",
                    width="stretch",
                )
            st.link_button(
                "🧾 Åpne / kopier diagnose",
                f"/?public_file_token={delivery['diagnosis']}&return_to=overview",
                width="stretch",
            )
            if delivery.get("package"):
                st.link_button(
                    "📦 Åpne / del komplett kontrollpakke",
                    f"/?public_file_token={delivery['package']}&return_to=overview",
                    width="stretch",
                )
                st.caption("Kontrollpakken inneholder kort PDF, utvidet PDF, diagnose og manifest fra nøyaktig samme run-id.")
            st.caption("PDF-returknappen er skjerm-only og skal ikke komme med ved utskrift.")
        except Exception:
            st.warning("Mobil delingsside er midlertidig utilgjengelig. Bruk reserveknappene under.")
            st.download_button("⬇ Reserve: kort PDF", short_pdf, "kvalitet_verdsettelse.pdf", "application/pdf", key="qv_pdf", use_container_width=True)
            if extended_pdf is not None:
                st.download_button("⬇ Reserve: utvidet PDF", extended_pdf, "kvalitet_utvidet_analyse.pdf", "application/pdf", key="qv_extended_pdf", use_container_width=True)
            st.download_button("⬇ Reserve: diagnose", diagnosis, "kvalitet_verdsettelse_diagnose.json", "application/json", key="qv_diagnosis", use_container_width=True)
        st.caption("Siste manuelle kjøring er lagret og kan åpnes igjen etter at du har vært på andre sider.")
        if st.button("⌂ Hovedsiden", key="qv_home", use_container_width=True, type="primary"):
            st.session_state["ai_control_center_last_applied_nav_v19016"] = ""
            st.query_params["aa_nav"] = "overview"
            st.rerun()
