from __future__ import annotations

import csv
import html
import io
import json
from datetime import datetime
from typing import Any, Mapping, Sequence

from services.storage_service import get_storage_service


MARKET_CLIMATE_VERSION = "v1864z"
MARKET_CLIMATE_LATEST_PATH = "analysis_snapshots/market_climate_latest.json"
MARKET_CLIMATE_RUNS_PATH = "analysis_snapshots/market_climate_runs.jsonl"


DEFAULT_MARKET_CLIMATE_SYMBOLS: list[dict[str, str]] = [
    {"key": "sp500", "label": "S&P 500", "symbol": "^GSPC", "category": "Aksjemarked"},
    {"key": "nasdaq", "label": "Nasdaq Composite", "symbol": "^IXIC", "category": "Aksjemarked"},
    {"key": "osebx", "label": "OSEBX", "symbol": "OSEBX.OL", "category": "Norge"},
    {"key": "vix", "label": "VIX", "symbol": "^VIX", "category": "Volatilitet"},
    {"key": "us10y", "label": "US 10Y yield", "symbol": "^TNX", "category": "Renter"},
    {"key": "brent", "label": "Brent olje", "symbol": "BZ=F", "category": "Norge"},
    {"key": "usdnok", "label": "USD/NOK", "symbol": "NOK=X", "category": "Norge"},
]


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        out = float(value)
        if out != out:
            return None
        return out
    except Exception:
        return None


def _clean(values: Sequence[Any]) -> list[float]:
    out: list[float] = []
    for value in values or []:
        number = _to_float(value)
        if number is not None and number > 0:
            out.append(float(number))
    return out


def _series_payload(payload: Any) -> tuple[list[str], list[float], list[float]]:
    if not isinstance(payload, Mapping):
        return [], _clean(payload or []), []
    close = payload.get("close")
    if close is None:
        close = payload.get("values")
    dates = payload.get("dates") or []
    volumes = payload.get("volume") or payload.get("volumes") or []
    clean_close = _clean(close or [])
    clean_volume = _clean(volumes or [])
    date_list = [str(x) for x in dates or []]
    if len(date_list) != len(clean_close):
        date_list = [str(i + 1) for i in range(len(clean_close))]
    return date_list, clean_close, clean_volume


def _round(value: Any, digits: int = 2) -> float | None:
    number = _to_float(value)
    if number is None:
        return None
    return round(number, digits)


def _pct(values: Sequence[float], lookback: int) -> float | None:
    clean = _clean(values)
    if len(clean) <= lookback:
        return None
    base = clean[-lookback - 1]
    if base <= 0:
        return None
    return (clean[-1] / base - 1.0) * 100.0


def _sma(values: Sequence[float], lookback: int) -> float | None:
    clean = _clean(values)
    if len(clean) < lookback:
        return None
    return sum(clean[-lookback:]) / lookback


def _high(values: Sequence[float], lookback: int) -> float | None:
    clean = _clean(values)
    if not clean:
        return None
    return max(clean[-lookback:])


def _score_clamp(value: float) -> int:
    return int(round(max(0.0, min(100.0, value))))


def _format_number(value: Any, suffix: str = "") -> str:
    number = _to_float(value)
    if number is None:
        return "-"
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:.1f}M{suffix}"
    if abs(number) >= 1_000:
        return f"{number:,.0f}{suffix}"
    return f"{number:.2f}{suffix}"


def _market_row(key: str, config: Mapping[str, str], payload: Any) -> dict[str, Any]:
    dates, close, volume = _series_payload(payload)
    last = close[-1] if close else None
    ma50 = _sma(close, 50)
    ma200 = _sma(close, 200)
    high_52w = _high(close, 252)
    pct_1m = _pct(close, 21)
    pct_3m = _pct(close, 63)
    pct_6m = _pct(close, 126)
    pct_from_high = ((last / high_52w - 1.0) * 100.0) if last and high_52w else None
    vol20 = _sma(volume, 20)
    vol50 = _sma(volume, 50)
    last_volume = volume[-1] if volume else None
    return {
        "key": key,
        "Indikator": config.get("label") or key,
        "Ticker": config.get("symbol") or "",
        "Kategori": config.get("category") or "",
        "Observasjoner": len(close),
        "Siste dato": dates[-1] if dates else "",
        "Siste": _round(last),
        "1 mnd %": _round(pct_1m),
        "3 mnd %": _round(pct_3m),
        "6 mnd %": _round(pct_6m),
        "MA50": _round(ma50),
        "MA200": _round(ma200),
        "Over MA50": "Ja" if last and ma50 and last >= ma50 else ("Nei" if last and ma50 else "-"),
        "Over MA200": "Ja" if last and ma200 and last >= ma200 else ("Nei" if last and ma200 else "-"),
        "52u høy": _round(high_52w),
        "% fra 52u høy": _round(pct_from_high),
        "Volum siste": _round(last_volume, 0),
        "Volum 20d": _round(vol20, 0),
        "Volum 50d": _round(vol50, 0),
        "Datastatus": "OK" if len(close) >= 40 else "Mangler",
    }


