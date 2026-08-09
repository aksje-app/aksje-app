"""Fast, bounded report delivery preflight without market analysis."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path

STATE_KEY = "scheduler/report_system_check.json"
STATE_PATH = runtime_data_path("scheduler", "report_system_check.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_report_system_check() -> dict[str, Any]:
    value = read_json(STATE_KEY, STATE_PATH, {})
    return dict(value) if isinstance(value, dict) else {}


def _row(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": str(detail)[:1000]}


def run_report_system_check(*, send_notification: bool = True) -> dict[str, Any]:
    """Verify the delivery chain without scanning markets or changing portfolios."""
    started = _now()
    rows: list[dict[str, str]] = []

    try:
        probe = {"probe_id": f"RSC-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}", "written_at": started}
        write_json(STATE_KEY, STATE_PATH, {"state": "RUNNING", **probe})
        echoed = read_json(STATE_KEY, STATE_PATH, {})
        ok = isinstance(echoed, dict) and echoed.get("probe_id") == probe["probe_id"]
        rows.append(_row("Varig database", "PASS" if ok else "FAIL", "Skrive-/lesekontroll bestått" if ok else "Lagret verdi kunne ikke leses tilbake"))
    except Exception as exc:
        rows.append(_row("Varig database", "FAIL", f"{type(exc).__name__}: {exc}"))

    try:
        from execution_coordination import report_execution_lock
        with report_execution_lock() as acquired:
            rows.append(_row(
                "Rapportlås", "PASS" if acquired else "WARN",
                "Låsen kunne reserveres og ble frigitt" if acquired else "En rapportkjøring bruker låsen nå",
            ))
    except Exception as exc:
        rows.append(_row("Rapportlås", "FAIL", f"{type(exc).__name__}: {exc}"))

    try:
        from reportlab.pdfgen import canvas
        buffer = io.BytesIO()
        document = canvas.Canvas(buffer)
        document.drawString(72, 800, "AI Aksje Analyzer – PDF systemkontroll")
        document.save()
        pdf = buffer.getvalue()
        valid = pdf.startswith(b"%PDF-") and b"%%EOF" in pdf[-1024:] and len(pdf) > 500
        rows.append(_row("PDF-motor", "PASS" if valid else "FAIL", f"Genererte {len(pdf)} byte gyldig test-PDF" if valid else "PDF-signatur eller sluttsignatur mangler"))
    except Exception as exc:
        rows.append(_row("PDF-motor", "FAIL", f"{type(exc).__name__}: {exc}"))

    try:
        from report_delivery import public_report_url
        url = public_report_url({"public_report_token": "SYSTEM_CHECK_TOKEN"})
        configured = bool(url and "public_report_token=SYSTEM_CHECK_TOKEN" in url)
        rows.append(_row(
            "Offentlig rapportlenke", "PASS" if configured else "FAIL",
            "Tokenbasert offentlig adresse kan bygges" if configured else "RENDER_EXTERNAL_URL eller REPORT_PUBLIC_BASE_URL mangler/er ugyldig",
        ))
    except Exception as exc:
        rows.append(_row("Offentlig rapportlenke", "FAIL", f"{type(exc).__name__}: {exc}"))

    if send_notification:
        try:
            from notifier import send_pushover_alert
            ok, detail = send_pushover_alert(
                "Rask systemkontroll av database, rapportlås, PDF og offentlig lenke er kjørt. "
                "Dette er ikke en markedsrapport og teller ikke i testserien 1/4–4/4.",
                title="🩺 SYSTEMKONTROLL · AI Aksje Analyzer",
            )
            rows.append(_row("Pushover", "PASS" if ok else "FAIL", "Testvarsel sendt" if ok else str(detail or "Ukjent varslingsfeil")))
        except Exception as exc:
            rows.append(_row("Pushover", "FAIL", f"{type(exc).__name__}: {exc}"))
    else:
        rows.append(_row("Pushover", "SKIPPED", "Varsling var eksplisitt slått av for denne kontrollen"))

    failed = [row for row in rows if row["status"] == "FAIL"]
    warned = [row for row in rows if row["status"] == "WARN"]
    state = "FAIL" if failed else ("DEGRADED" if warned else "PASS")
    result = {
        "state": state,
        "started_at": started,
        "completed_at": _now(),
        "checks": rows,
        "summary": {"passed": sum(row["status"] == "PASS" for row in rows), "failed": len(failed), "warnings": len(warned)},
        "safe_scope": "NO_MARKET_SCAN_NO_PORTFOLIO_ACTION_NO_LEARNING_ACTION",
    }
    try:
        write_json(STATE_KEY, STATE_PATH, result)
    except Exception as exc:
        result["state"] = "FAIL"
        result["persistence_error"] = f"{type(exc).__name__}: {exc}"
    return result
