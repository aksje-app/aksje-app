"""Checkpointed 200-candidate historical stop/hold search, one result per engine.
Exploratory OHLC backtest only: NOT a replay of full portfolio selection or trades.
"""
from __future__ import annotations
from datetime import datetime,timezone
from hashlib import sha256
from statistics import mean
from services.storage_service import get_storage_service
from strategy_history_worker import simulate

PREFIX="strategy_history/"
ENGINES=("AUTONOMY","SUPER_PORTFOLIO")
STOPS=(2,3,4,5,6,7,8,10,12,15)
HOLDS=(3,5,7,10,14,20,30,45,60,90,120,180,240,300,360,420,480,540,600,720)
TOTAL=len(STOPS)*len(HOLDS)
MIN_BARS=750
COST_ROUND_TRIP_PCT=0.30

def evaluate(rows, stop, hold):
    # Chronological disjoint regions, purged by the full maximum 720-day horizon.
    # Holdout is evaluated once only after 200/200 training candidates are locked.
    n=len(rows)
    train_end=int(n*.60)
    val_start=train_end+720
    val_end=int(n*.80)
    hold_start=val_end+720
    def score(segment):
        returns=simulate(segment,stop,hold)
        net=[x-COST_ROUND_TRIP_PCT for x in returns]
        return {"trades":len(net),"net_mean_pct":round(mean(net),5) if net else None,
                "win_pct":round(100*sum(x>0 for x in net)/len(net),3) if net else None}
    return {"train":score(rows[:train_end]),
            "validation":score(rows[val_start:val_end]),
            "holdout":score(rows[hold_start:])}

def run_once(per_run=10):
    storage=get_storage_service()
    history=storage.read_json(PREFIX+"progress.json",{}) or {}
    tickers=history.get("completed_tickers") or []
    outcomes={}
    for engine in ENGINES:
        path=PREFIX+"optimization/"+engine.lower()+".json"
        state=storage.read_json(path,{}) or {}
        cursor=min(TOTAL,int(state.get("cursor") or 0))
        if cursor==TOTAL:
            outcomes[engine]={"status":"COMPLETE","trials":cursor}
            continue
        # Deterministic frozen batch: only instruments in first completed history pass.
        # Limit memory and CPU; consume once per engine and store aggregate scores.
        sampled=sorted(tickers)[::max(1,len(tickers)//40)][:40]
        loaded=[]
        for ticker in sampled:
            key=sha256(ticker.encode()).hexdigest()
            record=storage.read_json(PREFIX+"prices/"+key+".json",{}) or {}
            bars=record.get("bars") or []
            if len(bars)>=MIN_BARS:
                loaded.append((ticker,bars))
        if len(loaded)<10:
            state.update({"status":"WAITING_FOR_LONG_HISTORY","eligible":len(loaded),"minimum":10})
            storage.write_json(path,state)
            outcomes[engine]=state
            continue
        trials=list(state.get("trials") or [])
        for idx in range(cursor,min(TOTAL,cursor+max(1,min(int(per_run),20)))):
            stop=STOPS[idx//len(HOLDS)]
            hold=HOLDS[idx%len(HOLDS)]
            metrics=[evaluate(bars,stop,hold) for _,bars in loaded]
            train=[m["train"]["net_mean_pct"] for m in metrics if m["train"]["trades"]>=5]
            valid=[m["validation"]["net_mean_pct"] for m in metrics if m["validation"]["trades"]>=5]
            trials.append({"trial":idx+1,"stop_pct":stop,"hold_days":hold,
                           "train_mean_pct":round(mean(train),5) if train else None,
                           "validation_mean_pct":round(mean(valid),5) if valid else None,
                           "train_symbols":len(train),"validation_symbols":len(valid)})
        cursor=len(trials)
        state={"status":"COMPLETE" if cursor==TOTAL else "RUNNING",
               "engine":engine,"cursor":cursor,"budget":TOTAL,"trials":trials,
               "sampled_symbols":len(loaded),"cost_round_trip_pct":COST_ROUND_TRIP_PCT,
               "strategy_validated":False,"production_changed":False,
               "scope":"UNCONDITIONAL_STOP_HOLD_NOT_PORTFOLIO_REPLAY",
               "updated_at":datetime.now(timezone.utc).isoformat()}
        if cursor==TOTAL:
            valid=[t for t in trials if t["validation_mean_pct"] is not None and t["validation_symbols"]>=5]
            finalists=sorted(valid,key=lambda t:t["validation_mean_pct"],reverse=True)[:5]
            lookup={(t["stop_pct"],t["hold_days"]):t for t in finalists}
            for (stop,hold),entry in lookup.items():
                test=[evaluate(bars,stop,hold)["holdout"]["net_mean_pct"]
                      for _,bars in loaded if evaluate(bars,stop,hold)["holdout"]["trades"]>=5]
                entry["holdout_mean_pct"]=round(mean([v for v in test if v is not None]),5) if test else None
                entry["holdout_symbols"]=len(test)
            state["finalists"]=finalists
        storage.write_json(path,state)
        outcomes[engine]={"status":state["status"],"trials":cursor,"eligible":len(loaded)}
    return outcomes
