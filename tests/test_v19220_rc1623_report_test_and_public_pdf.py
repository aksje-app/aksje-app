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


def test_public_url_fails_closed_without_durable_token(monkeypatch):
    monkeypatch.setenv("REPORT_PUBLIC_BASE_URL", "https://aksje-app.onrender.com/app/static/reports")
    monkeypatch.setenv("REPORT_BASE_URL", "https://aksje-app.onrender.com")
    assert report_delivery.public_report_url({"public_pdf_name": "old.pdf"}) == ""


def test_notification_copy_preserves_durable_public_token():
    source = open("market_intelligence.py", encoding="utf-8").read()
    notification_block = source[source.index("notification_view = dict(canonical_run)"):source.index("notify_ok, notify_detail")]
    assert '"public_report_token"' in notification_block


def test_pushover_receives_root_query_url_not_static_page(monkeypatch):
    import sys
    import types
    import market_intelligence as mi

    captured = {}
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://aksje-app.onrender.com")
    monkeypatch.setattr(mi, "_read", lambda *args, **kwargs: {})
    monkeypatch.setattr(mi, "_write", lambda *args, **kwargs: None)
    monkeypatch.setattr(mi, "_audit", lambda *args, **kwargs: None)

    def fake_send(message, **kwargs):
        captured.update(kwargs)
        return True, "Sendt"

    monkeypatch.setitem(sys.modules, "notifier", types.SimpleNamespace(send_pushover_alert=fake_send))
    job = mi.JobProfile(name="Autonomi rapporttest", notification_mode="ALWAYS")
    token = "T" * 43
    run = {
        "run_id": "MI-NOTIFY-ROUTE", "created_at": datetime.now(timezone.utc).isoformat(),
        "trigger": "TEST", "test_run": True, "public_pdf_name": "report.pdf",
        "public_report_token": token, "markets": ["Norge"],
        "summary": {"deep_analyzed": 1, "recommended": 0}, "changes": {},
        "report_status": {"label": "TEST"}, "report_revision": {"revision_label": "R1"},
        "candidates": [], "proposals": [],
    }
    ok, detail = mi._notification(job, run)
    assert ok is True
    assert detail == "Sendt"
    assert captured["url"] == f"https://aksje-app.onrender.com/?public_report_token={token}"
    assert "/app/static/" not in captured["url"]


def test_report_test_mode_is_bounded_and_due_every_30_minutes():
    now = datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc)
    state = {"enabled": True, "enabled_at": (now - timedelta(minutes=31)).isoformat(), "last_started_at": "", "successes": 0, "failures": 0}
    assert test_mode.test_mode_due(state, now=now) is True
    state["last_started_at"] = (now - timedelta(minutes=29)).isoformat()
    assert test_mode.test_mode_due(state, now=now) is False
    state["successes"] = 4
    assert test_mode.test_mode_due(state, now=now) is False


def test_report_test_mode_uses_explicit_half_hour_deadline_without_second_drift():
    first_cron = datetime(2026, 8, 9, 12, 31, 26, tzinfo=timezone.utc)
    state = {
        "enabled": True,
        "enabled_at": (first_cron - timedelta(minutes=5)).isoformat(),
        "next_due_at": "2026-08-09T13:00:00+00:00",
        "last_started_at": first_cron.isoformat(),
        "successes": 1,
        "failures": 0,
    }
    assert test_mode.test_mode_due(state, now=datetime(2026, 8, 9, 12, 59, 59, tzinfo=timezone.utc)) is False
    assert test_mode.test_mode_due(state, now=datetime(2026, 8, 9, 13, 0, 1, tzinfo=timezone.utc)) is True


def test_next_half_hour_aligns_four_cron_slots():
    starts = [
        datetime(2026, 8, 9, 12, 31, 26, tzinfo=timezone.utc),
        datetime(2026, 8, 9, 13, 1, 12, tzinfo=timezone.utc),
        datetime(2026, 8, 9, 13, 31, 8, tzinfo=timezone.utc),
        datetime(2026, 8, 9, 14, 1, 15, tzinfo=timezone.utc),
    ]
    expected = [
        "2026-08-09T13:00:00+00:00",
        "2026-08-09T13:30:00+00:00",
        "2026-08-09T14:00:00+00:00",
        "2026-08-09T14:30:00+00:00",
    ]
    assert [test_mode._next_half_hour(value).isoformat(timespec="seconds") for value in starts] == expected


def test_persist_state_retries_transient_database_failure(monkeypatch):
    attempts = []

    def flaky_write(*args):
        attempts.append(args)
        if len(attempts) < 3:
            raise RuntimeError("database temporarily unavailable")

    monkeypatch.setattr(test_mode, "write_json", flaky_write)
    monkeypatch.setattr(test_mode.time, "sleep", lambda *_: None)
    test_mode._persist_state({"enabled": True})
    assert len(attempts) == 3


