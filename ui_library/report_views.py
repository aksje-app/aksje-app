from __future__ import annotations
from datetime import datetime
from typing import Any,Mapping,Sequence
from .models import TimelineStepView

def build_report_timeline(reports: Sequence[Mapping[str,Any]],schedule: Mapping[str,Any],now: datetime) -> list[TimelineStepView]:
    result=[]
    for idx,row in enumerate(reports):
        raw=str(row.get("status") or "WAITING").upper()
        status="SENT" if raw in {"COMPLETED","SENT","SUCCESS"} else raw if raw in {"WAITING","RUNNING","FAILED","DELAYED"} else "WAITING"
        notification=row.get("notification") or {}; pdf=bool(row.get("pdf_path") or row.get("pdf_url"))
        details={"generation":"COMPLETED" if status=="SENT" else status,"storage":str(row.get("storage_status") or ("SAVED" if pdf else "WAITING")),"pdf":"SAVED" if pdf else "WAITING","pushover":"SENT" if notification.get("sent") else ("FAILED" if notification.get("error") else "WAITING")}
        result.append(TimelineStepView(str(row.get("report_id") or idx),str(row.get("report_type") or row.get("title") or "Rapport"),str(row.get("scheduled_at") or ""),status,"danger" if status=="FAILED" else "reports",details))
    return result
