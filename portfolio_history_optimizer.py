"""Read-only, checkpointed stop-loss/holding-period parameter research.

200 grid candidates per equity and per portfolio. It is not portfolio replay,
cannot alter trading rules, and uses isolated chronological splits.
"""
from __future__ import annotations
from datetime import datetime,timezone
from hashlib import sha256
from statistics import mean
from services.storage_service import get_storage_service
from strategy_history_worker import simulate

PREFIX="strategy_history/"
STOPS=tuple(2.0+0.5*i for i in range(20))
HOLDS=(5,7,10,14,20,30,40,60,90,120)
COST_PCT=0.3
GAP=120

def _score(returns, penalty):
    net=[r-COST_PCT for r in returns]
    if not net:return None
    peak=equity=1.0;drawdown=0.0
    for value in net:
        equity*=max(.00001,1+value/100)
        peak=max(peak,equity)
        drawdown=max(drawdown,100*(peak-equity)/peak)
    return {"trades":len(net),"avg_pct":round(mean(net),5),
            "total_pct":round(100*(equity-1),5),
            "max_drawdown_pct":round(drawdown,5),
            "objective":round(100*(equity-1)-penalty*drawdown,5)}

def optimize(bars, portfolio):
    if portfolio not in ("AUTONOMY","SUPER_PORTFOLIO"):
        raise ValueError("Unsupported portfolio")
    dates=[str(b.get("date") or "") for b in bars]
    if len(bars)<1000 or any(not d for d in dates) or dates!=sorted(set(dates)):
        return {"status":"INSUFFICIENT_HISTORY"}
    n=len(bars);end_train=int(n*.60);end_valid=int(n*.80)
    validation=(end_train+GAP,end_valid)
    holdout=(end_valid+GAP,n)
    if validation[1]-validation[0]<140 or holdout[1]-holdout[0]<140:
        return {"status":"INSUFFICIENT_PURGED_PERIODS"}
    penalty=1.5 if portfolio=="AUTONOMY" else 1.0
    candidates=[]
    for stop in STOPS:
        for hold in HOLDS:
            tr=_score(simulate(bars[:end_train],stop,hold),penalty)
            va=_score(simulate(bars[validation[0]:validation[1]],stop,hold),penalty)
            if tr and va and tr["trades"]>=3 and va["trades"]>=1:
                candidates.append({"stop_pct":stop,"hold_sessions":hold,"train":tr,"validation":va})
    # Lock finalists before evaluating untouched holdout.
    finalists=sorted(candidates,key=lambda t:(-t["train"]["objective"],-t["validation"]["objective"]))[:20]
    finalists=sorted(finalists,key=lambda t:-t["validation"]["objective"])[:5]
    for f in finalists:
        f["holdout"]=_score(simulate(bars[holdout[0]:],f["stop_pct"],f["hold_sessions"]),penalty)
    return {"status":"COMPLETE_RESEARCH","portfolio":portfolio,"budget":200,
            "evaluated":len(candidates),"finalists":finalists,
            "train_end":dates[end_train-1],"validation_start":dates[validation[0]],
            "holdout_start":dates[holdout[0]],"purge_sessions":GAP,
            "cost_round_trip_pct":COST_PCT,
            "scope":"UNCONDITIONAL_ENTRY_EXIT_GRID_NOT_PORTFOLIO_REPLAY",
            "production_changed":False,"promotion_eligible":False}

def run_once(limit=1):
    storage=get_storage_service()
    progress=storage.read_json(PREFIX+"progress.json",{}) or {}
    tickers=sorted(progress.get("completed_tickers") or [])
    key=PREFIX+"optimization_progress.json"
    state=storage.read_json(key,{}) or {}
    done=set(state.get("completed_tickers") or [])
    failed=set(state.get("rejected_tickers") or [])
    queue=[x for x in tickers if x not in done and x not in failed]
    for ticker in queue[:max(1,min(3,int(limit)))]:
        digest=sha256(ticker.encode()).hexdigest()
        record=storage.read_json(PREFIX+"prices/"+digest+".json",{}) or {}
        try:
            results={}
            for portfolio in ("AUTONOMY","SUPER_PORTFOLIO"):
                result=optimize(record.get("bars") or [],portfolio)
                storage.write_json(PREFIX+"optimized/"+portfolio+"/"+digest+".json",
                                   {"ticker":ticker,**result})
                results[portfolio]=result["status"]
            done.add(ticker)
        except Exception:
            failed.add(ticker)
    new={"status":"COMPLETE_RESEARCH_PASS" if len(done)+len(failed)>=len(tickers) else "RUNNING",
         "total":len(tickers),"processed":len(done),"failed":len(failed),
         "candidate_budget_per_symbol_per_portfolio":200,
         "completed_tickers":sorted(done),"rejected_tickers":sorted(failed),
         "updated_at":datetime.now(timezone.utc).isoformat(),
         "scope":"HISTORICAL_EXIT_RESEARCH_ONLY","production_changed":False}
    storage.write_json(key,new)
    return {k:v for k,v in new.items() if not k.endswith("_tickers")}
