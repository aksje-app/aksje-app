from datetime import datetime, timedelta, timezone

import public_report_store as public_store
import report_delivery
import report_test_mode as test_mode


def test_durable_public_pdf_roundtrip(monkeypatch):
    memory = {}
    monkeypatch.setattr(public_store, "write_json", lambda key, path, value: memory.__setitem__(key, value))
    monkeypatch.setattr(public_store, "read_json", lambda key, path, default: memory.get(key, default))
    run = {"run_id": "MI-PUBLIC-1", "public_pdf_name": "rapport.pdf"}
    token = public_store.publish_durable_pdf(run, b"%PDF-1.4\n%%EOF")
    loaded = public_store.load_public_pdf(token)
    assert loaded["report_id"] == "MI-PUBLIC-1"
    assert loaded["data"].startswith(b"%PDF-")
    assert len(token) >= 32


def test_public_url_uses_unlisted_token_not_streamlit_page_route(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://aksje-app.onrender.com")
    url = report_delivery.public_report_url({"public_report_token": "A" * 43, "public_pdf_name": "old.pdf"})
    assert url == "https://aksje-app.onrender.com/?public_report_token=" + "A" * 43
    assert "/app/static/" not in url


def test_report_test_mode_is_bounded_and_due_every_30_minutes():
    now = datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc)
    state = {"enabled": True, "enabled_at": (now - timedelta(minutes=31)).isoformat(), "last_started_at": "", "successes": 0, "failures": 0}
    assert test_mode.test_mode_due(state, now=now) is True
    state["last_started_at"] = (now - timedelta(minutes=29)).isoformat()
    assert test_mode.test_mode_due(state, now=now) is False
    state["successes"] = 4
    assert test_mode.test_mode_due(state, now=now) is False


def test_test_job_is_hard_blocked_from_actions(monkeypatch):
    from market_intelligence import JobProfile
    source = JobProfile(name="Morgenanalyse", run_autonomous_portfolio=True, run_controlled_learning=True)
    monkeypatch.setattr("market_intelligence.load_jobs", lambda: [source])
    job = test_mode.build_test_job()
    assert job.run_autonomous_portfolio is False
    assert job.run_controlled_learning is False
    assert job.notification_mode == "ALWAYS"
    assert job.include_report_link is True


def test_waiting_interval_does_not_disable_test_mode(monkeypatch):
    now = datetime.now(timezone.utc)
    state = {
        "enabled": True, "enabled_at": (now - timedelta(minutes=10)).isoformat(),
        "last_started_at": (now - timedelta(minutes=5)).isoformat(), "successes": 0, "failures": 0,
    }
    writes = []
    monkeypatch.setattr(test_mode, "load_report_test_mode", lambda: dict(state))
    monkeypatch.setattr(test_mode, "write_json", lambda *args: writes.append(args[-1]))
    result = test_mode.run_due_report_test()
    assert result["run_state"] == "NOT_DUE"
    assert result["enabled"] is True
    assert writes == []


def test_full_report_center_contains_operator_controls():
    source = open("market_intelligence.py", encoding="utf-8").read()
    assert "Aktiver testrapport med Pushover hvert 30. minutt" in source
    assert "Kjør én test umiddelbart" in source
    assert "Stopp og slå av testmodus" in source
    app = open("app.py", encoding="utf-8").read()
    assert app.index("render_public_report(st)") < app.index("current_user = require_login()")
