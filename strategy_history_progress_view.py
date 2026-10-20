"""Live, read-only historical strategy test progress for both portfolio pages."""
from __future__ import annotations

def snapshot(storage):
    record = storage.read_json("strategy_history/progress.json", {}) or {}
    total = max(0, int(record.get("total") or 0))
    done = max(0, int(record.get("completed") or 0))
    rejected = max(0, int(record.get("rejected") or 0))
    opt = storage.read_json("strategy_history/optimization_progress.json", {}) or {}
    staged = storage.read_json("strategy_history/staged_sector_progress.json", {}) or {}
    return {
        "optimization": opt,
        "staged": staged,
        "status": str(record.get("status") or "IKKE_STARTET"),
        "total": total, "done": done, "rejected": rejected,
        "pct": 100.0 * done / total if total else None,
        "processed_pct": 100.0 * min(total, done + rejected) / total if total else None,
        "updated_at": record.get("updated_at"),
        "reason": str(record.get("reason") or ""),
        "batch_completed": record.get("batch_completed"),
        "batch_total": record.get("batch_total"),
        "coarse_tested": max(0,int(record.get("coarse_tested") or record.get("completed") or 0)),
        "coarse_grid": max(0,int(record.get("coarse_grid") or 16)),
        "optimized": max(0,int(record.get("optimized") or 0)),
        "finalists": max(0,int(record.get("validated_finalists") or 0)),
    }

def render(st):
    from services.storage_service import get_storage_service
    st.subheader("📈 Strategitesting – historisk fremdrift")
    try:
        progress = snapshot(get_storage_service())
    except Exception as exc:
        st.error(f"Fremdriftsdata utilgjengelige: {type(exc).__name__}")
        return
    status = progress["status"]
    from app_time_display import local_display, age_hours, browser_timezone
    st.caption(f"Jobbstatus: {status} · Sist oppdatert ({browser_timezone(st)}): {local_display(st,progress['updated_at'])}")
    if progress["reason"]:
        st.warning(f"Årsak: {progress['reason']}")
    cols = st.columns(1)
    cols[0].metric("Aksjer analysert", f"{progress['done']:,} / {progress['total']:,}".replace(",", " "))
    cols[1].metric("Avvist / utilstrekkelige data", progress["rejected"])
    cols[2].metric("Datainnsamling", f"{progress['pct']:.1f} %" if progress["pct"] is not None else "Ikke målt")
    if progress["pct"] is not None:
        st.progress(min(1.0, progress["pct"] / 100))
        st.caption(f"Ferdig behandlet inkl. avviste: {progress['processed_pct']:.1f} %. Avviste regnes ikke som analyserte.")
    st.divider()
    st.subheader("Strategitester og bearbeiding")
    phases = st.columns(1)
    phases[0].metric("Aksjer med grovtester", progress["coarse_tested"])
    phases[1].metric("Stop-loss × eiertid per aksje", progress["coarse_grid"])
    phases[2].metric("Registrerte grovtester", progress["coarse_tested"] * progress["coarse_grid"])
    st.caption("Grovtestene er ubetingede kurssimuleringer, ikke porteføljespesifikke kjøpssignaler.")
    st.caption("Grovtesting er fullført; separat historisk parameteroptimalisering vises nedenfor. "
               "Finalister er forskningskandidater, ikke godkjente handelsregler.")
    staged=progress["staged"]
    st.divider()
    st.subheader("Trinnvise kjøp og sektorgrenser")
    st.caption(f"Status: {staged.get('status','IKKE_STARTET')} · "
               f"Historiske signalbilder kvalifisert: {staged.get('eligible',0)} / {staged.get('total',0)}. "
               "Ingen komplette porteføljebacktester er kjørt i denne modulen.")
    opt=progress["optimization"]
    st.divider()
    st.subheader("Historisk parameterforskning")
    completed=int(opt.get("processed") or 0)
    total=int(opt.get("total") or 0)
    st.caption(f"Status: {opt.get('status','IKKE_STARTET')} · Behandlet {completed} / {total} aksjer")
    if total:
        st.progress(min(1.,completed/total))
    summaries=opt.get("engine_totals") or {}
    for engine,label in (("AUTONOMY","Autonomi"),("SUPER_PORTFOLIO","Superporteføljen")):
        stats=summaries.get(engine) or {}
        with st.container(border=True):
            st.markdown(f"**{label}**")
            st.write(f"Aksjer fullført: {stats.get('complete_symbols',0)}")
            st.write(f"Gyldige kombinasjoner: {stats.get('valid_trials',0)}")
            st.write(f"Forskningsfinalister: {stats.get('finalists',0)}")
            st.write(f"Utilstrekkelig historikk: {stats.get('insufficient_symbols',0)}")
    if completed and not summaries:
        st.info("Eldre optimaliseringsresultater er ikke aggregert i statusen ennå. "
                "Nye kjøringer vil fylle opp separate porteføljetall.")
    st.divider()
    eta=opt.get("eta_hours")
    if isinstance(eta,(int,float)) and eta>=0 and opt.get("status")=="RUNNING":
        st.metric("Estimert resttid",f"{eta:.1f} timer")
        st.caption("Anslag basert på registrert gjennomstrømning; kan endre seg ved datamangler og pauser.")
    else:
        st.caption("Estimert resttid: Ikke tilstrekkelig grunnlag for pålitelig anslag.")
    hours=age_hours(opt.get("updated_at"))
    if hours is not None and hours>8 and opt.get("status")=="RUNNING":
        st.warning(f"Historisk optimalisering har ingen registrert fremdrift på {hours:.1f} timer.")
    st.caption(f"Siste optimaliseringskontroll: {local_display(st,opt.get('updated_at'))}.")
    st.caption("Resultatene er ubetingede inn-/utgangstester med kostnadsfradrag, "
               "kronologisk trening/validering/holdout og sperreperioder. "
               "Dette er ikke full porteføljereplay eller godkjent regelendring.")
    st.caption("Historiske OHLC og resultater lagres under strategy_history/prices/ og strategy_history/results/. "
               "Dette er utforskende simulering, ikke godkjente strategiresultater.")