def test_four_automatic_cron_runs_complete_and_stop(monkeypatch):
    import sys
    from types import SimpleNamespace

    clock = [datetime(2026, 8, 9, 12, 31, 26, tzinfo=timezone.utc)]
    store = {
        "enabled": True,
        "enabled_at": datetime(2026, 8, 9, 12, 25, tzinfo=timezone.utc).isoformat(),
        "next_due_at": datetime(2026, 8, 9, 12, 25, tzinfo=timezone.utc).isoformat(),
        "last_started_at": "",
        "successes": 0,
        "failures": 0,
    }

    monkeypatch.setattr(test_mode, "_now", lambda: clock[0])
    monkeypatch.setattr(test_mode, "load_report_test_mode", lambda: dict(store))
    monkeypatch.setattr(test_mode, "_persist_state", lambda state: store.update(dict(state)))
    monkeypatch.setitem(sys.modules, "notifier", SimpleNamespace(send_pushover_alert=lambda *args, **kwargs: (True, None)))
    monkeypatch.setattr(test_mode, "build_test_job", lambda **kwargs: object())
    monkeypatch.setattr(
        "market_intelligence.run_job",
        lambda *args, **kwargs: {
            "run_id": f"MI-{clock[0].strftime('%H%M%S')}",
            "notification": {"sent": True, "status_label": "Sendt"},
        },
    )

    starts = [
        datetime(2026, 8, 9, 12, 31, 26, tzinfo=timezone.utc),
        datetime(2026, 8, 9, 13, 1, 12, tzinfo=timezone.utc),
        datetime(2026, 8, 9, 13, 31, 8, tzinfo=timezone.utc),
        datetime(2026, 8, 9, 14, 1, 15, tzinfo=timezone.utc),
    ]
    for expected_count, current in enumerate(starts, 1):
        clock[0] = current
        result = test_mode.run_due_report_test()
        assert result["successes"] == expected_count
        assert result["last_notification_status"] == "Sendt"

    assert store["enabled"] is False
    assert store["disabled_reason"] == "SUCCESS_LIMIT"
    assert store["successes"] == 4


def test_notification_failure_does_not_count_as_success(monkeypatch):
    now = datetime(2026, 8, 9, 12, 31, 26, tzinfo=timezone.utc)
    store = {
        "enabled": True, "enabled_at": (now - timedelta(minutes=5)).isoformat(),
        "next_due_at": (now - timedelta(seconds=1)).isoformat(),
        "last_started_at": "", "successes": 0, "failures": 0,
    }
    monkeypatch.setattr(test_mode, "_now", lambda: now)
    monkeypatch.setattr(test_mode, "load_report_test_mode", lambda: dict(store))
    monkeypatch.setattr(test_mode, "_persist_state", lambda state: store.update(dict(state)))
    monkeypatch.setattr(test_mode, "build_test_job", lambda **kwargs: object())
    monkeypatch.setattr(
        "market_intelligence.run_job",
        lambda *args, **kwargs: {
            "run_id": "MI-NOTIFY-FAILED",
            "notification": {"sent": False, "attempted": True, "status_label": "Feilet", "detail": "Pushover timeout"},
        },
    )
    result = test_mode.run_due_report_test()
    assert result["successes"] == 0
    assert result["failures"] == 1
    assert result["run_state"] == "FAILED_NOTIFICATION"
    assert result["last_error"] == "Pushover timeout"


def test_final_persistence_failure_does_not_mask_report_error(monkeypatch):
    now = datetime(2026, 8, 9, 12, 31, 26, tzinfo=timezone.utc)
    state = {
        "enabled": True, "enabled_at": (now - timedelta(minutes=5)).isoformat(),
        "next_due_at": (now - timedelta(seconds=1)).isoformat(),
        "last_started_at": "", "successes": 0, "failures": 0,
    }
    writes = []

    def persist(value):
        writes.append(dict(value))
        if len(writes) > 1:
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(test_mode, "_now", lambda: now)
    monkeypatch.setattr(test_mode, "load_report_test_mode", lambda: dict(state))
    monkeypatch.setattr(test_mode, "_persist_state", persist)
    monkeypatch.setattr(test_mode, "build_test_job", lambda **kwargs: object())
    monkeypatch.setattr("market_intelligence.run_job", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("original report error")))
    result = test_mode.run_due_report_test()
    assert result["run_state"] == "FAILED_STATE_NOT_PERSISTED"
    assert "original report error" in result["last_error"]
    assert "database unavailable" in result["persistence_error"]


def test_test_job_runs_isolated_theoretical_learning_chain(monkeypatch):
    from market_intelligence import JobProfile
    source = JobProfile(name="Morgenanalyse", run_autonomous_portfolio=True, run_controlled_learning=True)
    monkeypatch.setattr("market_intelligence.load_jobs", lambda: [source])
    job = test_mode.build_test_job()
    assert job.run_autonomous_portfolio is True
    assert job.run_controlled_learning is True
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


def test_public_renderer_uses_native_static_pdf_not_optional_st_pdf():
    source = open("public_report_ui.py", encoding="utf-8").read()
    assert "st.pdf(" not in source
    assert "_hydrate_static_pdf(token, report)" in source
    assert "window.top.location.replace" not in source
    assert "Åpne PDF i ny fane" in source
    assert "Tilbake til AI Aksje Analyzer" in source
    assert 'target="_blank"' in source
    assert 'target="_self"' in source


def test_static_pdf_is_hydrated_atomically_on_web_instance(monkeypatch, tmp_path):
    import public_report_ui
    import report_delivery

    monkeypatch.setattr(report_delivery, "PUBLIC_REPORT_DIR", tmp_path / "static" / "reports")
    token = "H" * 43
    target, url = public_report_ui._hydrate_static_pdf(token, {"data": b"%PDF-1.4\n%%EOF"})
    assert target.read_bytes().startswith(b"%PDF-")
    assert target.name == f"public_report_{token}.pdf"
    assert url == f"/app/static/reports/public_report_{token}.pdf"
    assert not target.with_suffix(".pdf.tmp").exists()
