"""Read-only interim research findings from persisted per-symbol evidence."""
from collections import Counter
from hashlib import sha256
from statistics import median
from services.storage_service import get_storage_service
from portfolio_history_optimizer import METHOD_VERSION

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
    invalid_method = 0
    for ticker in tickers:
        digest = sha256(str(ticker).encode()).hexdigest()
        record = storage.read_json(PREFIX + "optimized/" + engine + "/" + digest + ".json", {}) or {}
        if record.get("status") == "COMPLETE_RESEARCH" and record.get("method_version") != METHOD_VERSION:
            invalid_method += 1
            continue
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
            "complete": complete, "missing_records": missing, "incomplete_history": incomplete_history, "invalid_method": invalid_method,
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
            if data["invalid_method"]:
                st.warning(f"{data['invalid_method']} eldre resultater er utelatt: overlappende kapitalbruk og inngangsdagens stopp må beregnes på nytt.")
            if data["missing_records"]:
                st.warning("{} aksjer har ikke fullstendig testresultat. Det kan skyldes for kort kurshistorikk eller manglende data.".format(data["missing_records"]))
            if data["incomplete_history"]:
                st.info("{} aksjer kunne ikke testes fullt fordi kurshistorikken var for kort.".format(data["incomplete_history"]))
            if not data["counts"]:
                lines(st, "Ingen verifiserbare finalister i lagrede resultater ennå.")
                continue
            st.subheader("Vanligste kombinasjoner")

            rows = [{"Grense for tap": f"{stop} %", "Maks. eiertid": f"{hold} børsdager", "Ganger valgt": n}
                    for (stop, hold), n in data["counts"].most_common(8)]
            st.dataframe(rows, hide_index=True, width="stretch")
            st.info("Disse innstillingene ble valgt ofte. Det betyr ikke at de tjente penger.")
            if data["validation"]:
                st.metric("Typisk resultat i kontrollperioden", "{:.2f} %".format(median(data["validation"])))
            if data["holdout"]:
                st.metric("Typisk resultat i siste testperiode", "{:.2f} %".format(median(data["holdout"])))
                st.info("Siste testperiode ble ikke brukt til å velge innstillingene. Resultatet er ikke avkastningen til porteføljen.")
            else:
                lines(st, "Ingen tilgjengelige holdout-resultater med handler.")
            st.subheader("Er resultatene stabile?")
            pairs = data["paired"]
            if pairs:
                before = median(p[0] for p in pairs)
                after = median(p[1] for p in pairs)
                lines(st,
                    f"Tester med kjøp og salg i begge perioder: {len(pairs)}.",
                    f"Resultat i tidligere periode: {before:.2f} %.",
                    f"Resultat i siste periode: {after:.2f} %.",
                    f"Typisk antall handler: {median(p[2] for p in pairs):g} og {median(p[3] for p in pairs):g}.")
                if abs(after - before) >= 20:
                    st.warning("Resultatene spriker mye. Vi vet ennå ikke om reglene er pålitelige.")
            else:
                st.warning("For få sammenlignbare handler til å vurdere pålitelighet.")
            if data["zero_holdout_trades"]:
                st.info(f"{data['zero_holdout_trades']} tester hadde ikke handler i siste periode.")
            st.divider()
        with st.expander("Hva betyr dette – forklart enkelt?"):
            lines(st,
                "Bare en liten del av aksjene er testet. Resultatene kan endre seg.",
                "Tallene gjelder simulerte kjøp og salg i gamle kursdata.",
                "En høy prosent betyr ikke at du kan forvente samme fortjeneste.",
                "Ingen av disse funnene endrer kjøps- eller salgsreglene.")
    except Exception as exc:
        st.error("Kunne ikke lese forskningsresultatene: " + type(exc).__name__)
