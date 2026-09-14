from __future__ import annotations
from datetime import datetime,timedelta,timezone
from io import BytesIO
import learning_observation_engine as engine

def _candidate(ticker,market,score,outcome,sector="Industri"):
    return {"ticker":ticker,"market":market,"sector":sector,"investment_score":score,"risk_score":35,
            "data_quality":95,"confidence_score":78,"strategy_match":"QUALITY","autonomy_outcome_code":outcome,
            "valid_for_decision":True,"evidence_valid_for_decision":True,"raw":{"current_price":100.0}}

def _memory(monkeypatch,initial=None):
    store={engine.OBSERVATIONS_KEY:list(initial or []),engine.STATE_KEY:{},engine.WEEKLY_KEY:[]}
    monkeypatch.setattr(engine,"read_json",lambda key,path,default:store.get(key,default))
    monkeypatch.setattr(engine,"write_json",lambda key,path,value:store.__setitem__(key,value)); return store

def test_az_version_lineage():
    from app_version import APP_VERSION,PREVIOUS_APP_VERSION
    assert APP_VERSION=="v19.22.0-rc16.31bd" and PREVIOUS_APP_VERSION == "v19.22.0-rc16.31bc"

def test_registration_freezes_groups_and_core_markets(monkeypatch):
    store=_memory(monkeypatch)
    candidates=[_candidate("STRICT.OL","Norge",80,"KJØPSKANDIDAT"),_candidate("MOD.ST","Sverige",75,"MODERAT_KJØPSANBEFALING"),
                _candidate("NEAR","USA",69,"OVERVÅKES_AUTOMATISK"),_candidate("CTRL","USA",55,"AVVIST"),
                _candidate("FOREIGN.CO","Danmark",90,"KJØPSKANDIDAT")]
    run={"run_id":"R1","created_at":"2026-08-28T12:00:00+00:00","candidates":candidates,"report_summary":{"production_buy_threshold":73}}
    result=engine.register_report_observations(run); rows=store[engine.OBSERVATIONS_KEY]
    assert result["created"]==4 and {r["group"] for r in rows}==set(engine.GROUP_TARGETS)
    assert {r["market"] for r in rows}<=set(engine.CORE_MARKETS)
    assert all(len(r["decision_snapshot"]["snapshot_sha256"])==64 and not r["trade_authorized"] and not r["production_applied"] for r in rows)

def test_registration_idempotent_and_capped(monkeypatch):
    store=_memory(monkeypatch); candidates=[_candidate(f"T{i}","USA",80 if i<40 else 55,"MODERAT_KJØPSANBEFALING" if i<40 else "AVVIST") for i in range(150)]
    run={"run_id":"R2","created_at":"2026-08-28T12:00:00+00:00","candidates":candidates,"report_summary":{"production_buy_threshold":73}}
    assert engine.register_report_observations(run)["created"]<=120
    assert engine.register_report_observations(run)["created"]==0
    assert len(store[engine.OBSERVATIONS_KEY])<=120

def test_evaluation_reaches_60_after_simulated_exit(monkeypatch):
    entry=datetime(2026,1,2,tzinfo=timezone.utc)
    row={"observation_id":"O1","ticker":"AAA","market":"USA","sector":"Tech","strategy":"QUALITY","group":"MODERATE",
         "benchmark_ticker":"^GSPC","entry_at":entry.isoformat(),"entry_market_date":"2026-01-02","entry_price":100.0,
         "status":"ACTIVE","horizon_measurements":{},"daily_marks":[],"simulated_exit_at":"2026-01-10T12:00:00+00:00"}
    store=_memory(monkeypatch,[row]); days=[]; day=entry.date()
    while len(days)<65:
        if day.weekday()<5: days.append(day.isoformat())
        day+=timedelta(days=1)
    stock=[{"date":"2025-12-31","close":99.0}]+[{"date":d,"close":100+i} for i,d in enumerate(days)]
    bench=[{"date":"2025-12-31","close":200.0}]+[{"date":d,"close":200+i} for i,d in enumerate(days)]
    result=engine.evaluate_observations(lambda symbols,start:{"AAA":stock,"^GSPC":bench},now=datetime(2026,4,15,tzinfo=timezone.utc))
    observed=store[engine.OBSERVATIONS_KEY][0]
    assert result["matured"]==1 and set(observed["horizon_measurements"])=={"1","5","20","60"}
    assert observed["status"]=="MATURED" and observed["simulated_exit_at"].startswith("2026-01-10")

