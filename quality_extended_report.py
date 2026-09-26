"""Extended Quality analysis PDF with traceable historical evidence."""
from __future__ import annotations

from io import BytesIO
from typing import Any, Mapping


def _safe(value: Any) -> str:
    return str(value if value is not None else "-").encode("latin-1", errors="replace").decode("latin-1")


def _all_rows(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for rows in (result.get("groups") or {}).values() for row in rows]


def build_extended_analysis_pdf(result: Mapping[str, Any]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors

    out = BytesIO()
    pdf = canvas.Canvas(out, pagesize=A4)
    width, height = A4

    def header(title: str, subtitle: str = "") -> float:
        pdf.setFont("Helvetica-Bold", 15)
        pdf.drawString(38, height - 42, _safe(title)[:82])
        pdf.setFont("Helvetica", 8)
        pdf.drawString(38, height - 58, _safe(subtitle)[:120])
        return height - 82

    def line(y: float, text: str, *, bold: bool = False, size: int = 8) -> float:
        if y < 48:
            pdf.showPage()
            y = header("Utvidet kvalitetsanalyse", f"Run {result.get('run_key') or '-'}")
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        pdf.drawString(40, y, _safe(text)[:125])
        return y - (size + 5)

    y = header("Utvidet kvalitet og verdsettelse",
               f"Generert {result.get('generated_at') or '-'} · aktiv quality_v1.1 · V2 shadow")
    y = line(y, "Dette er dokumentasjon av analysegrunnlaget, ikke en kjøpsordre.")
    y = line(y, f"Marked: undersøkt {result.get('market_examined_count') or '-'} / {result.get('market_universe_count') or '-'} · full dekning: {'JA' if result.get('market_coverage_complete') else 'NEI'}")
    shadow = result.get("quality_v2_shadow") or {}
    oversight = result.get("quality_v2_oversight") or {}
    y = line(y, f"V2 shadow: {shadow.get('evaluated', 0)} vurdert · uenighet {shadow.get('disagreement_count', 0)} · komplette shadow-kjøringer {oversight.get('complete_runs', 0)}")
    y = line(y, f"Neste V2-beslutningspunkt: {oversight.get('next_milestone') or 'BESLUTNING KREVES'}")
    y -= 8

    def chart(y: float, title: str, values: list[Any], labels: list[str], *, percent: bool = False) -> float:
        nums = []
        for value in values:
            try:
                nums.append(float(value) * (100 if percent else 1))
            except (TypeError, ValueError):
                pass
        if not nums:
            return line(y, f"{title}: IKKE DOKUMENTERT")
        y = line(y, title, bold=True)
        left, chart_w, chart_h = 55, width - 100, 82
        base = y - chart_h
        low, high = min(nums), max(nums)
        span = max(abs(high-low), abs(high)*.05, 1e-9)
        xs = [left + (i * chart_w / max(1, len(nums)-1)) for i in range(len(nums))]
        pts = [(x, base + (value-low)/span*chart_h) for x, value in zip(xs, nums)]
        pdf.setStrokeColor(colors.grey); pdf.line(left, base, left+chart_w, base)
        for a, b in zip(pts, pts[1:]): pdf.line(a[0], a[1], b[0], b[1])
        for idx, ((x, py), value) in enumerate(zip(pts, nums)):
            pdf.circle(x, py, 2, stroke=1, fill=0)
            label = labels[idx] if idx < len(labels) else f"t-{idx}"
            pdf.setFont("Helvetica", 5.5); pdf.drawCentredString(x, base-9, _safe(label)[:10])
            suffix = "%" if percent else ""
            pdf.drawCentredString(x, py+4, f"{value:.1f}{suffix}")
        return base - 18

    shadow_by_ticker = {str(row.get("ticker")): row for row in shadow.get("rows") or []}
    for item in _all_rows(result):
        pdf.showPage()
        y = header(f"{item.get('ticker')} · {item.get('name')}",
                   f"{item.get('country') or '-'} · {item.get('industry') or '-'} · kilde: {item.get('source') or '-'}")
        y = line(y, f"Aktiv V1.1: {item.get('group')} · kvalitetsstatus {item.get('quality_state')}", bold=True, size=10)
        y = line(y, f"Kurs {item.get('price') or '-'} {item.get('currency') or ''} · rapportert P/E {item.get('reported_pe') or '-'} · normalisert P/E {item.get('normalized_pe') or '-'}")
        y = line(y, f"Regnskapsdato {item.get('financial_date') or '-'} · alder {item.get('financial_age_days') if item.get('financial_age_days') is not None else '-'} dager")
        y = line(y, f"ROCE median {item.get('roce_pct') if item.get('roce_pct') is not None else '-'}% · siste {item.get('roce_latest_pct') if item.get('roce_latest_pct') is not None else '-'}% · trend {item.get('roce_trend')}")
        y = line(y, f"FCF positiv historikk: {round((item.get('fcf_positive_ratio') or 0)*100,1) if item.get('fcf_positive_ratio') is not None else '-'}% · siste FCF {item.get('free_cash_flow') if item.get('free_cash_flow') is not None else '-'}")
        y -= 5

        history = list(item.get("roce_history_pct") or [])
        if history:
            y = line(y, "ROCE-historikk (nyeste først)", bold=True)
            left, chart_w, chart_h = 55, width - 100, 105
            base = y - chart_h
            low, high = min(history + [0]), max(history + [12])
            span = max(1.0, high - low)
            pdf.setStrokeColor(colors.grey)
            pdf.line(left, base, left + chart_w, base)
            threshold_y = base + (12 - low) / span * chart_h
            pdf.setDash(3, 2); pdf.line(left, threshold_y, left + chart_w, threshold_y); pdf.setDash()
            if len(history) == 1:
                xs = [left + chart_w / 2]
            else:
                xs = [left + i * chart_w / (len(history)-1) for i in range(len(history))]
            points = [(x, base + (value-low)/span*chart_h) for x, value in zip(xs, history)]
            for a, b in zip(points, points[1:]):
                pdf.line(a[0], a[1], b[0], b[1])
            for idx, ((x, py), value) in enumerate(zip(points, history)):
                pdf.circle(x, py, 2, stroke=1, fill=0)
                pdf.setFont("Helvetica", 6); pdf.drawCentredString(x, base-10, f"t-{idx}"); pdf.drawCentredString(x, py+5, f"{value:.1f}%")
            pdf.setFont("Helvetica", 6); pdf.drawRightString(left + chart_w, threshold_y + 2, "12% referanse")
            y = base - 22

        eps = list(item.get("annual_eps_history") or [])
        fcf = list(item.get("free_cash_flow_history") or [])
        periods = list(item.get("fiscal_periods") or [])
        y = line(y, f"Faktiske tilgjengelige regnskapsperioder: {periods or 'IKKE DOKUMENTERT'}")
        y = chart(y, "EPS-historikk", eps, periods)
        y = chart(y, "FCF-historikk", fcf, periods)
        y = chart(y, "Driftsmargin", list(item.get("operating_margin_history") or []), periods, percent=True)
        y = chart(y, "Gjeld", list(item.get("debt_history") or []), periods)
        y = chart(y, "ROE (finans)", list(item.get("roe_history") or []), periods, percent=True)
        y = line(y, "ROIC-historikk: IKKE DOKUMENTERT i nåværende providergrunnlag.")
        y = line(y, "Kurs-historikk: IKKE DOKUMENTERT i denne rapportkjøringen.")

        v2 = shadow_by_ticker.get(str(item.get("ticker")), {})
        y = line(y, "Quality Model V2 · SHADOW · ingen produksjonseffekt", bold=True, size=9)
        y = line(y, f"V2 kvalitet {v2.get('quality_band') or '-'} · ROCE-trend {v2.get('roce_trend') or '-'} · FCF {v2.get('fcf_quality') or '-'}")
        y = line(y, f"ROIC-WACC {v2.get('roic_minus_wacc_pct_points') if v2.get('roic_minus_wacc_pct_points') is not None else 'ikke dokumentert'} · moat {v2.get('moat_evidence') or 'NOT_DOCUMENTED'}")
        for reason in v2.get("reasons") or []:
            y = line(y, f"V2: {reason}")
        y -= 5
        y = line(y, "Advarsler / databegrensninger", bold=True)
        for warning in item.get("warnings") or []:
            y = line(y, f"- {warning}")

    pdf.save()
    return out.getvalue()
