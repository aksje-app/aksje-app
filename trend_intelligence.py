"""Trend discovery and early-opportunity intelligence for RC16.31bn.

Observational only: this module may prioritise which candidates deserve deeper
research, but it never changes production buy thresholds, risk limits,
portfolio gates or trade authorisation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

VERSION = "v19.22.0-rc16.31ci"


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


def _pctile(value: float | None, peers: Sequence[float]) -> float | None:
    if value is None or not peers:
        return None
    ordered = sorted(float(x) for x in peers if x is not None and float(x) == float(x))
    if not ordered:
        return None
    below = sum(1 for x in ordered if x < value)
    equal = sum(1 for x in ordered if x == value)
    return round(100.0 * (below + 0.5 * equal) / len(ordered), 1)


def _phase(src: Mapping[str, Any]) -> str:
    r5 = _f(src.get("return_5d")); r20 = _f(src.get("return_20d") or src.get("return_1m")); r60 = _f(src.get("return_60d") or src.get("return_3m"))
    last = _f(src.get("last_price")); s20 = _f(src.get("sma20")); s50 = _f(src.get("sma50")); s200 = _f(src.get("sma200"))
    if r20 is None:
        return "UKJENT"
    above20 = last is not None and s20 not in (None, 0) and last > s20
    above50 = last is not None and s50 not in (None, 0) and last > s50
    above200 = last is not None and s200 not in (None, 0) and last > s200
    accel = _f(src.get("momentum_acceleration_5v20")) or 0.0
    if r20 > 2 and (r5 or 0) > 0 and above20 and (accel > 0.4 or _b(src.get("breakout_20d"))) and not above50:
        return "TIDLIG TREND"
    if r20 > 5 and above20 and above50:
        if r60 is not None and r60 > 24 and (r5 or 0) <= max(0.5, r20 / 6):
            return "MODEN TREND"
        if above200 or s200 is None:
            return "ETABLERT TREND"
    if (r5 or 0) < -2 and r20 > 0:
        return "TREND SVEKKES"
    return "NØYTRAL / UBEKREFTET"


def _trend_age(src: Mapping[str, Any]) -> tuple[int | None, str]:
    ages = []
    for key in ("breakout_20d_age_sessions", "rsi_cross_50_age_sessions", "rsi_cross_60_age_sessions", "golden_cross_age_sessions"):
        try:
            val = src.get(key)
            if val is not None and 0 <= int(val) <= 60:
                ages.append(int(val))
        except Exception:
            pass
    age = min(ages) if ages else None
    # If no event age exists, use price history condition as a conservative proxy.
    if age is None:
        r5 = _f(src.get("return_5d")); r20 = _f(src.get("return_20d")); p20 = _f(src.get("price_vs_sma20_pct"))
        if r5 is not None and r5 >= 2 and p20 is not None and p20 > 0:
            age = 5
        elif r20 is not None and r20 >= 5 and p20 is not None and p20 > 0:
            age = 20
    if age is None:
        return None, "UKJENT"
    if age <= 5:
        return age, "NY"
    if age <= 15:
        return age, "TIDLIG"
    if age <= 30:
        return age, "ETABLERT"
    return age, "MODEN"


def _fresh_signal(src: Mapping[str, Any]) -> dict[str, Any]:
    """Score recent ignition separately from long-running trend strength."""
    r1 = _f(src.get("return_1d")); r3 = _f(src.get("return_3d")); r5 = _f(src.get("return_5d")); r10 = _f(src.get("return_10d")); r20 = _f(src.get("return_20d")); r60 = _f(src.get("return_60d"))
    a1 = _f(src.get("momentum_acceleration_1v20")); a3 = _f(src.get("momentum_acceleration_3v20")); a5 = _f(src.get("momentum_acceleration_5v20"))
    rsi = _f(src.get("rsi")); vr = _f(src.get("volume_ratio_20")); volume_comparable = bool(src.get("volume_bar_complete") or src.get("volume_time_adjusted")); obv5 = _f(src.get("obv_pressure_5d")); obv10 = _f(src.get("obv_pressure_10d"))
    slope20 = _f(src.get("sma20_slope_5d_pct")); spreadchg = _f(src.get("golden_cross_spread_change_10d_pp")); compression = _f(src.get("compression_ratio_10v40")); expansion = _f(src.get("volatility_expansion_5v20")); close_loc = _f(src.get("close_location_in_day"))
    age, age_label = _trend_age(src)
    score = 0.0; signals=[]; cautions=[]
    def add(code, pts, label, meaning):
        nonlocal score
        score += pts; signals.append({"code":code,"points":pts,"label":label,"meaning":meaning})
    if a3 is not None and a3 > 0.7: add("3D_ACCELERATION", 16, f"3d akselerasjon {a3:+.1f} pp", "De siste tre dagene går raskere enn 20-dagerstakten; dette er et tidlig tegn på at etterspørselen øker.")
    if a5 is not None and a5 > 0.8: add("5D_ACCELERATION", 14, f"5d akselerasjon {a5:+.1f} pp", "Femdagersstigning er sterkere enn normalfarten i 20-dagersperioden.")
    if r3 is not None and r3 > 1.5: add("SHORT_BURST", 9, f"3d {r3:+.1f}%", "Kort kursburst gjør at kandidaten fanges før 20/60-dagers historikk blir dominerende.")
    if _b(src.get("breakout_20d")) or _b(src.get("breakout_holding")):
        hold = int(src.get("breakout_hold_sessions") or 0); b_age = src.get("breakout_20d_age_sessions")
        add("FRESH_BREAKOUT", 18, f"20d-brudd · alder {b_age if b_age is not None else 0} økter · hold {hold}", "Nylig motstand er brutt; 1–3 økter over nivået gir bedre kvalitet enn et enkelt intradag-stikk.")
    if volume_comparable and vr is not None and vr >= 1.35: add("VOLUME_SPIKE", 12, f"Volum {vr:.2f}x 20d", "Et ferskt prisutbrudd med høyere aktivitet har større sannsynlighet for å være institusjonelt støttet.")
    if obv5 is not None and obv5 > 0.10: add("OBV_5D_IGNITION", 10, f"OBV 5d {obv5:+.2f}", "Volumet følger oppgangsdagene; kjøpspresset er ferskt og målbar.")
    if src.get("rsi_cross_50_age_sessions") is not None and int(src.get("rsi_cross_50_age_sessions")) <= 7: add("RSI50_RECENT", 8, f"RSI > 50 for {int(src.get('rsi_cross_50_age_sessions'))} økter siden", "RSI har nylig skiftet fra nøytral til positiv sone.")
    if src.get("rsi_cross_60_age_sessions") is not None and int(src.get("rsi_cross_60_age_sessions")) <= 7: add("RSI60_RECENT", 6, "Nylig RSI-brudd over 60", "Momentumet har flyttet seg videre inn i positiv sone.")
    if _b(src.get("rsi_10d_breakout")): add("RSI_BREAKOUT", 7, "RSI brøt 10d-topp", "RSI bryter sin egen kortsiktige motstand og kan bekrefte prisakselerasjon.")
    if slope20 is not None and slope20 > 0.4: add("SMA20_TURNS_UP", 8, f"SMA20 +{slope20:.1f}% siste 5d", "Det korte glidende snittet peker tydeligere opp, et tegn på at trenden er i ferd med å etablere seg.")
    if spreadchg is not None and spreadchg > 0.25: add("GOLDEN_SPREAD_WIDENS", 6, f"50/200-spread øker {spreadchg:+.2f} pp", "Avstanden mellom SMA50 og SMA200 øker igjen; langsiktig trendstyrke tiltar etter eventuell kompresjon.")
    if compression is not None and compression < 0.55 and expansion is not None and expansion > 1.15: add("COMPRESSION_EXPANSION", 12, "Kompresjon → ekspansjon", "Aksjen har gått fra trangere handelsområde til økt bevegelse, et mønster som ofte følger nye trendstarter.")
    if close_loc is not None and close_loc >= 0.75 and (r1 or 0) > 0: add("STRONG_CLOSE", 5, "Stenger nær dagstopp", "Sterk sluttkurs viser at kjøperne beholdt kontrollen gjennom dagen.")
    if age_label == "NY": add("NEW_TREND_BONUS", 12, f"Trendalder {age or 0} økter", "Signalet er ferskt; det prioriteres foran eldre trender i Fresh Trend-køen.")
    elif age_label == "TIDLIG": add("EARLY_TREND_BONUS", 6, f"Trendalder {age} økter", "Trenden er fortsatt tidlig nok til å fortjene ekstra oppfølging.")
    if age_label in {"ETABLERT","MODEN"}: cautions.append("Trenden er ikke lenger fersk; sterk historikk skal ikke fortrenge helt nye trendstarter i Fresh Trend-køen.")
    if rsi is not None and rsi >= 72: cautions.append(f"RSI {rsi:.1f} er overkjøpt; videre styrke kan fortsette, men kortsiktig korreksjonsrisiko er høyere.")
    if volume_comparable and vr is not None and vr < 0.8 and _b(src.get("breakout_20d")): cautions.append(f"Bruddet har svak volumstøtte ({vr:.2f}x).")
    elif not volume_comparable and vr is not None: cautions.append("Dagens volumbar er ikke ferdig eller tidsjustert; volumet vises, men brukes ikke som negativ bekreftelse.")
    score=max(0.0,min(100.0,score))
    label="NYTT BREAKOUTSIGNAL" if score>=75 and age_label in {"NY","TIDLIG"} else "TIDLIG AKSELERASJON" if score>=55 else "FERSKT POSITIVT OPPSETT" if score>=35 else "INGEN FERSK TENNING"
    return {"score":round(score,1),"label":label,"trend_age_sessions":age,"trend_age":age_label,"signals":signals,"cautions":cautions[:4],"descriptive_only":True}


def _early_signal(src: Mapping[str, Any]) -> dict[str, Any]:
    r5 = _f(src.get("return_5d")); r20 = _f(src.get("return_20d")); r60 = _f(src.get("return_60d")); rsi = _f(src.get("rsi")); vr = _f(src.get("volume_ratio_20")); volume_comparable = bool(src.get("volume_bar_complete") or src.get("volume_time_adjusted")); obv10 = _f(src.get("obv_pressure_10d")); obv20 = _f(src.get("obv_pressure_20d"))
    last = _f(src.get("last_price")); s20 = _f(src.get("sma20")); s50 = _f(src.get("sma50")); s200 = _f(src.get("sma200"))
    p_s20 = _f(src.get("price_vs_sma20_pct")); s20_s50 = _f(src.get("sma20_vs_sma50_pct")); s50_s200 = _f(src.get("sma50_vs_sma200_pct")); accel = _f(src.get("momentum_acceleration_5v20"))
    if p_s20 is None and last not in (None,0) and s20 not in (None,0): p_s20=(last/s20-1)*100
    if s20_s50 is None and s20 not in (None,0) and s50 not in (None,0): s20_s50=(s20/s50-1)*100
    if s50_s200 is None and s50 not in (None,0) and s200 not in (None,0): s50_s200=(s50/s200-1)*100
    if accel is None and r5 is not None and r20 is not None: accel=r5-r20/4
    d20=_f(src.get("distance_from_20d_high_pct")); d60=_f(src.get("distance_from_60d_high_pct"))
    breakout20=_b(src.get("breakout_20d")) or _b(src.get("breakout_holding")) or (d20 is not None and d20 >= -0.05)
    breakout60=_b(src.get("breakout_60d")) or (d60 is not None and d60 >= -0.05)
    signals=[]; cautions=[]; score=0.0
    def add(code,pts,label,meaning):
        nonlocal score
        score+=pts; signals.append({"code":code,"label":label,"points":pts,"meaning":meaning})
    if r5 is not None and r20 is not None and r5>1 and r20>3: add("MULTI_HORIZON_MOMENTUM",12,f"5d {r5:+.1f}% / 20d {r20:+.1f}%","Positiv utvikling på flere horisonter reduserer risikoen for at bevegelsen bare er én sterk dag.")
    if accel is not None and accel>0.75: add("ACCELERATION",12,f"Stigningstakten øker ({accel:+.1f} pp)","Kort fart er høyere enn 20-dagers normalfart.")
    if p_s20 is not None and p_s20>0: add("ABOVE_SMA20",8,f"Kurs {p_s20:+.1f}% over SMA20","Kort trendretning er positiv.")
    if s20_s50 is not None and s20_s50>0: add("SMA20_ABOVE_SMA50",10,f"SMA20 {s20_s50:+.1f}% over SMA50","Kort trend ligger over mellomlang trend.")
    if s50_s200 is not None and s50_s200>0: add("SMA50_ABOVE_SMA200",10,f"SMA50 {s50_s200:+.1f}% over SMA200","Lang trendstruktur er positiv.")
    golden=_b(src.get("golden_cross_active")) or bool(s50 is not None and s200 is not None and s50 > s200)
    if golden: add("GOLDEN_CROSS",9,"Golden cross aktiv","50-dagerssnitt over 200-dagerssnitt bekrefter positiv langsiktig struktur.")
    if breakout20: add("BREAKOUT_20D",14,f"20d-brudd {(_f(src.get('breakout_20d_pct')) or 0):+.1f}%","Nylig motstand er brutt; videre styrke krever at nivået holder.")
    if breakout60: add("BREAKOUT_60D",8,f"60d-brudd {(_f(src.get('breakout_60d_pct')) or 0):+.1f}%","Brudd over lengre motstand viser bredere trendstyrke.")
    if obv10 is not None and obv10>0.08: add("OBV_BUY_PRESSURE",10,f"OBV-kjøpspress 10d {obv10:+.2f}","Volum følger oppgangsdager og kan tyde på akkumulering.")
    if obv20 is not None and obv20>0.05: add("OBV_20D_CONFIRM",6,f"OBV positiv 20d {obv20:+.2f}","Kjøpspresset har vart gjennom en lengre periode.")
    if volume_comparable and vr is not None and vr>=1.2: add("VOLUME_CONFIRMATION",8,f"Volum {vr:.2f}x 20d-snitt","Høyere aktivitet gir mer troverdighet til brudd og akselerasjon.")
    if rsi is not None and 52<=rsi<=68: add("RSI_HEALTHY_MOMENTUM",8,f"RSI {rsi:.1f}","Positivt momentum uten ekstrem overkjøpt tilstand.")
    if src.get("rsi_cross_50_age_sessions") is not None and int(src.get("rsi_cross_50_age_sessions"))<=10: add("RSI_50_CROSS",6,f"RSI brøt 50 for {int(src.get('rsi_cross_50_age_sessions'))} økter siden","Nylig skifte fra nøytralt til positivt momentum.")
    if rsi is not None and rsi>=72: cautions.append(f"RSI {rsi:.1f} er overkjøpt; styrken er positiv, men risikoen for kort korreksjon er høyere.")
    if p_s20 is not None and p_s20>=8: cautions.append(f"Kursen ligger {p_s20:.1f}% over SMA20 og kan være kortsiktig strukket.")
    if volume_comparable and breakout20 and vr is not None and vr<0.8: cautions.append(f"20d-brudd uten tydelig volumstøtte ({vr:.2f}x) er mindre robust.")
    elif not volume_comparable and vr is not None: cautions.append("Dagens volumbar er ikke ferdig eller tidsjustert; volumet kan ikke brukes som negativ bekreftelse ennå.")
    score=max(0.0,min(100.0,score)); label="STERKT TIDLIG STYRKESIGNAL" if score>=70 else "TIDLIG STYRKESIGNAL" if score>=50 else "POSITIVT TRENDOPPSETT" if score>=30 else "INGEN TYDELIG TIDLIG SIGNAL"
    conf=[]; fail=[]
    if breakout20 or breakout60:
        conf.append("Bruddet holder over tidligere topp i 1–3 økter, helst med normalt eller stigende volum."); fail.append("Kursen faller raskt tilbake under bruddnivået; det kan være et falskt breakout.")
    if p_s20 is not None and p_s20>0:
        conf.append("Kursen holder seg over SMA20, og SMA20 fortsetter å peke opp."); fail.append("Kursen etablerer seg under SMA20 samtidig som SMA20 flater ut eller faller.")
    if obv10 is not None and obv10>0.08:
        conf.append("OBV/kjøpspress fortsetter positivt."); fail.append("OBV svekkes mens kursen stiger; negativ divergens reduserer kvaliteten.")
    if rsi is not None and rsi>=50:
        conf.append("RSI holder seg over 50 uten vedvarende ekstrem overkjøpt tilstand."); fail.append("RSI faller under 50 samtidig som kort momentum svekkes.")
    if not conf: conf.append("Se etter samtidig styrking i kort momentum, trendstruktur og volum før signalet oppgraderes.")
    top=[str(x.get("label") or "") for x in signals[:3]]
    summary=(f"{label}: "+"; ".join(top)+". Disse forholdene kan støtte videre oppgang dersom bekreftelsene holder.") if top else "Ingen tydelig kombinasjon av trend-, breakout- og volumsignaler er bekreftet ennå."
    if cautions: summary += " Viktigste motargument: "+cautions[0]
    return {"score":round(score,1),"label":label,"criteria_met":len(signals),"signals":signals,"cautions":cautions[:4],"continuation_summary":summary,"confirmation_checks":conf[:4],"failure_checks":fail[:4],"descriptive_only":True}


def build_opportunity_preview(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Cheap pre-evidence receipt used to prioritise research budget."""
    src=_source(candidate); fresh=_fresh_signal(src); early=_early_signal(src)
    return {"ticker":str(candidate.get("ticker") or ""),"fresh_signal":fresh,"early_signal":early,"descriptive_only":True}