def test_weekly_analysis_is_shadow_only():
    rows=[]
    for i in range(12):
        rows.append({"status":"ACTIVE","ticker":f"X{i}","group":"MODERATE" if i<6 else "NEAR_THRESHOLD","market":"USA","sector":"Tech","strategy":"QUALITY","benchmark_ticker":"^GSPC","source_health":{"status":"OK"},"horizon_measurements":{"20":{"return_pct":4+i,"benchmark_return_pct":2,"excess_return_pct":2+i}}})
    a=engine.build_weekly_analysis(rows); twenty=next(r for r in a["horizons"] if r["horizon_days"]==20)
    assert twenty["excess_return"]["maturity"]=="FORELØPIG" and not a["production_parameters_changed"]
    assert all(not p["production_applied"] and p["approval_required"] for p in a["shadow_proposals"])

def test_weekly_pdfs_are_readable():
    from pypdf import PdfReader
    analysis=engine.build_weekly_analysis([])
    for technical in (False,True):
        payload=engine.build_weekly_pdf(analysis,technical=technical); reader=PdfReader(BytesIO(payload))
        text="\n".join(page.extract_text() or "" for page in reader.pages)
        assert payload.startswith(b"%PDF-") and "Ingen produksjonsregel" in text

def test_scheduler_nonblocking_before_scanner():
    source=open("scheduled_runner.py",encoding="utf-8").read(); learning=source.index("run_learning_maintenance"); scanner=source.index("run_paper_scanner")
    assert learning<scanner and "except Exception" in source[source.rfind("try:",0,learning):source.find("# Paper scanning",learning)]

def test_durable_public_json_integrity(monkeypatch):
    import public_report_store as store
    memory={}; monkeypatch.setattr(store,"read_json",lambda k,p,d:memory.get(k,d)); monkeypatch.setattr(store,"write_json",lambda k,p,v:memory.__setitem__(k,v))
    token=store.publish_durable_file(b'{"status":"ok"}',filename="weekly.json",mime="application/json",report_id="LWR-1")
    assert store.load_public_file(token)["data"]==b'{"status":"ok"}'
    memory[f"public_files/{token}.json"]["data_base64"]="AAAA"; assert store.load_public_file(token)=={}

def test_weekly_survives_pushover_failure(monkeypatch):
    import notifier,public_report_store
    store=_memory(monkeypatch)
    monkeypatch.setattr(public_report_store,"publish_durable_pdf",lambda record,data,token_field="public_report_token",**kwargs:record.__setitem__(token_field,"P"*43) or "P"*43)
    monkeypatch.setattr(public_report_store,"publish_durable_file",lambda *args,**kwargs:"J"*43)
    monkeypatch.setattr(notifier,"send_pushover_alert",lambda *args,**kwargs:(_ for _ in ()).throw(RuntimeError("offline")))
    result=engine.generate_weekly_report(now=datetime(2026,8,30,12,tzinfo=timezone.utc))
    assert result["status"]=="COMPLETED" and not store[engine.WEEKLY_KEY][0]["notification"]["sent"]

def test_failed_daily_retries(monkeypatch):
    store=_memory(monkeypatch); store[engine.STATE_KEY]={"daily":{"status":"FAILED","completed_at":"2026-08-28T05:00:00+00:00"}}
    assert not engine._daily_due(datetime(2026,8,28,5,30,tzinfo=timezone.utc))
    assert engine._daily_due(datetime(2026,8,28,6,1,tzinfo=timezone.utc))

def test_mobile_and_diagnostics_connected():
    assert "public_file_token" in open("public_report_ui.py",encoding="utf-8").read()
    assert "controlled_observation_engine" in open("learning_acceptance.py",encoding="utf-8").read()
