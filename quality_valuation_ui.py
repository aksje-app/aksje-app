"""Manual shadow screen with bounded acquisition, PDF and diagnostic export."""
from __future__ import annotations

from io import BytesIO
from datetime import datetime, timezone
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping, Sequence
from html import escape

from quality_valuation import GROUPS, MAX_SYMBOLS, ensure_valuation_context, run_screen
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
        "dark_green": colors.HexColor("#0b6b3a"),
        "green": colors.HexColor("#16a34a"),
        "yellow": colors.HexColor("#d97706"),
        "orange": colors.HexColor("#ea580c"),
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

    def score_color(score: Any):
        try:
            score = max(1, min(5, int(score)))
        except (TypeError, ValueError):
            score = 1
        return {
            5: palette["dark_green"],
            4: palette["green"],
            3: palette["yellow"],
            2: palette["orange"],
            1: palette["red"],
        }[score]

    def star_path(cx: float, cy: float, radius: float):
        import math
        path = page.beginPath()
        for index in range(10):
            angle = -math.pi / 2 + index * math.pi / 5
            current_radius = radius if index % 2 == 0 else radius * .45
            x = cx + math.cos(angle) * current_radius
            y = cy + math.sin(angle) * current_radius
            if index == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.close()
        return path

    def rating_stars(x: float, y: float, stars: Any) -> None:
        try:
            stars = max(1, min(5, int(stars)))
        except (TypeError, ValueError):
            stars = 1
        active = score_color(stars)
        for index in range(5):
            page.setStrokeColor(active if index < stars else palette["grey"])
            page.setFillColor(active if index < stars else colors.white)
            page.drawPath(star_path(x + index * 14, y, 5.2), stroke=1, fill=1)

    def indicator(x: float, y: float, label: str, score: Any) -> None:
        try:
            score = max(1, min(5, int(score)))
        except (TypeError, ValueError):
            score = 1
        page.setFillColor(score_color(score))
        page.circle(x, y + 2, 3.2, stroke=0, fill=1)
        page.setFillColor(colors.black)
        page.setFont(regular, 6.8)
        page.drawString(x + 7, y - 1, _printable(f"{label} {score}/5"))

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
            item = ensure_valuation_context(dict(item))
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
            name_text = f"{label}{item.get('ticker')} - {str(item.get('name') or '')[:44]}"
            y = write(y, name_text, font=bold, size=8.5, x=52)
            rating_stars(365, y + 11, item.get("overall_stars"))
            page.setFillColor(score_color(item.get("overall_stars")))
            page.setFont(bold, 7)
            page.drawString(440, y + 8, _printable(str(item.get("overall_grade_label") or ""))[:20])
            y = write(y, f"{item.get('exchange') or 'Børs ikke dokumentert'} - {item.get('country') or '-'} - {item.get('currency') or '-'}", size=7.2, x=52)
            indicator(55, y + 1, "Kvalitet", item.get("quality_score"))
            indicator(155, y + 1, "Prising", item.get("valuation_score"))
            indicator(250, y + 1, "Trend", item.get("trend_score"))
            indicator(335, y + 1, "Data", item.get("data_score"))
            y -= 12
            y = write(y, str(item.get("why_now") or ""), size=6.7, x=52)
            currency = item.get("currency") or ""
            entry = item.get("entry_range_scenario") or []
            entry_text = (
                f"{entry[0]:.2f}–{entry[1]:.2f} {currency}"
                if len(entry) >= 2 and all(isinstance(value, (int, float)) for value in entry[:2]) else "-"
            )
            y = write(y, "KURS / PRIS", font=bold, size=7.3, x=52)
            y = write(y, f"Kurs nå: {float(item.get('price')):.2f} {currency}" if isinstance(item.get("price"), (int, float)) else "Kurs nå: -", size=7.4, x=58)
            y = write(y, f"Scenarioverdi: {float(item.get('fair_price_scenario')):.2f} {currency}" if isinstance(item.get("fair_price_scenario"), (int, float)) else "Scenarioverdi: -", size=7.4, x=58)
            y = write(y, f"Inngangsscenario: {entry_text}", size=7.4, x=58)
            y = write(y, str(item.get("valuation_position_text") or "Scenarioavstand ikke beregnet."), font=bold, size=6.8, x=58)
            y = write(y, "VERDSETTELSE (multipler, ikke aksjekurs)", font=bold, size=7.3, x=52)
            y = write(y, f"P/E ved dagens kurs: {item.get('reported_pe') if item.get('reported_pe') is not None else '-'}x · Forward P/E: {item.get('forward_pe') if item.get('forward_pe') is not None else '-'}x", size=7.1, x=58)
            y = write(y, f"Normalisert P/E ved dagens kurs: {item.get('normalized_pe') if item.get('normalized_pe') is not None else '-'}x · Peer-median P/E: {item.get('assumed_pe') if item.get('assumed_pe') is not None else '-'}x", size=7.1, x=58)

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
                y = write(y, "Scenario er sammenligning - IKKE KURSMÅL", font=bold, size=7.1, x=52)
                if item.get("peer_count"):
                    thin = " - TYNT GRUNNLAG" if item.get("peer_basis_quality") == "THIN" else ""
                    y = write(y, f"Peers {item.get('peer_count')}{thin}: {', '.join(item.get('peer_tickers') or [])}", size=6.8, x=52)
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
    return add_pdf_return_links(buffer.getvalue(), return_url=_absolute_report_return_url("quality_reports"))

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
        "ticker", "name", "exchange", "country", "industry", "currency", "price", "group",
        "quality_state", "model_version", "sector_policy", "sector_subtype", "review_reason_category",
        "overall_stars", "overall_grade_label", "overall_grade_color", "quality_score", "quality_color",
        "valuation_score", "valuation_color", "trend_score", "trend_color", "data_score", "data_color",
        "grade_confidence", "why_now", "next_star_requirement", "grade_method",
        "sector_specific_evidence", "cycle_valuation_evidence",
        "financial_date", "financial_age_days",
        "reported_pe", "forward_pe", "normalized_pe", "normalized_eps",
        "annual_eps_history", "fiscal_periods", "operating_margin_history", "debt_history",
        "equity_history", "roe_history", "sector", "is_financial",
        "free_cash_flow", "free_cash_flow_history", "fcf_positive_ratio", "roce_pct", "roce_latest_pct", "roce_history_pct",
        "roce_trend", "roe_pct", "roe_latest_pct", "roe_trend",
        "quality_evidence_ready", "evidence_ready", "assumed_pe",
        "fair_price_scenario", "entry_range_scenario", "entry_buffer_pct",
        "peer_count", "peer_tickers", "peer_normalized_pe", "peer_basis_quality",
        "price_vs_scenario_pct", "price_vs_entry_low_pct", "price_vs_entry_high_pct",
        "valuation_position", "valuation_position_text", "valuation_position_color",
        "previous_comparison",
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
        "active_quality_model": "quality_v1.3@1.3",
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


