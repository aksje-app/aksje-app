from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import autonomous_portfolio as ap
import market_intelligence as mi


def test_autonomous_portfolio_has_paper_style_rows_and_ledger():
    portfolio = {"positions": {"AIZ": {"ticker": "AIZ", "sector": "Financial Services", "quantity": 10, "average_price": 100, "last_price": 110}}}
    rows = ap.autonomous_position_rows(portfolio)
    assert rows[0]["Markedsverdi"] == 1100
    assert rows[0]["Avkastning kr"] == 100
    assert round(rows[0]["Avkastning %"], 2) == 10.0
    ledger = ap.autonomous_decision_ledger_rows([{"timestamp": "2026-07-26T07:00:00+00:00", "run_id": "R1", "ticker": "EQNR.OL", "action": "SKIP", "reason": "Score under terskel", "score": 71.4}])
    assert ledger[0]["Handlet"] == "Nei"
    assert "Score under terskel" in ledger[0]["Stoppårsak / begrunnelse"]


def test_trade_display_hides_ids_from_primary_contract():
    rows = ap.autonomous_trade_display_rows([{"trade_id": "T-1", "timestamp": "2026-07-26T07:00:00+00:00", "ticker": "AIZ", "action": "BUY", "quantity": 2, "price": 100, "reason": "Godkjent"}])
    assert rows[0]["Tid"].startswith("26.07.2026")
    assert rows[0]["Kjøp/salg"] == "BUY"
    assert rows[0]["Teknisk ID"] == "T-1"


def test_manual_run_cannot_inherit_scheduled_slot(monkeypatch):
    source = Path(mi.__file__).read_text(encoding="utf-8")
    assert 'if trigger != "SCHEDULED":\n        scheduled_for = None' in source


def test_notification_receipt_has_lifecycle_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(mi, "REPORT_NOTIFICATION_RECEIPTS_PATH", tmp_path / "receipts.json")
    monkeypatch.setattr(mi, "_durable_key", lambda path: None)
    monkeypatch.setattr(mi, "report_public_url", lambda run: "")
    monkeypatch.setattr(mi, "resolve_report_identity", lambda run: {"type": "MORGENRAPPORT", "label": "Morgenrapport"})
    job = mi.JobProfile(job_id="J1", name="Test", notify_pushover=False)
    ok, detail = mi._notification(job, {"run_id": "R1", "created_at": datetime.now(timezone.utc).isoformat(), "trigger": "MANUAL", "changes": {}})
    assert not ok
    data = mi._read(mi.REPORT_NOTIFICATION_RECEIPTS_PATH, {})
    row = data["R1"]
    for key in ("created_at", "attempted_at", "sent_at", "expires_at", "status", "triggered_by", "report_id", "run_id"):
        assert key in row
    assert row["triggered_by"] == "MANUAL"


def test_stale_report_notification_expires(tmp_path, monkeypatch):
    monkeypatch.setattr(mi, "REPORT_NOTIFICATION_RECEIPTS_PATH", tmp_path / "receipts.json")
    monkeypatch.setattr(mi, "_durable_key", lambda path: None)
    monkeypatch.setattr(mi, "report_public_url", lambda run: "")
    monkeypatch.setattr(mi, "resolve_report_identity", lambda run: {"type": "MORGENRAPPORT", "label": "Morgenrapport"})
    job = mi.JobProfile(job_id="J1", name="Test", notify_pushover=True, notification_mode="ALWAYS")
    old = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
    ok, detail = mi._notification(job, {"run_id": "OLD", "created_at": old, "trigger": "SCHEDULED", "changes": {}})
    assert not ok
    assert "utløpt" in detail.lower()


def test_navigation_and_banner_repairs_are_in_source():
    app = Path("app.py").read_text(encoding="utf-8")
    config = Path(".streamlit/config.toml").read_text(encoding="utf-8")
    banner = Path("ui/live_market_banner.py").read_text(encoding="utf-8")
    assert "Do not inject a second mobile/navigation DOM into the main page" in app
    assert "showSidebarNavigation = false" in config
    assert '[data-testid="stSidebarNav"] { display:none !important; }' in app
    assert 'price_txt = "Data mangler" if price_missing' in banner
    assert 'with st.expander("Rediger bannere"' in app
    assert 'render_special_watch_menu_v18619(embedded=True)' in app


def test_report_requirements_remain_present():
    report = Path("decision_report.py").read_text(encoding="utf-8")
    required = ["decision_diff", "counter_hypothesis", "source_consensus", "report_reliability", "next_run_tasks"]
    lower = report.lower()
    for token in required:
        assert token in lower

