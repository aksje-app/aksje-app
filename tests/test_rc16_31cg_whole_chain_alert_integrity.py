from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
import zipfile

import candidate_market_data
import fresh_trend_monitor as monitor
import notifier
import trend_intelligence
from exit_policy import evaluate_exit
from market_intelligence import build_complete_report_package


NOW = datetime(2026, 9, 11, 8, 0, tzinfo=timezone.utc)


def receipt(ticker="WWI.OL", *, score=92.0, price=844.0, age=2, hold=1,
            data_at="2026-09-11T08:00:00+00:00", signal_id="SIG-1"):
    return {
        "ticker": ticker, "name": ticker.split(".")[0], "exchange_name": "Oslo Børs",
        "country": "Norge", "market": "NORGE", "last_price": price,
        "return_1d_pct": -0.24, "return_3d_pct": 3.1, "return_5d_pct": 3.9,
        "volume_ratio_20": 0.64, "latest_volume": 184000, "average_volume_20": 287500,
        "volume_comparison_basis": "dagsvolum mot ferdige 20d-dager; ikke tidsjustert",
        "breakout_hold_sessions": hold, "breakout_20d": True, "breakout_holding": True,
        "prior_20d_high": 836.0, "market_rs_5d_percentile": 72.0,
        "sector_rs_5d_percentile": 68.0, "market_rs_universe_count_5d": 286,
        "sector_rs_universe_count_5d": 31, "rs_reference_scope": "FULL_STAGE1_UNIVERSE",
        "rs_full_stage1_universe": 294, "momentum_acceleration_3v20": 1.7,
        "rsi": 60, "sma20": 810.5,
        "action_levels": {"breakout_level": 836.0, "invalidation_level": 810.5, "first_target": 887.0},
        "data_freshness": {"status": "FERSK_INNHENTET", "timestamp": data_at,
                           "fetched_at": data_at, "observed_timestamp": data_at, "age_seconds": 60},
        "fresh_signal": {"signal_id": signal_id, "score": score, "trend_age_sessions": age,
                         "signals": [{"label": "3d akselerasjon +1.7 pp"}, {"label": "20d-brudd"}]},
    }


def evaluate(row, state=None, minutes=0):
    old = monitor.write_json
    monitor.write_json = lambda *_a, **_k: None
    try:
        return monitor.monitor_receipts([row], now=NOW + timedelta(minutes=minutes), state=state or {}, notify=False)
    finally:
        monitor.write_json = old


def test_signal_age_and_breakout_hold_never_go_backwards_for_same_signal():
    first = evaluate(receipt(age=3, hold=2))
    second = evaluate(receipt(age=0, hold=0, data_at="2026-09-11T08:15:00+00:00"), first, 15)
    row = second["watchlist"][0]
    assert row["signal_age_sessions"] == 3
    assert row["fresh_signal"]["reported_trend_age_sessions"] == 0
    assert row["breakout_hold_sessions"] == 2
    assert row["reported_breakout_hold_sessions"] == 0
    assert not row["invariant_errors"]


def test_explicit_new_signal_may_reset_counters():
    first = evaluate(receipt(age=3, hold=2, signal_id="OLD"))
    second = evaluate(receipt(age=0, hold=0, signal_id="NEW", data_at="2026-09-11T08:15:00+00:00"), first, 15)
    row = second["watchlist"][0]
    assert row["signal_age_sessions"] == 0
    assert row["breakout_hold_sessions"] == 0


def test_rogs_drop_cannot_be_called_acceleration():
    first = evaluate(receipt("ROGS.OL", score=95))
    second = evaluate(receipt("ROGS.OL", score=81, data_at="2026-09-11T08:15:00+00:00"), first, 15)
    row = second["watchlist"][0]
    assert row["status"] == "MISTER MOMENT"
    assert row["direction"]["score"] < 0
    assert "AKSELERERER" not in second["alerts"][0]["title"]


def test_wwi_recovery_requires_hysteresis_and_does_not_flip_on_one_scan():
    first = evaluate(receipt(score=92))
    weak = evaluate(receipt(score=75, price=838, data_at="2026-09-11T08:15:00+00:00"), first, 15)
    one_recovery = evaluate(receipt(score=80, price=842, data_at="2026-09-11T08:30:00+00:00"), weak, 30)
    assert weak["watchlist"][0]["status"] == "MISTER MOMENT"
    assert one_recovery["watchlist"][0]["status"] != "AKSELERERER"


def test_dno_message_separates_setup_direction_and_coverage():
    result = evaluate(receipt("DNO.OL", score=100))
    message = result["alerts"][0]["message"]
    assert "Oppsettstatus:" in message
    assert "Retning nå:" in message
    assert "datadekning" in message
    assert "sikkerhet" not in message.lower()
    assert "basis dagsvolum" in message


def test_score_path_and_delta_use_same_precision():
    first = evaluate(receipt(score=100.0))
    second = evaluate(receipt(score=99.4, data_at="2026-09-11T08:15:00+00:00"), first, 15)
    _title, message = monitor._message(second["watchlist"][0])
    assert "Score 100.0 → 99.4 · sist -0.6" in message


def test_line_safe_compaction_keeps_one_footer_and_no_partial_data_line():
    row = receipt(score=70)
    row["name"] = "Et svært langt selskapsnavn " * 80
    result = evaluate(row)
    message = result["alerts"][0]["message"]
    assert len(message) <= notifier.PUSHOVER_MESSAGE_LIMIT
    assert message.count("v19.22.0-rc16.31cg") == 1
    assert message.count("Data:") == 1
    assert not any(line == "Data: F..." for line in message.splitlines())
    assert "Handling:" in message