def should_escalate_evidence(candidate: Mapping[str, Any]) -> bool:
    preview=build_opportunity_preview(candidate); fresh=preview["fresh_signal"]
    # Require meaningful freshness and adequate market data; no buy-rule change.
    dq=_f(candidate.get("data_quality") or _source(candidate).get("data_quality"))
    return bool(float(fresh.get("score") or 0)>=55 and (dq is None or dq>=60))


def _drivers(src: Mapping[str, Any], early: Mapping[str, Any], fresh: Mapping[str, Any]) -> list[str]:
    rows=[]
    for label,key in (("3d","return_3d"),("5d","return_5d"),("20d","return_20d"),("60d","return_60d")):
        val=_f(src.get(key));
        if val is not None: rows.append((abs(val),f"{label} {val:+.1f} %"))
    for item in list(fresh.get("signals") or [])[:2]+list(early.get("signals") or [])[:2]:
        if isinstance(item,Mapping): rows.append((float(item.get("points") or 0)+5,str(item.get("label") or "")))
    rows.sort(key=lambda x:x[0],reverse=True); out=[]
    for _,txt in rows:
        if txt and txt not in out: out.append(txt)
    return out[:5]


def _action_levels(src: Mapping[str, Any]) -> dict[str, Any]:
    price = _f(src.get("last_price"))
    breakout = _f(src.get("prior_20d_high"))
    sma20 = _f(src.get("sma20"))
    low20 = _f(src.get("low_20d"))
    preferred = breakout or sma20 or price
    pullback = breakout or sma20
    invalidation_choices = [value for value in (sma20, low20) if value is not None and (price is None or value < price)]
    invalidation = max(invalidation_choices) if invalidation_choices else (price * .95 if price else None)
    risk_per_share = (preferred - invalidation) if preferred and invalidation and preferred > invalidation else None
    target = preferred + 2.0 * risk_per_share if preferred and risk_per_share else None
    distance = ((price / breakout) - 1.0) * 100.0 if price and breakout else None
    return {
        "current_price": round(price, 4) if price is not None else None,
        "preferred_entry": round(preferred, 4) if preferred is not None else None,
        "pullback_retest": round(pullback, 4) if pullback is not None else None,
        "breakout_level": round(breakout, 4) if breakout is not None else None,
        "distance_to_breakout_pct": round(distance, 2) if distance is not None else None,
        "invalidation_level": round(invalidation, 4) if invalidation is not None else None,
        "first_target": round(target, 4) if target is not None else None,
        "reward_risk_ratio": 2.0 if target is not None and risk_per_share else None,
        "trade_authority": False,
        "note": "Observasjonsnivåer; kjøp krever alle ordinære data-, evidens-, risiko- og porteføljeporter.",
    }


