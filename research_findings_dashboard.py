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
    st.subheader("📊 Foreløpige forskningsfunn")
    st.info("Foreløpige observasjoner, ikke godkjente handelsregler eller prognose for porteføljeavkastning.")
    try:
        storage = get_storage_service()
        for engine, label in ENGINES:
            data = collect(storage, engine)
            st.markdown("### " + label)
            st.write("Behandlet: {} / {} aksjer".format(data["processed"], data["total"]))
            st.write("Med lagrede forskningsresultater: {}".format(data["complete"]))
            if data["missing_records"]:
                st.warning("{} ferdigmeldte aksjer mangler komplette resultatfiler.".format(data["missing_records"]))
            if not data["counts"]:
                st.write("Ingen verifiserbare finalister i lagrede resultater ennå.")
                continue
            st.markdown("**Hyppigste finalistkombinasjoner**")
            st.write("Antall er forekomster blant finalister, ikke antall lønnsomme aksjer.")
            for (stop, hold), n in data["counts"].most_common(8):
                st.write("Stop-loss {} % · eiertid {} handelsdager: {} finalister".format(stop, hold, n))
            if data["validation"]:
                st.metric("Median valideringsresultat per finalist", "{:.2f} %".format(median(data["validation"])))
            if data["holdout"]:
                st.metric("Median holdout-resultat per finalist", "{:.2f} %".format(median(data["holdout"])))
                st.caption("Holdout er kun en beskrivende måling av forhåndsvalgte finalister, ikke et estimat for fremtidig porteføljeavkastning.")
            else:
                st.write("Ingen tilgjengelige holdout-resultater med handler.")
            st.divider()
        with st.expander("Slik skal tallene tolkes"):
            st.write("Utvalget er fortsatt lite og kan være skjevt. De mest hyppige kombinasjonene er ikke nødvendigvis best.")
            st.write("Validering og holdout gjelder simulert inn-/utgang per aksje, ikke komplett porteføljebacktest.")
            st.write("Ingen resultatbasert automatisk endring av aktive handelsregler foretas.")
    except Exception as exc:
        st.error("Kunne ikke lese forskningsresultatene: " + type(exc).__name__)
