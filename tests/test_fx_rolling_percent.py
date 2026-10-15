from datetime import datetime, timedelta, timezone
import fx_rolling_percent as fx


def _sample(change, window="24t", threshold=1.5):
    return [{"window": window, "hours": 24, "threshold": threshold,
             "change_pct": change, "reference_rate": 1.90,
             "reference_at": "2026-10-14T12:00:00+00:00",
             "breach": abs(change) >= threshold}]


def test_first_breach_then_suppression_then_material_worsening():
    now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
    settings = {}
    messages = []
    def sender(message, title=None):
        messages.append((title, message))
        return True
    def run(pct, hours=0):
        return fx.evaluate(settings, symbol="BRLNOK=X", pair="BRL/NOK", rate=1.86,
                           sender=sender, now=now + timedelta(hours=hours),
                           changes=_sample(pct))
    assert run(-1.6)["sent"]
    assert not run(-1.8, 1)["sent"]
    assert not run(-2.2, 2)["sent"]
    assert run(-2.2, 7)["sent"]
    assert len(messages) == 2
    assert "Registrert:" in messages[0][1]


def test_reversal_and_return_to_normal():
    settings = {}
    now = datetime(2026, 10, 15, tzinfo=timezone.utc)
    sender = lambda *args, **kwargs: True
    def run(change):
        return fx.evaluate(settings, symbol="BRLNOK=X", pair="BRL/NOK",
                           rate=1.86, sender=sender, now=now, changes=_sample(change))
    assert run(-2)["sent"]
    assert run(.1)["reason"] == "no_breach"
    assert run(2)["sent"]


def test_missing_history_and_send_failure_do_not_record_sent():
    settings = {}
    def fail(*args, **kwargs):
        return False
    assert fx.evaluate(settings, symbol="BRLNOK=X", pair="BRL/NOK", rate=1.86,
                       sender=fail, changes=[])["reason"] == "no_breach"
    assert fx.evaluate(settings, symbol="BRLNOK=X", pair="BRL/NOK", rate=1.86,
                       sender=fail, changes=_sample(-2))["reason"] == "send_failed"
    assert "last_sent_at" not in settings[fx.STATE_KEY]["BRLNOK=X"]
