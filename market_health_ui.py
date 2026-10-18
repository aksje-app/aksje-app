"""Read-only market-health gauges for the main page.

Only measured, timestamped inputs may be shown as numbers. No broker actions,
strategy changes, network calls or synthetic scores.
"""
from __future__ import annotations
from datetime import datetime, timezone
from html import escape
from math import isfinite

INDICATORS = {
    "cape": ("Shiller CAPE", "S&P 500-pris i forhold til gjennomsnittlig inflasjonsjustert inntjening over ti år.", "Høye verdier antyder dyrt marked, ikke tidspunkt for børsfall.", "Shiller/Robert Shiller data", "Forholdstall"),
    "equity_yield": ("Total equity yield", "Samlet aksjonæravkastning/kapitalutbetaling relativt til markedsverdi. Metode og definisjon må dokumenteres.", "Må ikke forveksles med forventet fremtidig totalavkastning.", "Dokumentert metodisk serie", "%"),
    "vix": ("VIX fryktindeks", "Opsjonsmarkedets implisitte forventede S&P 500-svingninger over rundt 30 dager.", "Høy VIX betyr forventet volatilitet, ikke sikkert fall.", "Cboe VIX", "indeks"),
    "us10y": ("USA 10-årsrente", "Effektiv rente på amerikanske statsobligasjoner med omtrent ti års løpetid.", "Rask renteøkning kan presse aksjeverdsettelser.", "US Treasury/FRED", "%"),
    "us30y": ("USA 30-årsrente", "Lang statsobligasjonsrente som fanger opp langsiktige rente- og inflasjonsforventninger.", "Tolk sammen med realrente og inflasjon.", "US Treasury/FRED", "%"),
    "curve": ("10 minus 2 år", "Differansen mellom 10- og 2-årsrenten i prosentpoeng.", "Invertering har historisk vært et resesjonssignal, men tidsforsinkelsen varierer.", "US Treasury/FRED", "prosentpoeng"),
    "credit": ("High Yield kredittpåslag", "Ekstra rente over tryggere obligasjoner for selskaper med lavere kredittvurdering.", "Stigende påslag tyder ofte på økt finansieringsstress.", "ICE BofA/FRED", "prosentpoeng"),
    "breadth": ("Markedsbredde", "Andelen aksjer som deltar i oppgangen, eksempelvis over 200 dagers glidende snitt.", "Svak bredde kan varsle sårbar oppgang.", "Valgt og dokumentert børsunivers", "%"),
    "brent": ("Brent olje", "Referansepris for olje som påvirker inflasjon, energiselskaper og norsk økonomi.", "Stigning kan være både vekstsignal og inflasjonspress.", "Dokumentert Brent-spot/terminserie", "USD/fat"),
    "ttf": ("Europeisk naturgass", "Europeisk TTF-gasspris.", "Store utslag påvirker europeiske energikostnader.", "Dokumentert TTF-serie", "EUR/MWh"),
    "gold": ("Gull", "Gullpris i amerikanske dollar.", "Avhenger også av realrente, dollar og likviditet; ikke entydig fryktmål.", "Dokumentert XAU/USD-serie", "USD/oz"),
    "dxy": ("Dollarindeks DXY", "Vektet mål på dollarens verdi mot en kurv av seks valutaer, der euro veier mest.", "Stigende DXY kan stramme globale finansieringsvilkår, men effekten varierer mellom sektorer og land.", "ICE US Dollar Index", "indeks"),
    "eurusd": ("EUR/USD", "Antall amerikanske dollar per euro. Fallende EUR/USD betyr sterkere dollar mot euro.", "Kursen kompletterer DXY, men skal ikke telles som et helt uavhengig risikosignal.", "Dokumentert valutakilde", "USD/EUR"),
    "trend": ("S&P 500 mot 200-dagers snitt", "Avstand i prosent mellom S&P 500 og 200-dagers glidende gjennomsnitt.", "Negativ avstand kan indikere svak trend, ikke nødvendigvis krise.", "S&P 500 kursserie", "%"),
}
GROUPS = {"verdsettelse": ("Verdsettelsesrisiko", ("cape", "equity_yield")),
          "stress": ("Markedsstress", ("vix", "credit", "curve", "breadth")),
          "macro": ("Makro og trender", ("us10y", "us30y", "brent", "ttf", "gold", "dxy", "eurusd", "trend"))}


UPDATE_INTERVALS = {
    "cape": "Månedlig", "equity_yield": "Månedlig", "vix": "15 minutter",
    "us10y": "15 minutter (hvis intradagkilde; ellers daglig)",
    "us30y": "15 minutter (hvis intradagkilde; ellers daglig)",
    "curve": "15 minutter (hvis begge rentekurser er ferske; ellers daglig)",
    "credit": "Daglig", "breadth": "30 minutter", "brent": "15 minutter",
    "ttf": "15 minutter (ved tilgang til intradagkilde)", "gold": "15 minutter",
    "trend": "15 minutter i børstid", "dxy": "15 minutter",
    "eurusd": "15 minutter",
}
# Targets only. Snapshot freshness must be checked against the actual publication
# cadence and exchange holidays; a scheduler run does not prove fresh quotes.
COMPOSITE_INTERVAL = "Hvert 15. minutt når gyldige inngangsdata foreligger"