def _star_html(item: Mapping[str, Any]) -> str:
    stars = max(1, min(5, int(item.get("overall_stars") or 1)))
    color = escape(str(item.get("overall_grade_color") or "#64748b"))
    return (
        f'<span style="color:{color};font-weight:800;letter-spacing:1px">'
        + ("★" * stars) + ("☆" * (5 - stars)) + "</span>"
    )


def _indicator_html(label: str, score: Any, color: str) -> str:
    try:
        number = max(1, min(5, int(score)))
    except (TypeError, ValueError):
        number = 1
    safe_color = escape(str(color or "#64748b"))
    return (
        f'<span style="display:inline-block;margin:2px 8px 2px 0">'
        f'<span style="color:{safe_color};font-size:1.15em">●</span> '
        f'<b>{escape(label)}</b> {number}/5</span>'
    )


def _multiple(value: Any) -> str:
    try:
        number = float(value)
        return f"{number:.2f}x".replace(".", ",")
    except (TypeError, ValueError):
        return "-"


def _money(value: Any, currency: Any) -> str:
    try:
        number = float(value)
        return f"{number:.2f} {str(currency or '').strip()}".strip().replace(".", ",")
    except (TypeError, ValueError):
        return "-"


def _score_delta_label(value: Any) -> str:
    try:
        delta = int(value)
    except (TypeError, ValueError):
        return ""
    if delta > 0:
        return f"↑ +{delta}"
    if delta < 0:
        return f"↓ {delta}"
    return "→ uendret"


