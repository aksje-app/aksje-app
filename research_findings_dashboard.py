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
    incomplete_history = 0
    paired = []
    zero_holdout_trades = 0
    for ticker in tickers:
        digest = sha256(str(ticker).encode()).hexdigest()
        record = storage.read_json(PREFIX + "optimized/" + engine + "/" + digest + ".json", {}) or {}
        if record.get("status") != "COMPLETE_RESEARCH":
            if record.get("status") in ("INSUFFICIENT_HISTORY", "INSUFFICIENT_PURGED_PERIODS"):
                incomplete_history += 1
            else:
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
                if isinstance(v.get("total_pct"), (int, float)) and v.get("trades", 0):
                    paired.append((float(v["total_pct"]), float(h["total_pct"]), int(v["trades"]), int(h["trades"])))
            else:
                zero_holdout_trades += 1
    return {"total": int(state.get("total") or 0), "processed": int(state.get("processed") or 0),
            "complete": complete, "missing_records": missing, "incomplete_history": incomplete_history,
            "paired": paired, "zero_holdout_trades": zero_holdout_trades, "counts": counts,
            "holdout": holdout, "validation": validation, "updated_at": state.get("updated_at")}

def render(st):
    from research_readable_layout import lines
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
            if data["incomplete_history"]:
                lines(st, "{} aksjer kunne ikke testes fullt fordi kurshistorikken var for kort.".format(data["incomplete_history"]))
            if not data["counts"]:
                lines(st, "Ingen verifiserbare finalister i lagrede resultater ennå.")
                continue
            st.markdown("**Hvilke innstillinger går oftest igjen?**")

            rows = [{"Grense for tap": f"{stop} %", "Maks. eiertid": f"{hold} børsdager", "Ganger valgt": n}
                    for (stop, hold), n in data["counts"].most_common(8)]
            st.dataframe(rows, hide_index=True, width="stretch")
            lines(st, "Dette er innstillinger som ofte ble valgt i testene. Det betyr ikke at de er lønnsomme.")
            if data["validation"]:
                st.metric("Typisk resultat i kontrollperioden", "{:.2f} %".format(median(data["validation"])))
            if data["holdout"]:
                st.metric("Typisk resultat i siste testperiode", "{:.2f} %".format(median(data["holdout"])))
                lines(st, "Siste testperiode var holdt utenfor da innstillingene ble valgt. Tallene gjelder enkeltstående simuleringer, ikke din portefølje.")
            else:
                lines(st, "Ingen tilgjengelige holdout-resultater med handler.")
            st.markdown("**Kontroll av hvor pålitelige prosentene er**")
            pairs = data["paired"]
            lines(st, "Sammenlignbare tester med handler i begge perioder: {}".format(len(pairs)))
            if pairs:
                before = median(p[0] for p in pairs)
                after = median(p[1] for p in pairs)
                lines(st, "Typisk kontrollresultat for de samme testene: {:.2f} %".format(before))
                lines(st, "Typisk resultat i siste periode for de samme testene: {:.2f} %".format(after))
                lines(st, "Typisk antall handler: kontroll {} · siste periode {}".format(
                    median(p[2] for p in pairs), median(p[3] for p in pairs)))
                if abs(after - before) >= 20:
                    st.warning("Stor forskjell mellom periodene. Vi kan ennå ikke si at innstillingene gir stabile resultater.")
            else:
                st.warning("Ingen tester med handler i begge periodene. Resultatene kan ikke sammenlignes pålitelig.")
            if data["zero_holdout_trades"]:
                lines(st, "{} finalisttester mangler handler eller målbart resultat i siste periode.".format(data["zero_holdout_trades"]))
            st.divider()
        with st.expander("Hva betyr dette – forklart enkelt?"):
            lines(st, "Vi har undersøkt få aksjer. Resultatene kan endre seg mye når flere kommer med.")
            lines(st, "Kontrollperioden brukes til å vurdere valgte innstillinger. Siste testperiode brukes som en ekstra kontroll mot nye, historiske data.")
            lines(st, "En høy prosent er ikke forventet fortjeneste: perioder, antall handler og risiko kan være forskjellige.")
            lines(st, "Ingen av disse funnene endrer programmets kjøp eller salg automatisk.")
    except Exception as exc:
        st.error("Kunne ikke lese forskningsresultatene: " + type(exc).__name__)