def test_trade_block_summary_explains_no_trade():
    params = ap.AutonomousParameters(maximum_open_positions=2)
    portfolio = {"status": "ACTIVE", "positions": {"A": {}, "B": {}}}
    summary = ap.autonomous_trade_block_summary([], portfolio, params)
    assert "maks 2 åpne posisjoner" in summary["headline"]


def test_web_process_has_guarded_scheduler_safety_net():
    app = Path("app.py").read_text(encoding="utf-8")
    assert "kick_scheduler_background" in app
    assert "scheduler_kick_last_v1940" in app
    assert ">= 300" in app


def test_operations_panel_exposes_unattended_runner_and_notification_times():
    source = Path("operations_ui.py").read_text(encoding="utf-8")
    assert "load_unattended_state" in source
    for field in ("Opprettet", "Planlagt", "Forsøkt", "Sendt", "Utløst av"):
        assert field in source


def test_missing_price_ticker_card_is_rendered_not_dropped():
    source = Path("ui/live_market_banner.py").read_text(encoding="utf-8")
    assert "change_html = (" in source
    assert "Ingen markedsdata" in source
    assert 'spark_html = "" if price_missing' in source
    assert 'price_txt = "Data mangler" if price_missing' in source
    assert 'if not price_missing else ""\n            "</div>"' not in source


def test_notification_message_has_single_status_line():
    source = Path(mi.__file__).read_text(encoding="utf-8")
    marker = 'f"Status: {(run.get(\'report_status\') or {}).get(\'label\', \'Eldre rapport\')} · {revision.get(\'revision_label\', \'R1\')}",'
    assert source.count(marker) == 1