def _valuation_blocks_html(item: Mapping[str, Any]) -> str:
    item = ensure_valuation_context(dict(item))
    currency = item.get("currency") or ""
    entry = item.get("entry_range_scenario") or []
    entry_text = "-"
    if len(entry) >= 2:
        entry_text = f"{_money(entry[0], currency)} – {_money(entry[1], currency)}"
    status_color = escape(str(item.get("valuation_position_color") or "#64748b"))
    status_text = escape(str(item.get("valuation_position_text") or "Scenarioavstand ikke beregnet."))
    peer_count = int(item.get("peer_count") or 0)
    peer_note = ""
    if peer_count:
        thin = " · TYNT GRUNNLAG" if str(item.get("peer_basis_quality") or "") == "THIN" else ""
        peer_note = f'<div class="qv-peer-note">Peer-grunnlag: {peer_count} selskaper{thin}</div>'
    return (
        '<div class="qv-value-grid">'
        '<section class="qv-value-box qv-price-box"><span>KURS / PRIS</span>'
        f'<strong>Kurs nå: {_money(item.get("price"), currency)}</strong>'
        f'<div>Scenarioverdi: {_money(item.get("fair_price_scenario"), currency)}</div>'
        f'<div>Inngangsscenario: {escape(entry_text)}</div>'
        f'<b style="color:{status_color}">{status_text}</b>'
        '</section>'
        '<section class="qv-value-box qv-multiple-box"><span>VERDSETTELSE</span>'
        f'<strong>P/E ved dagens kurs: {_multiple(item.get("reported_pe"))}</strong>'
        f'<div>Forward P/E: {_multiple(item.get("forward_pe"))}</div>'
        f'<div>Normalisert P/E ved dagens kurs: {_multiple(item.get("normalized_pe"))}</div>'
        f'<div>Peer-median P/E: {_multiple(item.get("assumed_pe"))}</div>'
        '<small>P/E er multipler, ikke aksjekurs.</small>'
        + peer_note + '</section></div>'
    )


def _quality_report_choice_cards(delivery: Mapping[str, Any]) -> str:
    """Aurora-style report selector: text first, no decorative icon holders."""
    choices = [
        (
            "Kort rapport",
            "Rask oversikt over utvalgte aksjer, stjerner, prising og viktigste funn.",
            f"/?public_report_token={delivery.get('short_pdf')}&return_to=quality_reports",
            True,
        ),
    ]
    if delivery.get("extended_pdf"):
        choices.append((
            "Full analyse",
            "Detaljer, historikk, grafer og faglig grunnlag.",
            f"/?public_report_token={delivery.get('extended_pdf')}&return_to=quality_reports",
            False,
        ))
    choices.append((
        "Diagnose",
        "Teknisk kontrollgrunnlag og data for feilsøking.",
        f"/?public_file_token={delivery.get('diagnosis')}&return_to=quality_reports",
        False,
    ))
    if delivery.get("package"):
        choices.append((
            "Last ned alt",
            "Kort rapport, full analyse, diagnose og manifest samlet i én kontrollpakke.",
            f"/?public_file_token={delivery.get('package')}&return_to=quality_reports",
            False,
        ))

    cards = []
    for title, description, href, recommended in choices:
        badge = (
            '<span style="font-size:.72rem;font-weight:850;letter-spacing:.08em;color:#5eead4;'
            'border:1px solid #2dd4bf;border-radius:999px;padding:.18rem .5rem">ANBEFALT</span>'
            if recommended else ""
        )
        cards.append(
            '<a href="' + escape(href, quote=True) + '" target="_self" '
            'style="display:block;padding:1rem 1.05rem;border:1px solid #24445c;border-radius:.95rem;'
            'background:linear-gradient(180deg,#0a1d2d,#071522);text-decoration:none;color:#f4fbff;'
            'box-shadow:0 10px 24px rgba(0,0,0,.12)">'
            '<div style="display:flex;align-items:center;justify-content:space-between;gap:.7rem">'
            '<strong style="font-size:1.05rem">' + escape(title) + '</strong>' + badge + '</div>'
            '<div style="margin-top:.35rem;color:#a8bdcc;font-size:.9rem;line-height:1.38">'
            + escape(description) + '</div></a>'
        )
    return (
        '<section data-testid="quality-report-choices" style="display:grid;gap:.72rem;margin:.65rem 0 1rem">'
        '<a href="/?aa_nav=quality_valuation" target="_self" '
        'style="display:inline-block;width:max-content;max-width:100%;padding:.55rem .78rem;'
        'border:1px solid #2b7182;border-radius:.7rem;background:#0c2735;color:#e6f7fb;'
        'text-decoration:none;font-weight:800">← Tilbake til Kvalitet</a>'
        + "".join(cards) + '</section>'
    )