def test_generic_pushover_compaction_is_line_safe(monkeypatch):
    captured = {}
    monkeypatch.setattr(notifier, "notifications_allowed", lambda: (True, "OK"))
    monkeypatch.setattr(notifier, "pushover_enabled", lambda: True)
    monkeypatch.setattr(notifier, "load_settings", lambda: {"pushover_enabled": True})
    monkeypatch.setattr(notifier, "_recent_duplicate", lambda *_a, **_k: False)
    monkeypatch.setattr(notifier, "_record_notification_fingerprint", lambda *_a, **_k: None)
    monkeypatch.setattr(notifier, "_log_delivery", lambda *_a, **_k: None)
    class Response:
        status_code = 200
        text = "OK"
    def post(_url, data, timeout):
        captured.update(data)
        return Response()
    monkeypatch.setattr(notifier.requests, "post", post)
    assert notifier.send_pushover_alert("\n".join(f"HEL LINJE {i} " + "x" * 80 for i in range(50)))[0]
    assert len(captured["message"]) <= 1024
    assert captured["message"].splitlines()[-1] == "… flere detaljer i rapportlenken"
    assert not captured["message"].endswith("x…")


def test_bounded_refresh_preserves_full_scan_rs(monkeypatch):
    source = receipt()
    latest = {"markets": ["Norge"], "completed_at": "2026-09-11T07:45:00+00:00",
              "trend_discovery": {"coverage": {"full_stage1_universe": 294},
                                  "fresh_trend_watchlist": [source]}}
    calls = iter([{}, latest])
    monkeypatch.setattr(monitor, "read_json", lambda *_a, **_k: next(calls))
    monkeypatch.setattr(monitor, "write_json", lambda *_a, **_k: None)
    monkeypatch.setattr(candidate_market_data, "enrich_candidate_rows", lambda rows, **_k: rows)
    def fake_annotate(run, _history):
        reduced = dict(run["candidates"][0])
        reduced.update({"market_rs_5d_percentile": 50.0, "market_rs_universe_count_5d": 1})
        run["trend_discovery"] = {"fresh_trend_watchlist": [reduced]}
    monkeypatch.setattr(trend_intelligence, "annotate_run", fake_annotate)
    result = monitor.run_due_monitor(now=NOW, notify=False)
    row = result["watchlist"][0]
    assert row["market_rs_5d_percentile"] == 72.0
    assert row["market_rs_universe_count_5d"] == 286
    assert row["rs_full_stage1_universe"] == 294
    assert row["rs_reference_scope"] == "FULL_STAGE1_UNIVERSE"


def test_partial_rs_queue_cannot_create_positive_alert():
    row = receipt(score=100)
    row.update({"rs_reference_scope": "PARTIAL_MONITOR_QUEUE",
                "market_rs_universe_count_5d": 12, "rs_full_stage1_universe": 294})
    result = evaluate(row)
    assert result["alerts"] == []
    assert result["watchlist"][0]["decision_data_valid"] is False
    assert "fullscan" in result["watchlist"][0]["decision_validation_reason"]


def test_unfinished_daily_volume_is_visible_but_not_negative_scoring():
    row = receipt(score=92)
    row.update({"volume_bar_complete": False, "volume_time_adjusted": False})
    result = evaluate(row)
    evaluated = result["watchlist"][0]
    assert evaluated["components"]["Confirmation volume"] == 0
    assert evaluated["components"]["Risk"] == 0
    assert "ingen negativ poengføring" in result["alerts"][0]["message"]


def test_identical_snapshot_is_deterministic_and_silent():
    first = evaluate(receipt())
    second = evaluate(receipt(data_at="2026-09-11T08:15:00+00:00"), first, 15)
    assert second["watchlist"][0]["snapshot_unchanged"] is True
    assert second["alerts"] == []


def test_complete_download_really_contains_pdf_json_text_and_diagnosis():
    files = {
        "Morgenrapport.pdf": b"%PDF-main",
        "Morgenrapport_technical.pdf": b"%PDF-tech",
        "Morgenrapport.json": b"{}",
        "Morgenrapport.txt": b"rapport",
        "Bakgrunnsjobb_diagnose.zip": b"PK-diagnose",
    }
    package, manifest = build_complete_report_package(files, "MI-TEST")
    assert manifest["core_report_complete"] is True
    assert manifest["diagnostic_included"] is True
    with zipfile.ZipFile(BytesIO(package)) as archive:
        assert set(files).issubset(archive.namelist())
        assert "package_manifest.json" in archive.namelist()


def test_parallel_monitor_wake_is_skipped_without_notification(monkeypatch):
    class BusyLock:
        def __enter__(self):
            return False
        def __exit__(self, *_args):
            return False
    monkeypatch.setattr(monitor, "_monitor_execution_lock", lambda: BusyLock())
    result = monitor.run_due_monitor(now=NOW, notify=True)
    assert result["state"] == "ALREADY_RUNNING"
    assert "Ingen parallell" in result["notification_policy"]


def test_stagnation_never_names_an_implicit_replacement():
    unnamed = evaluate_exit(
        entry_price=100, current_price=100.5, highest_price=102,
        entry_score=78, current_score=69, holding_days=25,
        best_replacement_score=76,
    )
    named = evaluate_exit(
        entry_price=100, current_price=100.5, highest_price=102,
        entry_score=78, current_score=69, holding_days=25,
        best_replacement_score=76, replacement_ticker="NEW.OL",
        replacement_risk=35, replacement_momentum_pct=2.1,
    )
    assert unnamed["reason_code"] == "CAPITAL_STAGNATION"
    assert unnamed["replacement_ticker"] == ""
    assert named["reason_code"] == "CAPITAL_REPLACEMENT"
    assert "NEW.OL" in named["reason"]
