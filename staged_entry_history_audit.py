"""Availability audit before historical portfolio staging replay.

Never replace missing point-in-time purchase signals or sector classifications with
today's snapshots. This stage is a safe gate, not a claim of completed backtests.
"""
from __future__ import annotations
from datetime import datetime,timezone
from services.storage_service import get_storage_service
from staged_entry_sector_research import can_use_historical_snapshot

KEY="strategy_history/staged_sector_progress.json"

def run_once():
    storage=get_storage_service()
    frames=storage.read_json("controlled_learning/experiment_frames.json",[]) or []
    counters={"total":len(frames),"eligible":0,"missing_as_of":0}
    for frame in frames:
        observations=(frame.get("pipeline") or {}).get("candidates") or []
        snapshot={"as_of":frame.get("at"),"candidates":observations}
        if can_use_historical_snapshot(snapshot):counters["eligible"]+=1
        else:counters["missing_as_of"]+=1
    state={"status":"READY_FOR_REPLAY" if counters["eligible"]>=15 else "WAITING_FOR_POINT_IN_TIME_SIGNALS",
           **counters,"trials_completed":0,"production_changed":False,
           "note":"200-variant portfolio replay not started. Historical purchase signals and sector/industry as-of classifications required.",
           "updated_at":datetime.now(timezone.utc).isoformat()}
    storage.write_json(KEY,state)
    return state
