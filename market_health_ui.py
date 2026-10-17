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
    "trend": ("S&P 500 mot 200-dagers snitt", "Avstand i prosent mellom S&P 500 og 200-dagers glidende gjennomsnitt.", "Negativ avstand kan indikere svak trend, ikke nødvendigvis krise.", "S&P 500 kursserie", "%"),
}
GROUPS = {"verdsettelse": ("Verdsettelsesrisiko", ("cape", "equity_yield")),
          "stress": ("Markedsstress", ("vix", "credit", "curve", "breadth")),
          "macro": ("Makro og trender", ("us10y", "us30y", "brent", "ttf", "gold", "trend"))}


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
    st.subheader("🌡️ Markedstemperatur – global børshelse")
    st.caption("Kun observerte, tidsstemplete markedsdata. Foreløpig informativ/Shadow; ingen påvirkning på kjøp eller salg.")
    overall = snapshot.get("composite") or {}
    score = overall.get("risk_score") if isinstance(overall, dict) else None
    if isinstance(score, (int, float)) and isfinite(score) and 0 <= score <= 100 and overall.get("validated") is True:
        st.progress(int(score) / 100, text=f"Samlet risikometer: {score:.0f}/100")
    else:
        st.info("Samlet temperatur: IKKE BEREGNET – datadekning og kalibrering må være validert.")
    with st.expander("ℹ️ Hvordan beregnes samlet børshelse og fargene?"):
        st.write("Samlet børshelse skal kombinere verdsettelse, markedsstress, renter, trend og markedsbredde. Gruppene må normaliseres mot egen historikk og kontrolleres for overlapp. Rødt betyr forhøyet risiko – ikke et automatisk salgssignal.")
        st.write("Ingen samlet score gis ved manglende kritiske data, udokumenterte terskler eller utilstrekkelig historikk. Grønn drift er ikke dokumentasjon på god investeringsavkastning.")
    for group_id, (group_label, keys) in GROUPS.items():
        st.markdown(f"**{group_label}**")
        columns = st.columns(3)
        for n, key in enumerate(keys):
            name, meaning, caution, default_source, unit = INDICATORS[key]
            datum = rows.get(key)
            good = _valid(datum)
            with columns[n % 3]:
                if good:
                    st.metric(name, f"{float(datum['value']):,.2f} {unit}")
                    st.caption(f"{datum['observed_at']} · {datum['source']}")
                else:
                    st.metric(name, "Mangler data")
                with st.expander(f"ℹ️ Forklaring: {name}"):
                    st.write(meaning)
                    st.write("Tolkning:", caution)
                    st.write("Datakilde:", str(datum.get("source") if good else default_source))
                    st.write("Sist observert:", str(datum.get("observed_at") if good else "Ukjent"))
                    st.write("Historikk 1/7/30 dager: Ikke tilgjengelig" if not good or not datum.get("history") else datum["history"])
                    st.write("Inngår i sammensatt måler først når datadekning, metode og terskler er validert.")