def _trend_score(row: Mapping[str, Any]) -> int:
    if row.get("Datastatus") != "OK":
        return 50
    score = 50.0
    pct_3m = _to_float(row.get("3 mnd %")) or 0.0
    pct_6m = _to_float(row.get("6 mnd %")) or 0.0
    pct_from_high = _to_float(row.get("% fra 52u høy"))
    score += max(-18.0, min(18.0, pct_3m * 1.45))
    score += max(-14.0, min(14.0, pct_6m * 0.85))
    score += 8 if row.get("Over MA50") == "Ja" else -8
    score += 12 if row.get("Over MA200") == "Ja" else -12
    if pct_from_high is not None:
        if pct_from_high >= -3:
            score += 8
        elif pct_from_high >= -8:
            score += 4
        elif pct_from_high <= -20:
            score -= 10
    return _score_clamp(score)


def _factor(name: str, score: int, status: str, explanation: str, weight: float, evidence: str = "") -> dict[str, Any]:
    return {
        "Faktor": name,
        "Score": _score_clamp(score),
        "Status": status,
        "Vekt": round(float(weight), 2),
        "Bevis": evidence,
        "Forklaring": explanation,
    }


def _manual_float(manual_inputs: Mapping[str, Any], key: str) -> float | None:
    return _to_float(manual_inputs.get(key))


def _valuation_factor(manual_inputs: Mapping[str, Any]) -> dict[str, Any]:
    pb = _manual_float(manual_inputs, "osebx_price_book")
    if pb is None:
        return _factor(
            "Verdsettelse",
            50,
            "Mangler",
            "OSEBX pris/bok er ikke lagt inn/importert. Faktoren holdes nøytral, men confidence reduseres.",
            0.08,
            "Mangler OSEBX P/B",
        )
    score = 68.0
    if pb >= 2.35:
        score -= 24
        status = "Strukket"
    elif pb >= 2.10:
        score -= 12
        status = "Over normalen"
    elif pb <= 1.35:
        score -= 8
        status = "Billig, men mulig stress"
    else:
        status = "Normal"
    return _factor(
        "Verdsettelse",
        _score_clamp(score),
        status,
        "Pris/bok brukes som klimaindikator, ikke som enkeltselskapsanalyse.",
        0.08,
        f"OSEBX P/B {pb:.2f}",
    )


def _sentiment_factor(manual_inputs: Mapping[str, Any]) -> dict[str, Any]:
    bullish = _manual_float(manual_inputs, "aaii_bullish_pct")
    if bullish is None:
        return _factor(
            "Sentiment",
            50,
            "Mangler",
            "Bullish-andel er ikke lagt inn/importert. Faktoren holdes nøytral, men confidence reduseres.",
            0.06,
            "Mangler sentiment",
        )
    score = 66.0
    if bullish >= 55:
        score -= 20
        status = "Eufori-risiko"
    elif bullish <= 22:
        score -= 10
        status = "Frykt/stress"
    elif 32 <= bullish <= 48:
        score += 6
        status = "Balansert"
    else:
        status = "Normal"
    return _factor(
        "Sentiment",
        _score_clamp(score),
        status,
        "AAII/bullish-andel tolkes som klima og posisjonering, ikke som kjøpssignal alene.",
        0.06,
        f"Bullish {bullish:.1f}%",
    )


