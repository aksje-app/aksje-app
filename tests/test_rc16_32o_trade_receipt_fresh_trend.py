from __future__ import annotations

from datetime import datetime
from io import BytesIO

import app_version
import fresh_trend_monitor as fresh
import notifier
import paper_store
import super_portfolio
import trading_engine
from pypdf import PdfReader


def _memory_store(monkeypatch):
    data = {}

    def read_json(_key, _path, default):
        return data.get("value", default)

    def write_json(_key, _path, value):
        data["value"] = value

    monkeypatch.setattr(notifier, "read_json", read_json)
    monkeypatch.setattr(notifier, "write_json", write_json)
    return data


def test_failed_trade_notification_is_durable_and_retry_only_resends_notification(monkeypatch):
    _memory_store(monkeypatch)
    attempts = []

    def sender(**payload):
        attempts.append(dict(payload))
        return (False, "timeout") if len(attempts) == 1 else (True, None)

    monkeypatch.setattr(notifier, "notify_trade", sender)
    ok, detail = notifier.queue_trade_notification(
        "TRADE-1", trade_type="BUY", ticker="ATCO-B.ST", price=176.45,
        amount=7827.0, shares=45.766695, confidence=76, reason="BUY signal",
    )
    assert ok is False and detail == "timeout"
    assert notifier.trade_notification_receipts()[0]["status"] == "FAILED"

    result = notifier.retry_pending_trade_notifications(limit=10)
    assert result["attempted"] == 1
    assert result["sent"] == 1
    receipt = notifier.trade_notification_receipts()[0]
    assert receipt["status"] == "SENT"
    assert receipt["attempts"] == 2
    assert len(attempts) == 2


def test_unknown_entry_time_is_not_reported_as_zero_holding_days():
    assert trading_engine._holding_period({}, "ATCO-B.ST") == (None, False)
    days, known = trading_engine._holding_period(
        {"opened_at": datetime.now().isoformat(timespec="seconds")}, "ATCO-B.ST"
    )
    assert known is True
    assert days == 0


def test_trade_message_distinguishes_unknown_holding_time_and_buy_score(monkeypatch):
    messages = []
    monkeypatch.setattr(notifier, "send_pushover_alert", lambda message, **kwargs: (messages.append(message) or True, None))
    notifier.notify_trade(
        "SELL", "ATCO-B.ST", 171.05, entry_price=176.45, holding_days=None,
        holding_time_known=False, entry_score=None, exit_score=None,
    )
    assert "Eiertid: ukjent – kjøpstidspunkt mangler" in messages[-1]
    assert "Eiertid: 0" not in messages[-1]

    notifier.notify_trade("BUY", "GETI-B.ST", 100, entry_score=66.0)
    assert "Score ved kjøp: 66.0" in messages[-1]
    assert "66.0 → 0.0" not in messages[-1]


def test_fresh_trend_distinguishes_historical_returns_from_signal_follow_up():
    assert fresh.VERSION == app_version.APP_VERSION
    assert fresh._completed_signal_sessions(1) == 0
    assert fresh._completed_signal_sessions(2) == 1
    assert fresh._completed_signal_sessions(5) == 4

    title, body = fresh._message({
        "ticker": "DOFG.OL", "company_name": "DOF Group", "exchange": "Oslo Børs", "country": "Norge",
        "status": "AVVENTER BEKREFTELSE", "emoji": "⚪", "follow_up_session": 1,
        "last_price": 132.9, "initial_price": 132.0, "score_path": [93.0],
        "components": {"Score delta": 0, "Confirmation": 41, "Velocity": 67, "Risk": 0},
        "changes": {"horizons": {
            "1": {"amount": -2.2, "pct": -1.63}, "3": {"amount": 2.2, "pct": 1.68}, "5": {"amount": 2.6, "pct": 2.0},
        }},
        "direction": {"label": "SIDELENGS / AVVENT", "score": -4.2, "data_coverage": 67},
        "fresh_signal": {"trend_age_sessions": 1}, "data_freshness": {"status": "FERSK_INNHENTET", "age_seconds": 0},
        "pullback_retest": {"label": "INGEN RETEST"},
    })
    assert title
    assert "Fresh Trend-oppfølging: dag 1 av 5 børsdager" in body
    assert "Historisk kursutvikling bakover" in body
    assert "Utvikling siden signalstart" in body


def test_super_portfolio_uses_canonical_version_and_plain_weight_language():
    assert super_portfolio.VERSION == app_version.APP_VERSION
    assert super_portfolio._weight_change_text({"action": "BUY", "ticker": "GETI-B.ST", "from_pct": 0, "to_pct": 10}) == (
        "BUY GETI-B.ST: Ny posisjon · målvekt 10.0%"
    )
    assert "Avslutter posisjon" in super_portfolio._weight_change_text(
        {"action": "SELL", "ticker": "ATCO-B.ST", "from_pct": 8.4, "to_pct": 0}
    )


def test_super_portfolio_pdf_includes_listing_and_industry_columns():
    state = super_portfolio.default_state(super_portfolio.SuperPortfolioConfig())
    state.update({
        "updated_at": "2026-09-18T12:00:00+00:00",
        "source_run_id": "TEST-32O",
        "positions": {"BWLPG.OL": {
            "ticker": "BWLPG.OL", "country": "Norge", "exchange": "Oslo Børs",
            "sector": "Energi", "industry": "Olje og gass", "target_weight_pct": 8.5,
            "pnl_pct": 2.0, "portfolio_score_adjusted": 64, "rank": 6,
            "stop_status": "SAFE", "stop_pressure": "LOW",
        }},
    })
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(super_portfolio.build_pdf(state))).pages)
    assert app_version.APP_VERSION in text
    for label in ("Land / børs", "Bransje", "Norge", "Oslo Børs", "Olje og gass"):
        assert label in text


def test_postgres_trade_schema_preserves_delivery_and_entry_metadata():
    source = open(paper_store.__file__, encoding="utf-8").read()
    for column in ("exchange", "entry_score", "exit_score", "score_path", "trade_id"):
        assert f"ADD COLUMN IF NOT EXISTS {column}" in source
