"""Read-only interim research findings from persisted per-symbol evidence."""
from collections import Counter
from hashlib import sha256
from statistics import median
from services.storage_service import get_storage_service

ENGINES = (("AUTONOMY", "Autonomi"), ("SUPER_PORTFOLIO", "Superporteføljen"))
PREFIX = "strategy_history/"

def collect(storage, engine):
    state = storage.read_json(PREFIX + "optimization_progress.json", {}) or {}
    tickers = state.get("completed_tickers") or []
    counts = Counter()
    holdout = []
    validation = []
    complete = 0
    missing = 0
    for ticker in tickers:
        digest = sha256(str(ticker).encode()).hexdigest()
        record = storage.read_json(PREFIX + "optimized/" + engine + "/" + digest + ".json", {}) or {}
        if record.get("status") != "COMPLETE_RESEARCH":
            missing += 1
            continue
        complete += 1
        for finalist in record.get("finalists") or []:
            key = (finalist.get("stop_pct"), finalist.get("hold_sessions"))
            if key[0] is not None and key[1] is not None:
                counts[key] += 1
            v = finalist.get("validation") or {}
            h = finalist.get("holdout") or {}
            if isinstance(v.get("total_pct"), (int, float)):
                validation.append(float(v["total_pct"]))
            if isinstance(h.get("total_pct"), (int, float)) and h.get("trades", 0):
                holdout.append(float(h["total_pct"]))
    return {"total": int(state.get("total") or 0), "processed": int(state.get("processed") or 0),
            "complete": complete, "missing_records": missing, "counts": counts,
            "holdout": holdout, "validation": validation, "updated_at": state.get("updated_at")}

def render(st):
    st.subheader("📊 Hva viser aksjetestene så langt?")
    st.info("Dette er tidlige testresultater. De viser hva som har skjedd i gamle kursdata – ikke hva du kan forvente å tjene.")
    try:
        storage = get_storage_service()
        for engine, label in ENGINES:
            data = collect(storage, engine)
            st.markdown("### " + label)
            st.metric("Aksjer undersøkt", "{} / {}".format(data["processed"], data["total"]))
            st.metric("Aksjer med fullstendig test", data["complete"])
            if data["missing_records"]:
                st.warning("{} aksjer har ikke fullstendig testresultat. Det kan skyldes for kort kurshistorikk eller manglende data.".format(data["missing_records"]))
            if not data["counts"]:
                st.write("Ingen verifiserbare finalister i lagrede resultater ennå.")
                continue
            st.markdown("**Hvilke innstillinger går oftest igjen?**")

            rows = [{"Grense for tap": f"{stop} %", "Maks. eiertid": f"{hold} børsdager", "Ganger valgt": n}
                    for (stop, hold), n in data["counts"].most_common(8)]
            st.dataframe(rows, hide_index=True, width="stretch")
            st.write("Dette er innstillinger som ofte ble valgt i testene. Det betyr ikke at de er lønnsomme.")
            if data["validation"]:
                st.metric("Typisk resultat i kontrollperioden", "{:.2f} %".format(median(data["validation"])))
            if data["holdout"]:
                st.metric("Typisk resultat i siste testperiode", "{:.2f} %".format(median(data["holdout"])))
                st.write("Siste testperiode var holdt utenfor da innstillingene ble valgt. Tallene gjelder enkeltstående simuleringer, ikke din portefølje.")
            else:
                st.write("Ingen tilgjengelige holdout-resultater med handler.")
            st.divider()
        with st.expander("Hva betyr dette – forklart enkelt?"):
            st.write("Vi har undersøkt få aksjer. Resultatene kan endre seg mye når flere kommer med.")
            st.write("Kontrollperioden brukes til å vurdere valgte innstillinger. Siste testperiode brukes som en ekstra kontroll mot nye, historiske data.")
            st.write("En høy prosent er ikke forventet fortjeneste: perioder, antall handler og risiko kan være forskjellige.")
            st.write("Ingen av disse funnene endrer programmets kjøp eller salg automatisk.")
    except Exception as exc:
        st.error("Kunne ikke lese forskningsresultatene: " + type(exc).__name__)
