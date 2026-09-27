"""Compact extended Quality analysis PDF with sector-aware evidence."""
from __future__ import annotations

from io import BytesIO
from typing import Any, Mapping


def _safe(value: Any) -> str:
    return str(value if value is not None else "-").encode("latin-1", errors="replace").decode("latin-1")


def _all_rows(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    groups = result.get("groups") or {}
    order = ("Attraktivt priset kandidat", "Kvalitetsselskap", "Dyr kvalitet / følges", "Ufullstendig / krever vurdering")
    return [dict(row) for name in order for row in (groups.get(name) or [])]


def _compact_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    magnitude = abs(number)
    if magnitude >= 1_000_000_000:
        return f"{number / 1_000_000_000:.2f} mrd."
    if magnitude >= 1_000_000:
        return f"{number / 1_000_000:.1f} mill."
    if magnitude >= 1_000:
        return f"{number / 1_000:.1f}k"
    return f"{number:.2f}".rstrip("0").rstrip(".")


def build_extended_analysis_pdf(result: Mapping[str, Any]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors

    out = BytesIO()
    pdf = canvas.Canvas(out, pagesize=A4)
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

    def header(title: str, subtitle: str = "") -> float:
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica-Bold", 15)
        pdf.drawString(36, height - 40, _safe(title)[:82])
        pdf.setFont("Helvetica", 7.5)
        pdf.drawString(36, height - 55, _safe(subtitle)[:125])
        pdf.setStrokeColor(palette["light"])
        pdf.line(36, height - 63, width - 36, height - 63)
        return height - 82

    def text(y: float, value: str, *, bold: bool = False, size: float = 8, x: float = 40) -> float:
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        pdf.drawString(x, y, _safe(value)[:128])
        return y - (size + 4)

    def dot(x: float, y: float, state: str) -> None:
        color = palette["green"] if state == "good" else palette["red"] if state == "bad" else palette["yellow"] if state == "watch" else palette["blue"]
        pdf.setFillColor(color)
        pdf.circle(x, y + 2, 3.5, stroke=0, fill=1)

    def arrow(x: float, y: float, state: str) -> None:
        color = palette["green"] if state == "good" else palette["red"] if state == "bad" else palette["yellow"]
        pdf.setStrokeColor(color)
        pdf.setFillColor(color)
        if state == "good":
            pdf.line(x, y - 4, x, y + 5)
            pdf.line(x, y + 5, x - 3, y + 1)
            pdf.line(x, y + 5, x + 3, y + 1)
        elif state == "bad":
            pdf.line(x, y + 5, x, y - 4)
            pdf.line(x, y - 4, x - 3, y)
            pdf.line(x, y - 4, x + 3, y)
        else:
            pdf.line(x - 4, y, x + 4, y)
            pdf.line(x + 4, y, x, y + 3)
            pdf.line(x + 4, y, x, y - 3)

    def medal(x: float, y: float, rank: int) -> None:
        if rank not in (1, 2, 3):
            return
        fill = colors.HexColor("#d4af37") if rank == 1 else colors.HexColor("#9ca3af") if rank == 2 else colors.HexColor("#b87333")
        pdf.setFillColor(fill)
        pdf.circle(x, y, 7, stroke=0, fill=1)
        pdf.setFillColor(colors.white)
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawCentredString(x, y - 2.5, str(rank))

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
        path = pdf.beginPath()
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
            pdf.setStrokeColor(active if index < stars else palette["grey"])
            pdf.setFillColor(active if index < stars else colors.white)
            pdf.drawPath(star_path(x + index * 14, y, 5.2), stroke=1, fill=1)

    def indicator(x: float, y: float, label: str, score: Any) -> None:
        try:
            score = max(1, min(5, int(score)))
        except (TypeError, ValueError):
            score = 1
        pdf.setFillColor(score_color(score))
        pdf.circle(x, y + 2, 3.2, stroke=0, fill=1)
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica", 6.8)
        pdf.drawString(x + 7, y - 1, _safe(f"{label} {score}/5"))

    def trend_state(value: str) -> tuple[str, str]:
        value = str(value or "").upper()
        if value in {"FORBEDRENDE", "IMPROVING"}:
            return "good", "OPP"
        if value in {"SVEKKENDE", "WEAKENING"}:
            return "bad", "NED"
        return "watch", "STABIL"

    def mini_chart(y: float, title: str, values: list[Any], labels: list[str], *, percent: bool = False, compact: bool = False) -> float:
        pairs: list[tuple[float, str]] = []
        for idx, value in enumerate(values[:5]):
            try:
                number = float(value) * (100 if percent else 1)
            except (TypeError, ValueError):
                continue
            label = labels[idx] if idx < len(labels) else f"t-{idx}"
            pairs.append((number, str(label)))
        if not pairs:
            return text(y, f"{title}: IKKE DOKUMENTERT", size=7)
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.setFillColor(colors.black)
        pdf.drawString(40, y, _safe(title))
        left, chart_w, chart_h = 62, width - 118, 40
        base = y - 48
        nums = [p[0] for p in pairs]
        low, high = min(nums), max(nums)
        if low == high:
            low -= 1
            high += 1
        span = max(high - low, 1e-9)
        pdf.setStrokeColor(palette["light"])
        pdf.line(left, base, left + chart_w, base)
        xs = [left + i * chart_w / max(1, len(pairs) - 1) for i in range(len(pairs))]
        pts = [(x, base + (value - low) / span * chart_h) for x, (value, _) in zip(xs, pairs)]
        pdf.setStrokeColor(palette["blue"])
        for a, b in zip(pts, pts[1:]):
            pdf.line(a[0], a[1], b[0], b[1])
        for idx, ((x, py), (value, label)) in enumerate(zip(pts, pairs)):
            pdf.setFillColor(palette["blue"])
            pdf.circle(x, py, 2.2, stroke=0, fill=1)
            pdf.setFillColor(colors.black)
            pdf.setFont("Helvetica", 5.4)
            pdf.drawCentredString(x, base - 8, _safe(label)[:9])
            shown = f"{value:.1f}%" if percent else (_compact_number(value) if compact else f"{value:.2f}".rstrip("0").rstrip("."))
            pdf.drawCentredString(x, py + 4, _safe(shown)[:14])
        return base - 13

    rows = _all_rows(result)
    shadow = result.get("quality_v2_shadow") or {}
    oversight = result.get("quality_v2_oversight") or {}
    shadow_by_ticker = {str(row.get("ticker")): row for row in shadow.get("rows") or []}

    y = header(
        "Utvidet kvalitet og verdsettelse",
        f"Generert {result.get('generated_at') or '-'} - aktiv quality_v1.2 - V2 shadow",
    )
    y = text(y, "Dokumentasjon av analysegrunnlaget. Scenario er sammenligning, ikke kursmål eller kjøpsordre.", bold=True)
    y = text(y, f"Marked: undersøkt {result.get('market_examined_count') or '-'} / {result.get('market_universe_count') or '-'} - full dekning: {'JA' if result.get('market_coverage_complete') else 'NEI'}")
    y = text(y, f"V2 shadow: {shadow.get('evaluated', 0)} vurdert - uenighet {shadow.get('disagreement_count', 0)} - komplette shadow-kjøringer {oversight.get('complete_runs', 0)}")
    y = text(y, f"Neste V2-beslutningspunkt: {oversight.get('next_milestone') or 'BESLUTNING KREVES'}")
    y -= 8
    y = text(y, "Bransjepolicy", bold=True, size=10)
    for policy, explanation in (
        ("STANDARD", "ROCE/ROACE + trend + flerårig FCF."),
        ("FINANCIAL", "ROE brukes; industriell ROCE/FCF er ikke kvalitetsporter."),
        ("CYCLICAL", "Flerårig ROCE/FCF gjennom syklus; peer-P/E alene brukes ikke."),
        ("CAPITAL_INTENSIVE", "Lavere ROCE-referanse + flerårig FCF og trend for utility/telekom/infrastruktur."),
        ("REAL_ESTATE", "FFO/AFFO/NAV kreves; vanlig P/E alene er utilstrekkelig."),
    ):
        y = text(y, f"{policy}: {explanation}", size=8)
    y = text(y - 6, f"Selskaper i rapporten: {len(rows)}", bold=True, size=9)

    attractive_rank = 0
    for item in rows:
        pdf.showPage()
        y = header(
            f"{item.get('ticker')} - {item.get('name')}",
            f"{item.get('exchange') or 'Børs ikke dokumentert'} - {item.get('country') or '-'} - {item.get('currency') or '-'} - policy {item.get('sector_policy') or 'STANDARD'}",
        )
        rating_stars(360, height - 41, item.get("overall_stars"))
        pdf.setFillColor(score_color(item.get("overall_stars")))
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.drawString(435, height - 44, _safe(str(item.get("overall_grade_label") or ""))[:18])
        state = "good" if item.get("quality_evidence_ready") else "watch" if item.get("quality_state") in {"WATCH", "SECTOR_METRIC_REQUIRED"} else "bad"
        if item.get("group") == "Attraktivt priset kandidat":
            attractive_rank += 1
            medal(44, y + 1, attractive_rank)
            y = text(y, f"Pallplass {attractive_rank} - Aktiv: {item.get('group')} - kvalitetsstatus {item.get('quality_state')}", bold=True, size=9, x=58)
        else:
            dot(42, y - 1, state)
            y = text(y, f"Aktiv: {item.get('group')} - kvalitetsstatus {item.get('quality_state')}", bold=True, size=9, x=50)

        indicator(43, y + 1, "Kvalitet", item.get("quality_score"))
        indicator(145, y + 1, "Prising", item.get("valuation_score"))
        indicator(242, y + 1, "Trend", item.get("trend_score"))
        indicator(330, y + 1, "Data", item.get("data_score"))
        y -= 12
        y = text(y, str(item.get("why_now") or ""), size=6.8)
        y = text(y, f"Sikkerhet i graden: {item.get('grade_confidence') or '-'} - {item.get('next_star_requirement') or ''}", size=6.4)
        y = text(y, f"Kurs nå {item.get('price') or '-'} {item.get('currency') or ''} - P/E ved dagens kurs {item.get('reported_pe') or '-'} - forward P/E {item.get('forward_pe') or '-'}")
        y = text(y, f"Normalisert P/E ved dagens kurs {item.get('normalized_pe') or '-'} - normalisert EPS {item.get('normalized_eps') or '-'}")
        if item.get("entry_range_scenario"):
            y = text(y, f"Scenarioverdi {item.get('fair_price_scenario')} - inngangsscenario {item.get('entry_range_scenario')} - SCENARIO, IKKE KURSMAL", bold=True)
            peers = list(item.get("peer_tickers") or [])
            peer_pe = list(item.get("peer_normalized_pe") or [])
            if peers:
                basis = ", ".join(f"{ticker}:{pe}" for ticker, pe in zip(peers, peer_pe))
                y = text(y, f"Peer-median P/E {item.get('assumed_pe')} - peers ({len(peers)}): {basis}", size=7)
        else:
            y = text(y, "Ingen automatisk inngangsscenario for denne bransjepolicyen / utilstrekkelig peer-grunnlag.", size=7)

        if item.get("sector_policy") == "FINANCIAL":
            trend_kind, trend_label = trend_state(item.get("roe_trend"))
            arrow(43, y + 1, trend_kind)
            y = text(y, f"ROE median {item.get('roe_pct') if item.get('roe_pct') is not None else '-'}% - siste {item.get('roe_latest_pct') if item.get('roe_latest_pct') is not None else '-'}% - retning {trend_label}", x=52)
        else:
            trend_kind, trend_label = trend_state(item.get("roce_trend"))
            arrow(43, y + 1, trend_kind)
            y = text(y, f"ROCE median {item.get('roce_pct') if item.get('roce_pct') is not None else '-'}% - siste {item.get('roce_latest_pct') if item.get('roce_latest_pct') is not None else '-'}% - retning {trend_label}", x=52)

        y = text(y, f"Regnskapsdato {item.get('financial_date') or '-'} - alder {item.get('financial_age_days') if item.get('financial_age_days') is not None else '-'} dager")
        y = text(y, f"FCF TTM/siste {_compact_number(item.get('free_cash_flow'))} - positiv års-historikk {round((item.get('fcf_positive_ratio') or 0)*100,1) if item.get('fcf_positive_ratio') is not None else '-'}%")
        y = text(y, f"Metode: {item.get('capital_return_method') or '-'}", size=6.7)

        periods = list(item.get("fiscal_periods") or [])
        y = text(y, f"Faktiske tilgjengelige regnskapsperioder: {periods or 'IKKE DOKUMENTERT'}", size=6.7)
        if item.get("sector_policy") == "FINANCIAL":
            y = mini_chart(y, "ROE-historikk", list(item.get("roe_history") or []), periods, percent=True)
        else:
            y = mini_chart(y, "ROCE-historikk", list(item.get("roce_history_pct") or []), periods, percent=False)
        y = mini_chart(y, "EPS-historikk", list(item.get("annual_eps_history") or []), periods)
        y = mini_chart(y, "FCF års-historikk", list(item.get("free_cash_flow_history") or []), periods, compact=True)
        y = mini_chart(y, "Driftsmargin", list(item.get("operating_margin_history") or []), periods, percent=True)
        y = mini_chart(y, "Gjeld", list(item.get("debt_history") or []), periods, compact=True)

        v2 = shadow_by_ticker.get(str(item.get("ticker")), {})
        y = text(y, f"V2 shadow: kvalitet {v2.get('quality_band') or '-'} - FCF {v2.get('fcf_quality') or '-'} - moat {v2.get('moat_evidence') or 'NOT_DOCUMENTED'}", bold=True, size=7.5)
        if v2.get("reasons"):
            y = text(y, f"V2: {str((v2.get('reasons') or [''])[0])}", size=6.4)

        warnings = list(item.get("warnings") or [])
        y = text(y, f"Vurderingsårsak: {item.get('review_reason_category') or '-'}", bold=True, size=7.5)
        for warning in warnings[:3]:
            y = text(y, f"- {warning}", size=6.3)
        if len(warnings) > 3:
            y = text(y, f"... +{len(warnings) - 3} flere advarsler i diagnosefilen.", size=6.3)

    pdf.save()
    from pdf_mobile_return import add_pdf_return_links
    from public_report_ui import _absolute_report_return_url
    return add_pdf_return_links(out.getvalue(), return_url=_absolute_report_return_url("quality_reports"))
