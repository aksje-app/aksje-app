"""Trend discovery, early-signal receipts and audit helpers for RC16.31bm.

This layer is descriptive and observational. It never changes production buy
thresholds, risk limits, portfolio gates or trade authorisation. It packages
factual technical fields already produced by candidate enrichment, adds
cross-sectional relative-strength context and explains why each signal may
matter for continuation or caution.
"""
from __future__ import annotations

from typing import Any, Mapping

VERSION = "v19.22.0-rc16.31bm"


def _f(value: Any) -> float | None:
    try:
        x = float(value)
        return x if x == x else None
    except Exception:
        return None


def _b(value: Any) -> bool:
    return bool(value)


def _source(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    return {**dict(candidate), **dict(raw)}


def _pctile(value: float | None, peers: list[float]) -> float | None:
    if value is None or not peers:
        return None
    ordered = sorted(x for x in peers if x == x)
    if not ordered:
        return None
    below = sum(1 for x in ordered if x < value)
    equal = sum(1 for x in ordered if x == value)
    return round(100.0 * (below + 0.5 * equal) / len(ordered), 1)


def _phase(src: Mapping[str, Any]) -> str:
    r5 = _f(src.get("return_5d"))
    r20 = _f(src.get("return_20d") or src.get("return_1m"))
    r60 = _f(src.get("return_60d") or src.get("return_3m"))
    last = _f(src.get("last_price")); s20 = _f(src.get("sma20")); s50 = _f(src.get("sma50")); s200 = _f(src.get("sma200"))
    if r20 is None:
        return "UKJENT"
    above20 = last is not None and s20 not in (None, 0) and last > s20
    above50 = last is not None and s50 not in (None, 0) and last > s50
    above200 = last is not None and s200 not in (None, 0) and last > s200
    accel = _f(src.get("momentum_acceleration_5v20")) or 0.0
    if r20 > 3 and (r5 or 0) > 0 and above20 and (accel > 0.5 or _b(src.get("breakout_20d"))) and not above50:
        return "TIDLIG TREND"
    if r20 > 5 and above20 and above50:
        if r60 is not None and r60 > 24 and (r5 or 0) <= max(0.5, r20 / 6):
            return "MODEN TREND"
        if above200 or s200 is None:
            return "ETABLERT TREND"
    if (r5 or 0) < -2 and r20 > 0:
        return "TREND SVEKKES"
    return "NØYTRAL / UBEKREFTET"


def _early_signal(src: Mapping[str, Any]) -> dict[str, Any]:
    r5 = _f(src.get("return_5d")); r10 = _f(src.get("return_10d")); r20 = _f(src.get("return_20d")); r60 = _f(src.get("return_60d"))
    rsi = _f(src.get("rsi")); vr = _f(src.get("volume_ratio_20")); obv10 = _f(src.get("obv_pressure_10d")); obv20 = _f(src.get("obv_pressure_20d"))
    last = _f(src.get("last_price")); s20 = _f(src.get("sma20")); s50 = _f(src.get("sma50")); s200 = _f(src.get("sma200"))
    p_s20 = _f(src.get("price_vs_sma20_pct"))
    s20_s50 = _f(src.get("sma20_vs_sma50_pct"))
    s50_s200 = _f(src.get("sma50_vs_sma200_pct"))
    if p_s20 is None and last not in (None, 0) and s20 not in (None, 0):
        p_s20 = (last / s20 - 1.0) * 100.0
    if s20_s50 is None and s20 not in (None, 0) and s50 not in (None, 0):
        s20_s50 = (s20 / s50 - 1.0) * 100.0
    if s50_s200 is None and s50 not in (None, 0) and s200 not in (None, 0):
        s50_s200 = (s50 / s200 - 1.0) * 100.0
    accel = _f(src.get("momentum_acceleration_5v20"))
    if accel is None and r5 is not None and r20 is not None:
        accel = r5 - r20 / 4.0
    gc_age = src.get("golden_cross_age_sessions")
    rsi50_age = src.get("rsi_cross_50_age_sessions")
    golden_cross = _b(src.get("golden_cross_active")) or bool(s50 is not None and s200 is not None and s50 > s200)
    d20_high = _f(src.get("distance_from_20d_high_pct"))
    d60_high = _f(src.get("distance_from_60d_high_pct"))
    breakout20 = _b(src.get("breakout_20d")) or (d20_high is not None and d20_high >= -0.05)
    breakout60 = _b(src.get("breakout_60d")) or (d60_high is not None and d60_high >= -0.05)

    signals: list[dict[str, Any]] = []
    cautions: list[str] = []
    score = 0.0

    def add(code: str, points: float, label: str, meaning: str) -> None:
        nonlocal score
        score += points
        signals.append({"code": code, "label": label, "points": points, "meaning": meaning})

    if r5 is not None and r20 is not None and r5 > 1.0 and r20 > 3.0:
        add("MULTI_HORIZON_MOMENTUM", 12, f"5d {r5:+.1f}% / 20d {r20:+.1f}%", "Positiv utvikling på både kort og mellomlang horisont reduserer risikoen for at bevegelsen bare er én tilfeldig sterk dag.")
    if accel is not None and accel > 0.75:
        add("ACCELERATION", 12, f"Stigningstakten øker ({accel:+.1f} pp)", "De siste fem dagene går raskere enn gjennomsnittstakten i 20-dagersperioden; det kan varsle at kjøpspresset tiltar.")
    if p_s20 is not None and p_s20 > 0:
        add("ABOVE_SMA20", 8, f"Kurs {p_s20:+.1f}% over SMA20", "Kurs over kort glidende snitt viser at den nære trendretningen er positiv.")
    if s20_s50 is not None and s20_s50 > 0:
        add("SMA20_ABOVE_SMA50", 10, f"SMA20 {s20_s50:+.1f}% over SMA50", "Kort trend ligger over mellomlang trend, et klassisk tegn på positiv trendstruktur.")
    if s50_s200 is not None and s50_s200 > 0:
        add("SMA50_ABOVE_SMA200", 10, f"SMA50 {s50_s200:+.1f}% over SMA200", "Lang trendstruktur er positiv; dette gir medvind så lenge avstanden ikke kollapser.")
    if golden_cross:
        text = "Golden cross aktiv"
        if gc_age is not None:
            text += f" ({gc_age} økter siden)"
        add("GOLDEN_CROSS", 9, text, "50-dagerssnitt over 200-dagerssnitt bekrefter en positiv langsiktig regimeendring, men er normalt et tregere signal.")
    if breakout20:
        bp = _f(src.get("breakout_20d_pct")) or 0.0
        add("BREAKOUT_20D", 14, f"20d-brudd {bp:+.1f}%", "Kurs over forrige 20-dagers topp viser at nylig motstand er brutt; videre oppgang blir mer sannsynlig hvis bruddet holder og volumet bekrefter.")
    if breakout60:
        bp = _f(src.get("breakout_60d_pct")) or 0.0
        add("BREAKOUT_60D", 8, f"60d-brudd {bp:+.1f}%", "Brudd over en lengre topp viser styrke mot et mer betydelig historisk motstandsnivå.")
    if obv10 is not None and obv10 > 0.08:
        add("OBV_BUY_PRESSURE", 10, f"OBV-kjøpspress 10d {obv10:+.2f}", "On Balance Volume stiger når volum følger oppgangsdager; positivt trykk kan tyde på akkumulering fremfor bare prisstøy.")
    if obv20 is not None and obv20 > 0.05:
        add("OBV_20D_CONFIRM", 6, f"OBV positiv 20d {obv20:+.2f}", "Kjøpspresset er ikke bare kortvarig, men har vært positivt gjennom en lengre periode.")
    if vr is not None and vr >= 1.2:
        add("VOLUME_CONFIRMATION", 8, f"Volum {vr:.2f}x 20d-snitt", "Høyere aktivitet enn normalt gir mer troverdighet til et brudd eller en trendakselerasjon.")
    if rsi is not None and 52 <= rsi <= 68:
        add("RSI_HEALTHY_MOMENTUM", 8, f"RSI {rsi:.1f}", "RSI viser positivt momentum uten å være ekstremt overkjøpt; dette er ofte et bedre fortsettelsesområde enn RSI langt over 70.")
    if rsi50_age is not None and int(rsi50_age) <= 10:
        add("RSI_50_CROSS", 6, f"RSI brøt 50 for {int(rsi50_age)} økter siden", "Et nylig brudd over RSI 50 kan markere skifte fra nøytralt til positivt momentum.")

    if rsi is not None and rsi >= 72:
        cautions.append(f"RSI {rsi:.1f} er overkjøpt; styrken er positiv, men risikoen for kort korreksjon er høyere.")
    if p_s20 is not None and p_s20 >= 8:
        cautions.append(f"Kursen ligger {p_s20:.1f}% over SMA20 og kan være kortsiktig strukket.")
    if breakout20 and vr is not None and vr < 0.8:
        cautions.append(f"20d-brudd uten tydelig volumstøtte ({vr:.2f}x) er mindre robust.")
    if r5 is not None and r20 is not None and r5 < -1.5 and r20 > 3:
        cautions.append("20d-trenden er positiv, men 5d-momentum har snudd ned; følg om dette er en normal pause eller trendbrudd.")

    score = max(0.0, min(100.0, score))
    if score >= 70:
        label = "STERKT TIDLIG STYRKESIGNAL"
    elif score >= 50:
        label = "TIDLIG STYRKESIGNAL"
    elif score >= 30:
        label = "POSITIVT TRENDOPPSETT"
    else:
        label = "INGEN TYDELIG TIDLIG SIGNAL"

    continuation = [s["meaning"] for s in signals[:4]]
    confirmation_checks: list[str] = []
    failure_checks: list[str] = []
    if breakout20 or breakout60:
        confirmation_checks.append("Bruddet holder over tidligere topp i de neste øktene, helst med normalt eller stigende volum.")
        failure_checks.append("Kursen faller raskt tilbake under bruddnivået; det kan være et falskt breakout.")
    if p_s20 is not None and p_s20 > 0:
        confirmation_checks.append("Kursen holder seg over SMA20, og SMA20 fortsetter å peke opp.")
        failure_checks.append("Kursen etablerer seg under SMA20 samtidig som SMA20 flater ut eller faller.")
    if obv10 is not None and obv10 > 0.08:
        confirmation_checks.append("OBV/kjøpspress fortsetter positivt slik at volum bekrefter prisoppgangen.")
        failure_checks.append("OBV svekkes mens kursen stiger; negativ divergens reduserer kvaliteten på oppgangen.")
    if rsi is not None and rsi >= 50:
        confirmation_checks.append("RSI holder seg over 50 uten vedvarende ekstrem overkjøpt tilstand.")
        failure_checks.append("RSI faller under 50 samtidig som kort momentum svekkes.")
    if not confirmation_checks:
        confirmation_checks.append("Se etter samtidig styrking i 5/20d momentum, trendstruktur og volum før signalet oppgraderes.")
    top_labels = [str(x.get("label") or "") for x in signals[:3] if isinstance(x, Mapping)]
    if top_labels:
        summary = f"{label}: " + "; ".join(top_labels) + ". Disse forholdene kan støtte videre oppgang dersom bekreftelsene holder."
    else:
        summary = "Ingen tydelig kombinasjon av tidlige trend-, breakout- og volum-signaler er bekreftet ennå."
    if cautions:
        summary += " Viktigste motargument: " + cautions[0]
    return {
        "score": round(score, 1),
        "label": label,
        "criteria_met": len(signals),
        "signals": signals,
        "cautions": cautions[:4],
        "continuation_case": continuation,
        "continuation_summary": summary,
        "confirmation_checks": confirmation_checks[:4],
        "failure_checks": failure_checks[:4],
        "descriptive_only": True,
    }


def _drivers(src: Mapping[str, Any], early: Mapping[str, Any]) -> list[str]:
    rows: list[tuple[float, str]] = []
    for label, key in (("5d", "return_5d"), ("20d", "return_20d"), ("60d", "return_60d")):
        val = _f(src.get(key))
        if val is not None:
            rows.append((abs(val), f"{label} {val:+.1f} %"))
    vr = _f(src.get("volume_ratio_20"))
    if vr is not None and vr >= 1.2:
        rows.append((min(20.0, vr * 5), f"volum {vr:.2f}x 20d"))
    d20 = _f(src.get("distance_from_20d_high_pct"))
    if d20 is not None and d20 >= -2.0:
        rows.append((8.0, f"{abs(d20):.1f} % fra 20d-topp"))
    for item in list(early.get("signals") or [])[:2]:
        if isinstance(item, Mapping):
            rows.append((float(item.get("points") or 0) + 5.0, str(item.get("label") or "")))
    rows.sort(key=lambda x: x[0], reverse=True)
    out: list[str] = []
    for _, text in rows:
        if text and text not in out:
            out.append(text)
    return out[:4]


def build_trend_receipt(candidate: Mapping[str, Any], history_item: Mapping[str, Any] | None = None) -> dict[str, Any]:
    src = _source(candidate)
    history_item = dict(history_item or {})
    obs = list(history_item.get("observations") or [])
    previous_rank = obs[-1].get("rank") if obs else None
    current_rank = candidate.get("rank")
    rank_delta = None
    try:
        rank_delta = int(previous_rank) - int(current_rank) if previous_rank and current_rank else None
    except Exception:
        pass
    early = _early_signal(src)
    return {
        "version": VERSION,
        "ticker": str(candidate.get("ticker") or ""),
        "market": str(candidate.get("market") or src.get("market") or ""),
        "sector": str(candidate.get("sector") or src.get("sector") or ""),
        "first_discovered_at": history_item.get("first_seen") or candidate.get("created_at") or "",
        "last_seen_at": history_item.get("last_seen") or "",
        "times_seen": int(history_item.get("times_in_list") or len(obs) or 0),
        "rank_change": rank_delta,
        "trend_phase": _phase(src),
        "return_5d_pct": _f(src.get("return_5d")),
        "return_10d_pct": _f(src.get("return_10d")),
        "return_20d_pct": _f(src.get("return_20d") or src.get("return_1m")),
        "return_60d_pct": _f(src.get("return_60d") or src.get("return_3m")),
        "momentum_acceleration_5v20": _f(src.get("momentum_acceleration_5v20")),
        "volume_ratio_20": _f(src.get("volume_ratio_20")),
        "obv_pressure_5d": _f(src.get("obv_pressure_5d")),
        "obv_pressure_10d": _f(src.get("obv_pressure_10d")),
        "obv_pressure_20d": _f(src.get("obv_pressure_20d")),
        "rsi": _f(src.get("rsi")),
        "rsi_cross_50_age_sessions": src.get("rsi_cross_50_age_sessions"),
        "rsi_cross_70_age_sessions": src.get("rsi_cross_70_age_sessions"),
        "sma20": _f(src.get("sma20")),
        "sma50": _f(src.get("sma50")),
        "sma200": _f(src.get("sma200")),
        "price_vs_sma20_pct": _f(src.get("price_vs_sma20_pct")),
        "sma20_vs_sma50_pct": _f(src.get("sma20_vs_sma50_pct")),
        "sma50_vs_sma200_pct": _f(src.get("sma50_vs_sma200_pct")),
        "golden_cross_active": _b(src.get("golden_cross_active")),
        "golden_cross_age_sessions": src.get("golden_cross_age_sessions"),
        "distance_from_20d_high_pct": _f(src.get("distance_from_20d_high_pct")),
        "distance_from_60d_high_pct": _f(src.get("distance_from_60d_high_pct")),
        "breakout_20d": _b(src.get("breakout_20d")),
        "breakout_60d": _b(src.get("breakout_60d")),
        "breakout_20d_pct": _f(src.get("breakout_20d_pct")),
        "breakout_60d_pct": _f(src.get("breakout_60d_pct")),
        "prior_20d_high": _f(src.get("prior_20d_high")),
        "prior_60d_high": _f(src.get("prior_60d_high")),
        "low_20d": _f(src.get("low_20d")),
        "low_60d": _f(src.get("low_60d")),
        "price_trend_60d": list(src.get("price_trend_60d") or [])[-60:],
        "early_signal": early,
        "top_trend_drivers": _drivers(src, early),
        "descriptive_only": True,
    }


def annotate_run(run: dict[str, Any], history: Mapping[str, Any] | None = None) -> dict[str, Any]:
    history = dict(history or {})
    candidates = [row for row in (run.get("candidates") or []) if isinstance(row, Mapping)]
    receipts: list[dict[str, Any]] = []
    for row in candidates:
        ticker = str(row.get("ticker") or "")
        receipt = build_trend_receipt(row, history.get(ticker) if isinstance(history.get(ticker), Mapping) else {})
        row["trend_receipt"] = receipt
        receipts.append(receipt)

    market20 = [_f(r.get("return_20d_pct")) for r in receipts]
    market20f = [x for x in market20 if x is not None]
    market60f = [x for x in (_f(r.get("return_60d_pct")) for r in receipts) if x is not None]
    sectors: dict[str, list[float]] = {}
    for r in receipts:
        val = _f(r.get("return_20d_pct")); sector = str(r.get("sector") or "Ukjent")
        if val is not None:
            sectors.setdefault(sector, []).append(val)
    for r in receipts:
        r["market_rs_20d_percentile"] = _pctile(_f(r.get("return_20d_pct")), market20f)
        r["market_rs_60d_percentile"] = _pctile(_f(r.get("return_60d_pct")), market60f)
        r["sector_rs_20d_percentile"] = _pctile(_f(r.get("return_20d_pct")), sectors.get(str(r.get("sector") or "Ukjent"), []))

    ranked = [r for r in receipts if r.get("return_20d_pct") is not None]
    ranked.sort(key=lambda r: float(r.get("return_20d_pct") or -1e9), reverse=True)
    early = [r for r in receipts if isinstance(r.get("early_signal"), Mapping)]
    early.sort(key=lambda r: (float((r.get("early_signal") or {}).get("score") or 0), float(r.get("return_20d_pct") or -1e9)), reverse=True)
    run["trend_discovery"] = {
        "version": VERSION,
        "mode": "NORWAY_PRODUCTION_STABILIZATION" if run.get("markets") == ["Norge"] else "MULTI_MARKET",
        "top10": ranked[:10],
        "near_candidates": ranked[10:15],
        "early_signal_watchlist": early[:12],
        "coverage": {
            "candidates": len(candidates),
            "with_20d_return": len(ranked),
            "with_60d_chart": sum(1 for r in receipts if len(r.get("price_trend_60d") or []) >= 20),
            "with_early_signal": sum(1 for r in early if float((r.get("early_signal") or {}).get("score") or 0) >= 30),
        },
        "missed_winner_audit": {"state": "COLLECTING_BASELINE", "note": "Sammenlignes mot bredt markedsunivers når nok daglige observasjoner er lagret."},
        "production_scoring_changed": False,
        "explanation": "Tidligsignalene er et separat observasjonslag. De skal finne akselerasjon, brudd og akkumulering tidlig, men kan ikke alene utløse kjøp.",
    }
    return run