def _ipo_factor(manual_inputs: Mapping[str, Any]) -> dict[str, Any]:
    ipo_count = _manual_float(manual_inputs, "us_ipo_count")
    if ipo_count is None:
        return _factor(
            "IPO og spekulasjon",
            50,
            "Mangler",
            "IPO-tall er ikke lagt inn/importert. Faktoren holdes nøytral, men confidence reduseres.",
            0.05,
            "Mangler IPO-tall",
        )
    score = 64.0
    if ipo_count >= 220:
        score -= 24
        status = "Høy spekulasjon"
    elif ipo_count >= 150:
        score -= 12
        status = "Aktivt marked"
    elif ipo_count <= 25:
        score -= 12
        status = "Lukket/risikoaversjon"
    else:
        status = "Normal"
    return _factor(
        "IPO og spekulasjon",
        _score_clamp(score),
        status,
        "Høyt IPO-trykk kan varsle spekulativ fase; svært lavt trykk kan varsle risikoaversjon.",
        0.05,
        f"USA IPO-årstall {ipo_count:.0f}",
    )


def _normalized_chart_series(
    series_map: Mapping[str, Any],
    symbol_config: Sequence[Mapping[str, str]],
    keys: set[str],
    max_points: int = 180,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    config_map = {str(item.get("key")): item for item in symbol_config}
    for key in keys:
        config = config_map.get(key, {})
        dates, values, _volume = _series_payload(series_map.get(key))
        if len(values) < 2:
            continue
        dates = dates[-max_points:]
        values = values[-max_points:]
        base = values[0]
        if base <= 0:
            continue
        points = [{"date": dates[i], "value": round((value / base) * 100.0, 2)} for i, value in enumerate(values)]
        out.append({"key": key, "label": config.get("label") or key, "symbol": config.get("symbol") or "", "points": points})
    return out


def build_market_climate_snapshot(
    series_map: Mapping[str, Any] | None = None,
    *,
    manual_inputs: Mapping[str, Any] | None = None,
    symbol_config: Sequence[Mapping[str, str]] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    series_map = series_map or {}
    manual_inputs = dict(manual_inputs or {})
    symbol_config = list(symbol_config or DEFAULT_MARKET_CLIMATE_SYMBOLS)
    config_map = {str(item.get("key")): item for item in symbol_config}
    rows = [_market_row(key, config, series_map.get(key, {})) for key, config in config_map.items()]
    row_by_key = {str(row.get("key")): row for row in rows}

    equity_keys = ["sp500", "nasdaq", "osebx"]
    equity_scores = [_trend_score(row_by_key[key]) for key in equity_keys if key in row_by_key and row_by_key[key].get("Datastatus") == "OK"]
    if equity_scores:
        trend_score = _score_clamp(sum(equity_scores) / len(equity_scores))
        trend_status = "Støttende" if trend_score >= 65 else ("Svak" if trend_score <= 40 else "Blandet")
        trend_evidence = ", ".join(
            f"{row_by_key[key].get('Indikator')}: {_format_number(row_by_key[key].get('3 mnd %'), '%')} 3m"
            for key in equity_keys
            if key in row_by_key and row_by_key[key].get("Datastatus") == "OK"
        )
    else:
        trend_score = 50
        trend_status = "Mangler"
        trend_evidence = "Ingen brede aksjemarkedsserier"

    breadth_count = sum(
        1
        for key in equity_keys
        if key in row_by_key and row_by_key[key].get("Datastatus") == "OK" and row_by_key[key].get("Over MA200") == "Ja"
    )
    breadth_total = sum(1 for key in equity_keys if key in row_by_key and row_by_key[key].get("Datastatus") == "OK")
    breadth_score = _score_clamp(42 + breadth_count * 18 + (trend_score - 50) * 0.25) if breadth_total else 50

    vix_row = row_by_key.get("vix", {})
    vix_last = _to_float(vix_row.get("Siste"))
    if vix_last is None:
        volatility_factor = _factor("Volatilitet og frykt", 50, "Mangler", "VIX mangler, derfor nøytral klimaeffekt.", 0.16, "Mangler VIX")
    else:
        vix_score = 88 if vix_last <= 15 else 74 if vix_last <= 20 else 58 if vix_last <= 25 else 42 if vix_last <= 30 else 24
        vix_1m = _to_float(vix_row.get("1 mnd %")) or 0.0
        if vix_1m > 25:
            vix_score -= 8
        volatility_factor = _factor(
            "Volatilitet og frykt",
            vix_score,
            "Lav frykt" if vix_score >= 70 else ("Stress" if vix_score <= 40 else "Normal"),
            "Lavere VIX støtter risikovilje; høy eller raskt stigende VIX trekker markedsklima ned.",
            0.16,
            f"VIX {vix_last:.1f}, 1m {_format_number(vix_1m, '%')}",
        )

    rate_row = row_by_key.get("us10y", {})
    tnx_last = _to_float(rate_row.get("Siste"))
    if tnx_last is None:
        rate_factor = _factor("Renter og likviditet", 50, "Mangler", "10-års renten mangler, derfor nøytral klimaeffekt.", 0.14, "Mangler US 10Y")
    else:
        yield_pct = tnx_last / 10.0 if tnx_last > 15 else tnx_last
        tnx_1m = _to_float(rate_row.get("1 mnd %")) or 0.0
        rate_score = 63.0 - max(0.0, (yield_pct - 4.0) * 9.0)
        if tnx_1m > 6:
            rate_score -= 7
        if tnx_1m < -4:
            rate_score += 5
        rate_factor = _factor(
            "Renter og likviditet",
            _score_clamp(rate_score),
            "Støttende" if rate_score >= 65 else ("Press" if rate_score <= 42 else "Nøytral"),
            "Fallende/stabile renter støtter multipler og risikoappetitt; bratt renteoppgang trekker ned.",
            0.14,
            f"US 10Y ca. {yield_pct:.2f}%, 1m {_format_number(tnx_1m, '%')}",
        )

    brent_row = row_by_key.get("brent", {})
    usdnok_row = row_by_key.get("usdnok", {})
    brent_3m = _to_float(brent_row.get("3 mnd %"))
    nok_3m = _to_float(usdnok_row.get("3 mnd %"))
    norway_score = 50.0
    norway_bits = []
    if brent_3m is not None:
        norway_score += max(-10.0, min(10.0, brent_3m * 0.6))
        norway_bits.append(f"Brent 3m {_format_number(brent_3m, '%')}")
    if nok_3m is not None:
        norway_score -= max(-8.0, min(8.0, nok_3m * 0.45))
        norway_bits.append(f"USD/NOK 3m {_format_number(nok_3m, '%')}")
    norway_factor = _factor(
        "Norge: olje og valuta",
        _score_clamp(norway_score),
        "OK" if norway_bits else "Mangler",
        "Brent og NOK brukes som grovt klima for Oslo Børs og råvare-/eksportfølsomme aksjer.",
        0.10,
        ", ".join(norway_bits) if norway_bits else "Mangler Brent/USDNOK",
    )

    factors = [
        _factor(
            "Bred trend og momentum",
            trend_score,
            trend_status,
            "Måler om brede indekser har positiv 3-6 måneders trend, ligger over MA50/MA200 og holder seg nær 52-ukers høyde.",
            0.25,
            trend_evidence,
        ),
        _factor(
            "Markedsbredde-proxy",
            breadth_score,
            "Støttende" if breadth_score >= 65 else ("Svak" if breadth_score <= 40 else "Blandet"),
            "Teller hvor mange brede markeder som er over 200-dagers snitt. Dette er en proxy, ikke ekte aksje-for-aksje breadth ennå.",
            0.16,
            f"{breadth_count}/{breadth_total} brede markeder over MA200" if breadth_total else "Mangler breddegrunnlag",
        ),
        volatility_factor,
        rate_factor,
        norway_factor,
        _valuation_factor(manual_inputs),
        _sentiment_factor(manual_inputs),
        _ipo_factor(manual_inputs),
    ]

    total_weight = sum(float(row.get("Vekt") or 0) for row in factors) or 1.0
    climate_score = _score_clamp(sum(float(row.get("Score") or 50) * float(row.get("Vekt") or 0) for row in factors) / total_weight)
    available_factors = sum(1 for row in factors if row.get("Status") != "Mangler")
    confidence = _score_clamp(42 + available_factors * 6 + min(16, len(equity_scores) * 5))
    missing = [str(row.get("Faktor")) for row in factors if row.get("Status") == "Mangler"]

    if climate_score >= 70:
        label = "Risk-on / støttende"
        action = "Markedsklima støtter offensiv kandidatjakt, men enkeltselskap må fortsatt ha egne signaler."
    elif climate_score >= 55:
        label = "Moderat støttende"
        action = "Normal kandidatjakt. Prioriter aksjer med sterke egne signaler og frisk datakvalitet."
    elif climate_score >= 40:
        label = "Blandet / nøytralt"
        action = "Krev bedre aksjespesifikke bevis, og reduser vekt på gamle institusjonelle kilder."
    else:
        label = "Risk-off / krevende"
        action = "Bruk defensiv kandidatjakt. Bare svært sterke og ferske aksjesignaler bør slippe høyt opp."

    snapshot = {
        "version": MARKET_CLIMATE_VERSION,
        "created_at": generated_at or datetime.now().isoformat(timespec="seconds"),
        "climate_score": climate_score,
        "confidence": confidence,
        "label": label,
        "action": action,
        "summary": f"{label}: score {climate_score}/100, confidence {confidence}%. {action}",
        "missing_factors": missing,
        "manual_inputs": manual_inputs,
        "symbol_config": [dict(item) for item in symbol_config],
        "market_rows": rows,
        "factor_rows": factors,
        "chart_series": _normalized_chart_series(series_map, symbol_config, {"sp500", "nasdaq", "osebx"}),
        "round_note": "Runde 1: Markedsklima lagres og rapporteres som beslutningsstøtte. Det påvirker ikke AI Kandidattest-score før Runde 2.",
    }
    return snapshot


def save_market_climate_snapshot(snapshot: Mapping[str, Any]) -> None:
    storage = get_storage_service()
    storage.write_json(MARKET_CLIMATE_LATEST_PATH, dict(snapshot))
    storage.append_jsonl(MARKET_CLIMATE_RUNS_PATH, dict(snapshot))


def load_latest_market_climate_snapshot() -> dict[str, Any] | None:
    data = get_storage_service().read_json(MARKET_CLIMATE_LATEST_PATH, default=None)
    return data if isinstance(data, dict) else None


def market_climate_to_json(snapshot: Mapping[str, Any]) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=2, default=str)


def market_climate_to_csv(snapshot: Mapping[str, Any]) -> str:
    rows: list[dict[str, Any]] = []
    for item in snapshot.get("factor_rows") or []:
        if isinstance(item, Mapping):
            rows.append({"Seksjon": "Faktor", **dict(item)})
    for item in snapshot.get("market_rows") or []:
        if isinstance(item, Mapping):
            rows.append({"Seksjon": "Marked", **dict(item)})
    if not rows:
        return ""
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(str(key))
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def _html_table(rows: Sequence[Mapping[str, Any]], columns: Sequence[str] | None = None) -> str:
    rows = [dict(row) for row in rows if isinstance(row, Mapping)]
    if not rows:
        return "<p>Ingen rader.</p>"
    if not columns:
        columns = list(rows[0].keys())
    head = "".join(f"<th>{html.escape(str(col))}</th>" for col in columns)
    body = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(str(row.get(col, '')))}</td>" for col in columns)
        body.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _svg_factor_bars(factors: Sequence[Mapping[str, Any]]) -> str:
    rows = [row for row in factors if isinstance(row, Mapping)]
    if not rows:
        return ""
    width = 900
    row_h = 34
    height = 44 + len(rows) * row_h
    parts = [f"<svg viewBox='0 0 {width} {height}' width='100%' height='{height}' role='img'>"]
    parts.append("<rect width='100%' height='100%' fill='#ffffff'/>")
    parts.append("<text x='14' y='24' font-size='16' font-weight='700' fill='#111827'>Markedsklima - faktorscore</text>")
    for i, row in enumerate(rows):
        y = 44 + i * row_h
        score = max(0.0, min(100.0, float(row.get("Score") or 0)))
        bar_w = score * 5.3
        color = "#16a34a" if score >= 70 else "#f59e0b" if score >= 45 else "#dc2626"
        parts.append(f"<text x='14' y='{y + 18}' font-size='12' fill='#111827'>{html.escape(str(row.get('Faktor') or ''))}</text>")
        parts.append(f"<rect x='245' y='{y + 5}' width='530' height='15' fill='#e5e7eb'/>")
        parts.append(f"<rect x='245' y='{y + 5}' width='{bar_w:.1f}' height='15' fill='{color}'/>")
        parts.append(f"<text x='790' y='{y + 18}' font-size='12' fill='#111827'>{score:.0f}/100</text>")
    parts.append("</svg>")
    return "".join(parts)