def _valid(row):
    if not isinstance(row, dict) or not row.get("observed_at") or not row.get("source"):
        return False
    try:
        value = float(row["value"])
        observed = datetime.fromisoformat(str(row["observed_at"]).replace("Z", "+00:00"))
        return isfinite(value) and observed.tzinfo is not None and observed <= datetime.now(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return False


def render_market_health(st, snapshot=None):
    """Optional main-page block. Inputs remain read-only and unknown is explicit."""
    if snapshot is None:
        try:
            from durable_runtime import read_json
            from storage_architecture import runtime_data_path
            snapshot = read_json("market_health/latest.json", runtime_data_path("market_health", "latest.json"), {})
        except Exception:
            snapshot = {}
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    rows = snapshot.get("indicators") or {}
    rows = rows if isinstance(rows, dict) else {}
    from market_health_history import normalize, summarize
    from market_health_alerts import critical_alert
    from market_health_gauges import display_gauge
    from market_health_cockpit import market_cards
    policies = snapshot.get("alert_policies") if isinstance(snapshot.get("alert_policies"), dict) else {}
    st.subheader("🌡️ Markedstemperatur – global børshelse")
    # Distinguish source observation time from scheduler polling time.
    from zoneinfo import ZoneInfo
    def _clock_label(raw):
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed > datetime.now(timezone.utc):
                return "Ukjent"
            return parsed.astimezone(ZoneInfo("America/Fortaleza")).strftime("%d.%m kl. %H:%M")
        except (TypeError, ValueError, OverflowError):
            return "Ukjent"
    checked_at = (snapshot.get("collection_status") or {}).get("at") if isinstance(snapshot.get("collection_status"), dict) else None
    observed = [str(row.get("observed_at")) for row in rows.values() if isinstance(row, dict) and row.get("observed_at")]
    last_quote = max(observed) if observed else None
    st.caption(f"🕒 Siste datakontroll: {_clock_label(checked_at)} · Nyeste kursobservasjon: {_clock_label(last_quote)} (Brasil, UTC−3)")
    st.caption("Hver enkelt måler viser dessuten sitt eget kurstidspunkt og datakilde.")
    # Render static accessible dial artwork, not a green health indicator without evidence.
    def dial(label, value=None):
        verified = isinstance(value, (int, float)) and isfinite(value) and 0 <= value <= 100
        pct = float(value) if verified else 0
        angle = -90 + pct * 1.8
        color = "#2aaa75" if pct < 30 else "#e7b53b" if pct < 55 else "#e78636" if pct < 75 else "#d75050"
        needle = (f'<line x1="90" y1="105" x2="90" y2="46" stroke="{color}" stroke-width="4" '
                  f'transform="rotate({angle:.1f} 90 105)" stroke-linecap="round"/>') if verified else ""
        title = f"{pct:.0f}/100" if verified else "Ukjent"
        return (f'<div role="img" aria-label="{escape(label)}: {title}" style="text-align:center">'
                '<svg viewBox="0 0 180 118" style="width:100%;max-width:215px">'
                '<path d="M 20 105 A 70 70 0 0 1 160 105" fill="none" stroke="#2aaa75" stroke-width="14"/>'
                '<path d="M 41 56 A 70 70 0 0 1 100 36" fill="none" stroke="#e7b53b" stroke-width="14"/>'
                '<path d="M 100 36 A 70 70 0 0 1 147 64" fill="none" stroke="#e78636" stroke-width="14"/>'
                '<path d="M 147 64 A 70 70 0 0 1 160 105" fill="none" stroke="#d75050" stroke-width="14"/>'
                + needle + '<circle cx="90" cy="105" r="5" fill="currentColor"/></svg>'
                f'<div><strong>{escape(label)}</strong></div><div>{title}</div></div>')

    st.caption("Kun observerte, tidsstemplete markedsdata. Foreløpig informativ/Shadow; ingen påvirkning på kjøp eller salg.")
    overall = snapshot.get("composite") or {}
    score = overall.get("risk_score") if isinstance(overall, dict) else None
    if isinstance(score, (int, float)) and isfinite(score) and 0 <= score <= 100 and overall.get("validated") is True:
        st.progress(int(score) / 100, text=f"Samlet risikometer: {score:.0f}/100")
    else:
        st.info("Samlet temperatur: IKKE BEREGNET – datadekning og kalibrering må være validert.")
    if hasattr(st, "markdown") and isinstance(score, (int, float)) and isfinite(score) and overall.get("validated") is True:
        st.markdown(dial("Samlet markedsrisiko", score), unsafe_allow_html=True)
    else:
        st.caption("Samlet instrumentmåler vises når risikomodellen er validert; inntil da vises de enkelte markedsmålingene.")
    with st.expander("ℹ️ Hvordan beregnes samlet børshelse og fargene?"):
        st.write("Samlet børshelse skal kombinere verdsettelse, markedsstress, renter, trend og markedsbredde. Gruppene må normaliseres mot egen historikk og kontrolleres for overlapp. Rødt betyr forhøyet risiko – ikke et automatisk salgssignal.")
        st.write("Ingen samlet score gis ved manglende kritiske data, udokumenterte terskler eller utilstrekkelig historikk. Grønn drift er ikke dokumentasjon på god investeringsavkastning.")
        st.write("Planlagt oppdateringsintervall:", COMPOSITE_INTERVAL)
        st.write("DXY er primært dollarmål. EUR/USD er forklarende krysskurs, ikke et dobbelt vektet uavhengig signal.")
    st.markdown("""<style>\n@keyframes mh-critical-pulse {0%,100% {opacity:1;box-shadow:0 0 0 0 rgba(220,50,50,.28)}50% {opacity:.7;box-shadow:0 0 0 7px rgba(220,50,50,0)}}\n.mh-critical {border:2px solid #cf3434;border-radius:12px;padding:8px;background:rgba(210,45,45,.12);animation:mh-critical-pulse 2.4s ease-in-out infinite}\n@media (prefers-reduced-motion: reduce) {.mh-critical {animation:none}}\n</style>""", unsafe_allow_html=True)
    animate = st.checkbox("Pulsér kritiske målere", value=True, key="market_health_critical_animation") if hasattr(st, "checkbox") else False
    available_keys = [key for _, (_, group_keys) in GROUPS.items() for key in group_keys if normalize(key, rows.get(key))]
    st.caption(f"{len(available_keys)} av {len(INDICATORS)} indikatorer har målte verdier. Fargeskala vises bare når skalaen er dokumentert.")
    # Render one HTML grid rather than Streamlit columns: columns were collapsing
    # and overlapping on iOS, even when the Python regression suite was green.
    cards = []
    for key in ("vix", "trend", "us10y", "us30y", "dxy", "brent", "gold", "eurusd",
                "cape", "equity_yield", "credit", "curve", "breadth", "ttf"):
        name, meaning, caution, default_source, unit = INDICATORS[key]
        datum = rows.get(key)
        checked = normalize(key, datum)
        good = checked is not None and checked["status"] == "CURRENT"
        from zoneinfo import ZoneInfo
        timestamp = ""
        if checked and datum:
            try:
                timestamp = datetime.fromisoformat(str(datum["observed_at"]).replace("Z", "+00:00")).astimezone(ZoneInfo("America/Fortaleza")).strftime("%d.%m kl. %H:%M")
            except (ValueError, TypeError):
                timestamp = ""
        cards.append({"key": key, "name": name, "valid": good,
                      "value": checked["value"] if good else None,
                      "label": f"{float(datum['value']):,.2f} {unit}" if good else ("Utdatert" if checked else "Mangler data"),
                      "observed": timestamp,
                      "status": "Utdatert" if checked else "Mangler data"})
        alert = critical_alert(key, datum, checked, policies.get(key))
        if alert:
            style = "mh-critical" if animate else ""
            st.markdown(f'<div class="{style}" role="status">🔴 KRITISK: {escape(name)} · {alert["value"]:g}</div>', unsafe_allow_html=True)
    st.markdown(market_cards(cards), unsafe_allow_html=True)
    with st.expander("ℹ️ Forklaringer, datakilder og historikk for alle målere"):
        for card in cards:
            key = card["key"]
            name, meaning, caution, default_source, unit = INDICATORS[key]
            datum = rows.get(key)
            checked = normalize(key, datum)
            with st.expander(f"ℹ️ Forklaring: {name}"):
                st.write(meaning)
                st.write("Tolkning:", caution)
                st.write("Planlagt oppdateringsintervall:", UPDATE_INTERVALS[key])
                st.write("Datakilde:", str(datum.get("source") if isinstance(datum, dict) else default_source))
                st.write("Sist observert:", str(datum.get("observed_at") if isinstance(datum, dict) else "Ukjent"))
                if checked and checked["status"] == "CURRENT":
                    st.write("Skalaforklaring:", display_gauge(key, checked["value"]).get("method", "Ingen godkjent skala"))
                history = datum.get("observations") if isinstance(datum, dict) else None
                details = summarize(key, history) if isinstance(history, list) else None
                st.write("Historikk 24 timer / 7 / 30 dager:", details["history"] if details else "Ikke tilgjengelig")
                st.write("Inngår først i samlet risikoskår etter validert metode.")