def _render_quality_report_choices(st: Any, result: Mapping[str, Any]) -> None:
    st.markdown("#### Rapporter og deling")
    st.caption("Velg hva du vil gjøre. Kort rapport er laget for rask lesing; full analyse viser hele grunnlaget.")

    short_pdf = build_screen_pdf(result)
    diagnosis = diagnostic_document(result)
    extended_pdf = None
    try:
        from quality_extended_report import build_extended_analysis_pdf
        extended_pdf = build_extended_analysis_pdf(result)
    except Exception:
        st.caption("Full analyse er midlertidig utilgjengelig. Kort rapport og diagnose kan fortsatt brukes.")

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

        st.markdown(_quality_report_choice_cards(delivery), unsafe_allow_html=True)
    except Exception:
        st.error("Rapportsiden kunne ikke publiseres akkurat nå.")
        with st.expander("Reserve: direkte filer", expanded=False):
            st.download_button(
                "Kort rapport",
                short_pdf,
                "kvalitet_verdsettelse.pdf",
                "application/pdf",
                key="qv_pdf_fallback",
                use_container_width=True,
            )
            if extended_pdf is not None:
                st.download_button(
                    "Full analyse",
                    extended_pdf,
                    "kvalitet_utvidet_analyse.pdf",
                    "application/pdf",
                    key="qv_extended_pdf_fallback",
                    use_container_width=True,
                )
            st.download_button(
                "Diagnose",
                diagnosis,
                "kvalitet_verdsettelse_diagnose.json",
                "application/json",
                key="qv_diagnosis_fallback",
                use_container_width=True,
            )