def _svg_line_chart(series: Sequence[Mapping[str, Any]]) -> str:
    rows = [row for row in series if isinstance(row, Mapping) and row.get("points")]
    if not rows:
        return ""
    width, height = 900, 320
    left, right, top, bottom = 52, 28, 34, 42
    values = []
    for row in rows:
        for point in row.get("points") or []:
            if isinstance(point, Mapping):
                value = _to_float(point.get("value"))
                if value is not None:
                    values.append(value)
    if not values:
        return ""
    lo, hi = min(values), max(values)
    if hi == lo:
        hi += 1
        lo -= 1
    colors = ["#0284c7", "#16a34a", "#f97316", "#7c3aed"]
    parts = [f"<svg viewBox='0 0 {width} {height}' width='100%' height='{height}' role='img'>"]
    parts.append("<rect width='100%' height='100%' fill='#ffffff'/>")
    parts.append("<text x='14' y='22' font-size='16' font-weight='700' fill='#111827'>Bredt marked normalisert til 100</text>")
    for tick in range(5):
        y = top + tick * ((height - top - bottom) / 4)
        value = hi - tick * ((hi - lo) / 4)
        parts.append(f"<line x1='{left}' y1='{y:.1f}' x2='{width - right}' y2='{y:.1f}' stroke='#e5e7eb'/>")
        parts.append(f"<text x='8' y='{y + 4:.1f}' font-size='11' fill='#6b7280'>{value:.0f}</text>")
    for idx, row in enumerate(rows):
        points = [p for p in row.get("points") or [] if isinstance(p, Mapping) and _to_float(p.get("value")) is not None]
        if len(points) < 2:
            continue
        color = colors[idx % len(colors)]
        path_points = []
        for j, point in enumerate(points):
            x = left + j * ((width - left - right) / max(1, len(points) - 1))
            value = float(point.get("value"))
            y = top + (hi - value) * ((height - top - bottom) / (hi - lo))
            path_points.append(f"{x:.1f},{y:.1f}")
        parts.append(f"<polyline fill='none' stroke='{color}' stroke-width='2.2' points='{' '.join(path_points)}'/>")
        legend_x = 610 + (idx % 2) * 130
        legend_y = 22 + (idx // 2) * 18
        parts.append(f"<rect x='{legend_x}' y='{legend_y - 10}' width='10' height='10' fill='{color}'/>")
        parts.append(f"<text x='{legend_x + 16}' y='{legend_y}' font-size='12' fill='#111827'>{html.escape(str(row.get('label') or ''))}</text>")
    parts.append("</svg>")
    return "".join(parts)


def market_climate_report_html(snapshot: Mapping[str, Any]) -> str:
    factors = [row for row in snapshot.get("factor_rows") or [] if isinstance(row, Mapping)]
    markets = [row for row in snapshot.get("market_rows") or [] if isinstance(row, Mapping)]
    css = """
    body{font-family:Arial,sans-serif;color:#111827;margin:18px;background:#fff}
    h1{font-size:24px;margin:0 0 6px} h2{font-size:18px;margin:20px 0 8px}
    .meta{color:#4b5563;font-size:12px;margin-bottom:12px}.summary{border:1px solid #cbd5e1;background:#f8fafc;padding:12px;border-radius:8px}
    table{border-collapse:collapse;width:100%;font-size:12px;margin:8px 0 18px}th,td{border:1px solid #d1d5db;padding:6px;text-align:left;vertical-align:top}th{background:#f3f4f6}
    .print{margin:0 0 12px;padding:6px 10px}.note{color:#4b5563;font-size:12px}
    @media print{.print{display:none} body{margin:8px}}
    """
    factor_cols = ["Faktor", "Score", "Status", "Vekt", "Bevis", "Forklaring"]
    market_cols = ["Indikator", "Ticker", "Kategori", "Siste dato", "Siste", "1 mnd %", "3 mnd %", "6 mnd %", "Over MA50", "Over MA200", "52u høy", "% fra 52u høy", "Datastatus"]
    return f"""<!doctype html>
<html lang="no">
<head><meta charset="utf-8"><title>Markedsklima rapport</title><style>{css}</style></head>
<body>
<button class="print" onclick="window.print()">Skriv ut / lagre som PDF</button>
<h1>Markedsklima rapport</h1>
<div class="meta">Oppdatert: {html.escape(str(snapshot.get("created_at") or ""))} | Versjon: {html.escape(str(snapshot.get("version") or ""))}</div>
<div class="summary"><b>{html.escape(str(snapshot.get("label") or ""))}</b><br>
Score {html.escape(str(snapshot.get("climate_score") or ""))}/100 | Confidence {html.escape(str(snapshot.get("confidence") or ""))}%<br>
{html.escape(str(snapshot.get("action") or ""))}</div>
<p class="note">{html.escape(str(snapshot.get("round_note") or ""))}</p>
{_svg_factor_bars(factors)}
{_svg_line_chart(snapshot.get("chart_series") or [])}
<h2>Faktorer</h2>{_html_table(factors, factor_cols)}
<h2>Markedstall</h2>{_html_table(markets, market_cols)}
</body></html>"""
