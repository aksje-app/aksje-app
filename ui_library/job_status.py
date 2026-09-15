from __future__ import annotations

from typing import Any, Mapping
from .models import JobStatusView

def _percent(value: Any) -> int:
    try: return max(0,min(100,int(value or 0)))
    except (TypeError,ValueError): return 0

def manual_job_view(status: Mapping[str,Any]) -> JobStatusView:
    state=str(status.get("state") or "IDLE").upper()
    heartbeat=str(status.get("worker_heartbeat_at") or status.get("heartbeat_at") or "")
    progress=str(status.get("last_progress_at") or status.get("updated_at") or "")
    return JobStatusView(job_id=str(status.get("execution_id") or ""),state=state,label=str(status.get("job_name") or status.get("message") or "Bakgrunnsjobb"),phase=str(status.get("active_stage") or status.get("phase") or ""),percent=_percent(status.get("percent")),completed_units=status.get("completed"),total_units=status.get("total"),started_at=str(status.get("started_at") or ""),last_activity_at=max(heartbeat,progress),message=str(status.get("message") or ""),error=str(status.get("error") or ""),can_stop=state in {"QUEUED","RUNNING","STOP_REQUESTED"},diagnostic_available=bool(status.get("execution_id")))

def super_portfolio_job_view(status: Mapping[str,Any]) -> JobStatusView:
    state=str(status.get("state") or "IDLE").upper()
    active=state in {"QUEUED","RUNNING","PAUSE_REQUESTED","PAUSED","STOP_REQUESTED"}
    heartbeat=str(status.get("worker_heartbeat_at") or status.get("heartbeat_at") or "")
    progress=str(status.get("last_progress_at") or status.get("updated_at") or "")
    return JobStatusView(job_id=str(status.get("job_id") or ""),state=state,label=str(status.get("job_name") or "Super Portfolio"),phase=str(status.get("phase") or status.get("market") or ""),percent=_percent(status.get("percent")),completed_units=status.get("completed"),total_units=status.get("total"),started_at=str(status.get("started_at") or ""),last_activity_at=max(heartbeat,progress),message=str(status.get("message") or ""),error=str(status.get("error") or status.get("failure_type") or ""),can_pause=state in {"QUEUED","RUNNING"},can_resume=state in {"PAUSE_REQUESTED","PAUSED"},can_stop=active and state!="STOP_REQUESTED",diagnostic_available=bool(status.get("job_id")))