def _inject_quality_card_css(st: Any) -> None:
    st.markdown(
        """
        <style>
        .qv-value-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.65rem;margin:.5rem 0 .7rem}
        .qv-value-box{border:1px solid rgba(100,116,139,.34);border-radius:13px;padding:.75rem .85rem;background:rgba(8,23,38,.66)}
        .qv-value-box>span{display:block;font-size:.68rem;font-weight:900;letter-spacing:.08em;color:#8fa4b6;margin-bottom:.35rem}
        .qv-value-box>strong,.qv-value-box>div,.qv-value-box>b,.qv-value-box>small{display:block;margin:.16rem 0}
        .qv-value-box>strong{font-size:.95rem;color:#f3f7fb}.qv-value-box>div{font-size:.83rem;color:#cbd5e1}
        .qv-value-box>b{font-size:.8rem;margin-top:.38rem}.qv-value-box>small,.qv-peer-note{font-size:.72rem;color:#7fb4d5}
        .qv-multiple-box{border-color:rgba(59,130,246,.34)}.qv-price-box{border-color:rgba(45,212,191,.28)}
        @media(max-width:760px){.qv-value-grid{grid-template-columns:1fr}.qv-value-box{padding:.72rem}.qv-value-box>strong{font-size:.94rem}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def resolve_market_bound_manual_tickers(
    requested: Sequence[str],
    market_tickers: Sequence[str],
) -> tuple[list[str], list[str]]:
    """Resolve manual symbols strictly inside the selected market universe.

    A bare symbol may map to one qualified market symbol (for example EQNR ->
    EQNR.OL) only when that base symbol is unique inside the selected universe.
    No global/provider fallback is allowed here.
    """
    universe = [str(value or "").strip() for value in market_tickers if str(value or "").strip()]
    exact = {value.upper(): value for value in universe}
    by_base: dict[str, list[str]] = {}
    for value in universe:
        base = value.upper().split(".", 1)[0]
        by_base.setdefault(base, []).append(value)

    resolved: list[str] = []
    errors: list[str] = []
    for raw in requested:
        token = str(raw or "").strip()
        if not token:
            continue
        upper = token.upper()
        match = exact.get(upper)
        if match is None:
            matches = by_base.get(upper.split(".", 1)[0], [])
            if len(matches) == 1 and "." not in upper:
                match = matches[0]
            elif len(matches) > 1 and "." not in upper:
                errors.append(f"{token}: flere treff i valgt marked – bruk full ticker")
                continue
        if match is None:
            errors.append(f"{token}: finnes ikke i valgt marked")
            continue
        if match not in resolved:
            resolved.append(match)
    return resolved, errors


def render_quality_valuation(
    st: Any,
    market_tickers: Sequence[str] = (),
    *,
    selected_market: str = "",
    expanded: bool = False,
) -> None:
    _inject_quality_card_css(st)
    with st.expander("Kvalitet, prising og inngangskurs · shadow", expanded=expanded):
        st.caption("Manuell observasjonsanalyse. Starter ingen handel og sender ikke Pushover. Finansdata må kontrolleres i selskapsrapporten.")
        source = st.radio("Aksjer", ["Skriv tickere", "Bruk valgt markedsutvalg"], horizontal=True, key="qv_source")
        raw = st.text_input("Tickere, adskilt med komma", placeholder="EQNR.OL, NHY.OL, YAR.OL", key="qv_tickers") if source == "Skriv tickere" else ""
        typed = [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()] if raw else []
        market_errors: list[str] = []
        if source == "Skriv tickere":
            selected, market_errors = resolve_market_bound_manual_tickers(typed, market_tickers)
            if selected_market:
                st.caption(f"Manuelt søk er låst til valgt marked: {selected_market}. Ingen global ticker-gjetting brukes.")
            if market_errors:
                st.error("Marked/ticker stemmer ikke: " + " · ".join(market_errors))
        else:
            selected = list(market_tickers)
            st.caption(f"Hele valgt univers undersøkes først: {len(selected)} aksjer. Deretter går inntil {MAX_SYMBOLS} best rangerte videre til full kvalitets-/prisingsanalyse.")
        use_scenario = st.checkbox("Vis priseksempel med P/E jeg velger", value=False, key="qv_use_assumption")
        assumed_pe = st.number_input("P/E-forutsetning (analytisk scenario, ikke fast verdi)", 4.0, 40.0, 15.0, 0.5, key="qv_assumption") if use_scenario else None
        if use_scenario:
            st.warning("Samme P/E på tvers av bransjer er kun et illustrert scenario. Det gir ikke en bekreftet inngangskurs eller automatisk kjøpssignal.")
        run_attempted = st.button(
            "Kjør kvalitetsvurdering",
            key="qv_run",
            type="primary",
            disabled=(not bool(selected)) or bool(market_errors),
        )
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
        report_choice_mode = str(st.query_params.get("qv_reports") or "").strip() == "1"
        if report_choice_mode:
            _render_quality_report_choices(st, result)
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
                    st.markdown(
                        f"<b>{escape(str(item['ticker']))} · {escape(str(item['name']))}</b> · "
                        f"{_star_html(item)} <b>{escape(str(item.get('overall_grade_label') or ''))}</b><br>"
                        f"<span style='color:#64748b'>{escape(str(item.get('exchange') or 'Børs ikke dokumentert'))} · "
                        f"{escape(str(item.get('country') or '-'))} · {escape(str(item.get('currency') or '-'))}</span>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        _indicator_html("Kvalitet", item.get("quality_score"), str(item.get("quality_color") or ""))
                        + _indicator_html("Prising", item.get("valuation_score"), str(item.get("valuation_color") or ""))
                        + _indicator_html("Trend", item.get("trend_score"), str(item.get("trend_color") or ""))
                        + _indicator_html("Data", item.get("data_score"), str(item.get("data_color") or "")),
                        unsafe_allow_html=True,
                    )
                    st.caption(str(item.get("why_now") or ""))
                    metric_name = "ROE" if item.get("sector_policy") == "FINANCIAL" else "ROCE"
                    metric_value = item.get("roe_pct") if metric_name == "ROE" else item.get("roce_pct")
                    st.write(f"{metric_name}: {metric_value if metric_value is not None else '-'}%")
                    st.markdown(_valuation_blocks_html(item), unsafe_allow_html=True)
                    previous = item.get("previous_comparison") if isinstance(item.get("previous_comparison"), Mapping) else {}
                    if previous.get("comparable"):
                        star_change = _score_delta_label(previous.get("star_delta"))
                        q_change = _score_delta_label(previous.get("quality_score_delta"))
                        p_change = _score_delta_label(previous.get("valuation_score_delta"))
                        group_change = (
                            f" · gruppe: {previous.get('previous_group')} → {item.get('group')}"
                            if previous.get("group_changed") else ""
                        )
                        st.caption(f"Siden forrige sammenlignbare kjøring: stjerner {star_change} · kvalitet {q_change} · prising {p_change}{group_change}")
                    st.caption(str(item.get("next_star_requirement") or ""))
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
        _render_quality_report_choices(st, result)