def _data_freshness(src: Mapping[str, Any]) -> dict[str, Any]:
    observed_timestamp = next((src.get(key) for key in (
        "market_data_at", "price_updated_at", "data_timestamp", "quote_timestamp",
        "latest_trade_timestamp", "updated_at"
    ) if src.get(key)), "")
    fetched_at = src.get("fetch_completed_at") or src.get("enriched_at") or ""
    fetch_status = str(src.get("data_fetch_status") or "").upper()
    timestamp = fetched_at or observed_timestamp
    if not timestamp:
        return {"timestamp": "", "fetched_at": "", "observed_timestamp": "", "age_seconds": None, "status": "UKJENT"}
    try:
        parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        parsed = parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
        age = max(0, int((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()))
        status = "FERSK_INNHENTET" if fetched_at and age <= 20 * 60 else "FERSK" if age <= 20 * 60 else "FORSINKET" if age <= 24 * 3600 else "FORELDET"
        if fetch_status in {"ERROR", "NO_DATA", "QUARANTINED", "FAILED"}:
            status = "FEIL"
        return {"timestamp": str(timestamp), "fetched_at": str(fetched_at), "observed_timestamp": str(observed_timestamp), "age_seconds": age, "status": status, "fetch_status": fetch_status}
    except (TypeError, ValueError):
        return {"timestamp": str(timestamp), "fetched_at": str(fetched_at), "observed_timestamp": str(observed_timestamp), "age_seconds": None, "status": "UGYLDIG"}


def build_trend_receipt(candidate: Mapping[str, Any], history_item: Mapping[str, Any] | None = None) -> dict[str, Any]:
    src=_source(candidate); history_item=dict(history_item or {}); obs=list(history_item.get("observations") or [])
    try:
        from security_metadata import infer_security_listing
        listing = infer_security_listing(candidate.get("ticker"), {**dict(src), **dict(candidate)})
    except Exception:
        listing = {}
    previous_rank=obs[-1].get("rank") if obs else None; current_rank=candidate.get("rank"); rank_delta=None
    try: rank_delta=int(previous_rank)-int(current_rank) if previous_rank and current_rank else None
    except Exception: pass
    early=_early_signal(src); fresh=_fresh_signal(src); age,age_label=_trend_age(src)
    return {
        "version":VERSION,"ticker":str(candidate.get("ticker") or ""),"name":str(candidate.get("name") or src.get("name") or src.get("company_name") or ""),"country":str(candidate.get("country") or src.get("country") or listing.get("country") or "Ukjent"),"market":str(candidate.get("market") or src.get("market") or listing.get("market") or "Ukjent"),"sector":str(candidate.get("sector") or src.get("sector") or ""),
        "exchange":str(candidate.get("exchange") or src.get("exchange") or listing.get("exchange") or "Ukjent"),"exchange_name":str(candidate.get("exchange_name") or src.get("exchange_name") or src.get("market_segment") or listing.get("exchange") or "Ukjent"),"market_segment":str(candidate.get("market_segment") or src.get("market_segment") or src.get("exchange_name") or listing.get("exchange") or "Ukjent"),"exchange_mic":str(candidate.get("exchange_mic") or src.get("exchange_mic") or ""),"exchange_symbol":str(candidate.get("exchange_symbol") or src.get("exchange_symbol") or ""),"isin":str(candidate.get("isin") or src.get("isin") or ""),
        "first_discovered_at":history_item.get("first_seen") or candidate.get("created_at") or "","last_seen_at":history_item.get("last_seen") or "","times_seen":int(history_item.get("times_in_list") or len(obs) or 0),"rank_change":rank_delta,
        "trend_phase":_phase(src),"trend_age_sessions":age,"trend_age":age_label,"last_price":_f(src.get("last_price")),
        "return_1d_pct":_f(src.get("return_1d")),"return_3d_pct":_f(src.get("return_3d")),"return_5d_pct":_f(src.get("return_5d")),"return_10d_pct":_f(src.get("return_10d")),"return_15d_pct":_f(src.get("return_15d")),"return_20d_pct":_f(src.get("return_20d") or src.get("return_1m")),"return_60d_pct":_f(src.get("return_60d") or src.get("return_3m")),
        "momentum_acceleration_3v20":_f(src.get("momentum_acceleration_3v20")),"momentum_acceleration_5v20":_f(src.get("momentum_acceleration_5v20")),"volume_ratio_20":_f(src.get("volume_ratio_20")),"latest_volume":_f(src.get("latest_volume")),"average_volume_20":_f(src.get("average_volume_20")),
        "obv_pressure_5d":_f(src.get("obv_pressure_5d")),"obv_pressure_10d":_f(src.get("obv_pressure_10d")),"obv_pressure_20d":_f(src.get("obv_pressure_20d")),
        "rsi":_f(src.get("rsi")),"rsi_cross_50_age_sessions":src.get("rsi_cross_50_age_sessions"),"rsi_cross_60_age_sessions":src.get("rsi_cross_60_age_sessions"),"rsi_cross_70_age_sessions":src.get("rsi_cross_70_age_sessions"),"rsi_10d_breakout":_b(src.get("rsi_10d_breakout")),
        "sma20":_f(src.get("sma20")),"sma50":_f(src.get("sma50")),"sma200":_f(src.get("sma200")),"sma20_slope_5d_pct":_f(src.get("sma20_slope_5d_pct")),"golden_cross_spread_change_10d_pp":_f(src.get("golden_cross_spread_change_10d_pp")),
        "price_vs_sma20_pct":_f(src.get("price_vs_sma20_pct")),"sma20_vs_sma50_pct":_f(src.get("sma20_vs_sma50_pct")),"sma50_vs_sma200_pct":_f(src.get("sma50_vs_sma200_pct")),"golden_cross_active":_b(src.get("golden_cross_active")),"golden_cross_age_sessions":src.get("golden_cross_age_sessions"),
        "distance_from_20d_high_pct":_f(src.get("distance_from_20d_high_pct")),"distance_from_60d_high_pct":_f(src.get("distance_from_60d_high_pct")),"breakout_20d":_b(src.get("breakout_20d")),"breakout_60d":_b(src.get("breakout_60d")),"breakout_20d_age_sessions":src.get("breakout_20d_age_sessions"),"breakout_hold_sessions":src.get("breakout_hold_sessions"),"breakout_holding":_b(src.get("breakout_holding")),"breakout_20d_pct":_f(src.get("breakout_20d_pct")),"breakout_60d_pct":_f(src.get("breakout_60d_pct")),
        "prior_20d_high":_f(src.get("prior_20d_high")),"prior_60d_high":_f(src.get("prior_60d_high")),"low_20d":_f(src.get("low_20d")),"low_60d":_f(src.get("low_60d")),"support_levels":list(src.get("support_levels") or []),"resistance_levels":list(src.get("resistance_levels") or []),
        "compression_ratio_10v40":_f(src.get("compression_ratio_10v40")),"volatility_expansion_5v20":_f(src.get("volatility_expansion_5v20")),"close_location_in_day":_f(src.get("close_location_in_day")),"price_trend_60d":list(src.get("price_trend_60d") or [])[-60:],
        "early_signal":early,"fresh_signal":fresh,"action_levels":_action_levels(src),"data_freshness":_data_freshness(src),"data_fetch_status":str(src.get("data_fetch_status") or ""),"data_source":str(src.get("data_source") or ""),"refresh_proof":str(src.get("refresh_proof") or ""),"market_bar_interval":str(src.get("market_bar_interval") or "1d"),"volume_bar_complete":bool(src.get("volume_bar_complete")),"volume_time_adjusted":bool(src.get("volume_time_adjusted")),"volume_comparison_basis":str(src.get("volume_comparison_basis") or "dagsvolum mot ferdige 20d-dager; ikke tidsjustert"),"top_trend_drivers":_drivers(src,early,fresh),"descriptive_only":True,
    }


def annotate_run(run: dict[str, Any], history: Mapping[str, Any] | None = None) -> dict[str, Any]:
    history=dict(history or {})
    # RC16.31br: Fresh Trend peer ranking is based on every stage-1 screened
    # equity, not only the smaller deep-analysis set. Scored candidates replace
    # their lightweight counterparts so richer evidence is retained.
    pool = [row for row in (run.get("fresh_screening_candidates") or []) if isinstance(row, Mapping)]
    scored = [row for row in (run.get("candidates") or []) if isinstance(row, Mapping)]
    by_ticker = {str(row.get("ticker") or "").upper(): row for row in pool if str(row.get("ticker") or "").strip()}
    for row in scored:
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            by_ticker[ticker] = row
    candidates=list(by_ticker.values()); receipts=[]
    for row in candidates:
        ticker=str(row.get("ticker") or ""); receipt=build_trend_receipt(row,history.get(ticker) if isinstance(history.get(ticker),Mapping) else {}); row["trend_receipt"]=receipt; receipts.append(receipt)
    markets5={}; markets20={}; markets60={}; sectors20={}; sectors5={}
    for r in receipts:
        market=str(r.get("market") or r.get("country") or "Ukjent"); sec=(market,str(r.get("sector") or "Ukjent")); v20=_f(r.get("return_20d_pct")); v5=_f(r.get("return_5d_pct")); v60=_f(r.get("return_60d_pct"))
        if v20 is not None: markets20.setdefault(market,[]).append(v20); sectors20.setdefault(sec,[]).append(v20)
        if v5 is not None: markets5.setdefault(market,[]).append(v5); sectors5.setdefault(sec,[]).append(v5)
        if v60 is not None: markets60.setdefault(market,[]).append(v60)
    for r in receipts:
        market=str(r.get("market") or r.get("country") or "Ukjent"); sec=(market,str(r.get("sector") or "Ukjent")); p5=_pctile(_f(r.get("return_5d_pct")),markets5.get(market,[])); p20=_pctile(_f(r.get("return_20d_pct")),markets20.get(market,[]))
        r["market_rs_5d_percentile"]=p5; r["market_rs_20d_percentile"]=p20; r["market_rs_60d_percentile"]=_pctile(_f(r.get("return_60d_pct")),markets60.get(market,[])); r["sector_rs_5d_percentile"]=_pctile(_f(r.get("return_5d_pct")),sectors5.get(sec,[])); r["sector_rs_20d_percentile"]=_pctile(_f(r.get("return_20d_pct")),sectors20.get(sec,[]))
        r["market_rs_universe_count_5d"] = len(markets5.get(market, []))
        r["sector_rs_universe_count_5d"] = len(sectors5.get(sec, []))
        r["rs_reference_scope"] = "FULL_STAGE1_UNIVERSE"
        r["relative_strength_ignition"] = round(p5-p20,1) if p5 is not None and p20 is not None else None
        fs=r.get("fresh_signal") or {}
        if r.get("relative_strength_ignition") is not None and r["relative_strength_ignition"]>=20:
            fs.setdefault("signals",[]).append({"code":"RS_IGNITION","points":0,"label":f"RS-tenning +{r['relative_strength_ignition']:.1f}p","meaning":"5-dagers relativ styrke har rykket kraftig opp mot 20-dagersplasseringen; aksjen begynner å slå markedet raskere."})
    ranked=sorted([r for r in receipts if r.get("return_20d_pct") is not None],key=lambda r:float(r.get("return_20d_pct") or -1e9),reverse=True)
    early=sorted(receipts,key=lambda r:(float((r.get("early_signal") or {}).get("score") or 0),float(r.get("return_20d_pct") or -1e9)),reverse=True)
    fresh=sorted(receipts,key=lambda r:(float((r.get("fresh_signal") or {}).get("score") or 0),float(r.get("relative_strength_ignition") or -999),float(r.get("return_5d_pct") or -1e9)),reverse=True)
    fresh_only=[r for r in fresh if (r.get("fresh_signal") or {}).get("trend_age") in {"NY","TIDLIG"} and float((r.get("fresh_signal") or {}).get("score") or 0)>=35]
    # RC16.31cb: expose the four explainable monitoring axes in every report
    # receipt. The durable 15-minute engine adds history/status transitions.
    from fresh_trend_monitor import _components, _pullback_retest
    for r in fresh_only:
        r["fresh_monitor_components"] = _components(r)
        r["pullback_retest"] = _pullback_retest(r)
    established=[r for r in early if r.get("trend_age") in {"ETABLERT","MODEN"} and float((r.get("early_signal") or {}).get("score") or 0)>=30]
    prior = run.get("trend_discovery") if isinstance(run.get("trend_discovery"), Mapping) else {}
    prior_coverage = prior.get("coverage") if isinstance(prior.get("coverage"), Mapping) else {}
    actual_by_market = (run.get("scan_configuration") or {}).get("actual_by_market") or {}
    scan_actual = sum(int(value or 0) for value in actual_by_market.values()) if isinstance(actual_by_market, Mapping) else 0
    full_stage1 = max(len(pool), int(prior_coverage.get("full_stage1_universe") or 0), scan_actual)
    for receipt in receipts:
        receipt["rs_full_stage1_universe"] = full_stage1
        receipt["rs_reference_at"] = run.get("completed_at") or run.get("generated_at") or run.get("started_at") or ""
    run["trend_discovery"]={"version":VERSION,"mode":"NORWAY_PRODUCTION_STABILIZATION" if run.get("markets")==["Norge"] else "MULTI_MARKET","top10":ranked[:10],"near_candidates":ranked[10:15],"early_signal_watchlist":early[:12],"fresh_trend_watchlist":fresh_only[:12],"established_trend_watchlist":established[:12],"coverage":{"candidates":len(candidates),"full_stage1_universe":full_stage1,"deep_scored":len(scored),"with_20d_return":len(ranked),"with_60d_chart":sum(1 for r in receipts if len(r.get("price_trend_60d") or [])>=20),"with_early_signal":sum(1 for r in early if float((r.get("early_signal") or {}).get("score") or 0)>=30),"with_fresh_signal":len(fresh_only)},"missed_winner_audit":{"state":"COLLECTING_BASELINE","note":"Fresh Trend måles separat fra etablerte vinnere slik at eldre 30–60d-trender ikke kan dominere nye trendstarter."},"production_scoring_changed":False,"evidence_priority_changed":True,"explanation":"Fresh Trend og etablert trend er separate køer. Fresh Trend favoriserer fersk akselerasjon, breakout, RSI/OBV-tenning og kompresjon→ekspansjon. Sterke ferske signaler kan få tidligere evidenskontroll, men kan aldri alene utløse kjøp."}
    return run