def test_existing_position_and_paused_portfolio_get_explicit_ledger_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "ROOT", tmp_path)
    monkeypatch.setattr(ap, "PORTFOLIO_PATH", tmp_path / "portfolio.json")
    monkeypatch.setattr(ap, "LEARNING_PORTFOLIO_PATH", tmp_path / "learning_portfolio.json")
    monkeypatch.setattr(ap, "TRADES_PATH", tmp_path / "trades.json")
    monkeypatch.setattr(ap, "DECISIONS_PATH", tmp_path / "decisions.json")
    monkeypatch.setattr(ap, "LEARNING_TRADES_PATH", tmp_path / "learning_trades.json")
    monkeypatch.setattr(ap, "LEARNING_DECISIONS_PATH", tmp_path / "learning_decisions.json")
    monkeypatch.setattr(ap, "EQUITY_HISTORY_PATH", tmp_path / "equity.json")
    monkeypatch.setattr(ap, "LEARNING_EQUITY_HISTORY_PATH", tmp_path / "learning_equity.json")
    monkeypatch.setattr(ap, "PERFORMANCE_PATH", tmp_path / "performance.json")
    monkeypatch.setattr(ap, "LEARNING_PERFORMANCE_PATH", tmp_path / "learning_performance.json")
    monkeypatch.setattr(ap, "NOTIFICATIONS_PATH", tmp_path / "notifications.json")
    monkeypatch.setattr(ap, "AUDIT_PATH", tmp_path / "audit.jsonl")
    params = ap.AutonomousParameters(initial_cash=100000, minimum_investment_score=70, minimum_data_quality=0, maximum_risk_score=100, allow_additions=False)
    monkeypatch.setattr(ap, "load_parameters", lambda: params)
    monkeypatch.setattr(ap, "save_parameters", lambda *_: None)
    monkeypatch.setattr(ap, "load_learning_portfolio", lambda: {"cash": 0, "positions": {}, "status": "ACTIVE"})
    monkeypatch.setattr(ap, "_update_learning_positions", lambda *args: ([], []))
    monkeypatch.setattr(ap, "_record_learning_decisions", lambda *args: None)
    monkeypatch.setattr(ap, "_record_learning_trade", lambda *args: None)
    monkeypatch.setattr(ap, "_write", lambda *args: None)
    monkeypatch.setattr(ap, "_append_equity_history", lambda *args, **kwargs: None)
    monkeypatch.setattr(ap, "_append_learning_equity_history", lambda *args, **kwargs: None)
    monkeypatch.setattr(ap, "_append_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(ap, "_record_decisions", lambda rows: setattr(ap, "_captured_decisions", list(rows)))

    monkeypatch.setattr(ap, "load_portfolio", lambda: {"cash": 50000, "positions": {"AIZ": {"ticker": "AIZ", "quantity": 1, "average_price": 100, "last_price": 100, "highest_price": 100}}, "status": "ACTIVE", "high_watermark": 50100})
    ap.run_autonomous_cycle([{"ticker": "AIZ", "investment_score": 90, "data_quality_score": 100, "data_quality": 100, "risk_score": 10, "price": 100, "portfolio_action": "BUY", "autonomy_outcome_code": "KJØPSKANDIDAT", "valid_for_decision": True, "evidence_valid_for_decision": True, "final_decision_ready": True}], "R-EXIST")
    assert any("allerede i porteføljen" in str(row.get("reason", "")) for row in ap._captured_decisions)

    monkeypatch.setattr(ap, "load_portfolio", lambda: {"cash": 50000, "positions": {}, "status": "PAUSED", "pause_reason": "Manuell pause", "high_watermark": 100000})
    ap.run_autonomous_cycle([{"ticker": "EQNR.OL", "investment_score": 90, "data_quality_score": 100, "risk_score": 10, "price": 300}], "R-PAUSE")
    assert any(row.get("execution_stage") == "PORTFOLIO_PAUSED" and row.get("ticker") == "EQNR.OL" for row in ap._captured_decisions)


def test_mobile_portfolio_uses_cards_and_hides_desktop_tables():
    source = Path(ap.__file__).read_text(encoding="utf-8")
    assert "_render_trade_cards_mobile" in source
    assert "_render_decision_cards_mobile" in source
    assert 'key="autonomous-desktop-positions-v1940"' in source
    assert 'key="autonomous-desktop-trades-v1940"' in source
    assert 'key="autonomous-desktop-decisions-v1940"' in source
    assert '@media(max-width:760px)' in source


def test_scheduled_pushover_success_records_complete_lifecycle(tmp_path, monkeypatch):
    import sys
    import types
    monkeypatch.setattr(mi, "REPORT_NOTIFICATION_RECEIPTS_PATH", tmp_path / "receipts.json")
    monkeypatch.setattr(mi, "_durable_key", lambda path: None)
    monkeypatch.setattr(mi, "report_public_url", lambda run: "https://example.invalid/report.pdf")
    monkeypatch.setattr(mi, "resolve_report_identity", lambda run: {"type": "MORGENRAPPORT", "label": "Morgenrapport"})
    fake = types.ModuleType("notifier")
    fake.send_pushover_alert = lambda *args, **kwargs: (True, "HTTP 200")
    monkeypatch.setitem(sys.modules, "notifier", fake)
    job = mi.JobProfile(job_id="J1", name="Morgenrapport", notify_pushover=True, notification_mode="ALWAYS")
    now = datetime.now(timezone.utc)
    run = {
        "run_id": "R-SCHEDULED", "report_id": "REPORT-1", "created_at": now.isoformat(),
        "scheduled_for": (now - timedelta(minutes=2)).isoformat(), "trigger": "SCHEDULED",
        "changes": {}, "markets": ["Norge"], "summary": {}, "report_status": {"label": "Endelig"},
        "report_revision": {"revision_label": "R1"}, "candidates": [],
    }
    ok, detail = mi._notification(job, run)
    assert ok is True
    data = mi._read(mi.REPORT_NOTIFICATION_RECEIPTS_PATH, {})["R-SCHEDULED"]
    assert data["status"] == "SENT"
    assert data["triggered_by"] == "SCHEDULED"
    assert data["scheduled_at"] == run["scheduled_for"]
    assert data["attempted_at"]
    assert data["sent_at"]
    assert data["report_id"] == "REPORT-1"


def test_manual_notification_has_no_scheduled_timestamp(tmp_path, monkeypatch):
    import sys
    import types
    monkeypatch.setattr(mi, "REPORT_NOTIFICATION_RECEIPTS_PATH", tmp_path / "receipts.json")
    monkeypatch.setattr(mi, "_durable_key", lambda path: None)
    monkeypatch.setattr(mi, "report_public_url", lambda run: "")
    monkeypatch.setattr(mi, "resolve_report_identity", lambda run: {"type": "UTKAST", "label": "Utkast"})
    fake = types.ModuleType("notifier")
    fake.send_pushover_alert = lambda *args, **kwargs: (True, "HTTP 200")
    monkeypatch.setitem(sys.modules, "notifier", fake)
    job = mi.JobProfile(job_id="J2", name="Manuelt utkast", notify_pushover=True, notification_mode="ALWAYS")
    run = {"run_id": "R-MANUAL", "created_at": datetime.now(timezone.utc).isoformat(), "trigger": "MANUAL", "changes": {}, "markets": [], "summary": {}, "candidates": []}
    ok, detail = mi._notification(job, run)
    assert ok is True
    row = mi._read(mi.REPORT_NOTIFICATION_RECEIPTS_PATH, {})["R-MANUAL"]
    assert row["scheduled_at"] == ""
    assert row["triggered_by"] == "MANUAL"
