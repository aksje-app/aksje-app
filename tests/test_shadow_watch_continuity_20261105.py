from datetime import datetime
from zoneinfo import ZoneInfo

from services.shadow_daily_watch import run_daily_watch


def test_daily_learning_watch_continues_after_original_october_window():
    store = {}
    sent = []
    def sender(message, **kwargs):
        sent.append((message, kwargs))
        return True, "ok"
    now = datetime(2026, 11, 5, 9, tzinfo=ZoneInfo("America/Fortaleza"))
    learning = {"status": "COMPLETED", "matured": 0, "production_changed": False}
    shadow = {"status": "DEFERRED_MEMORY", "production_changed": False}
    guard = {"status": "COMPLETED"}
    first = run_daily_watch(learning, shadow, guard, now=now,
        read_state=lambda key: store.get(key),
        write_state=lambda key, value: store.__setitem__(key, value), sender=sender)
    assert first["delivery"] == "CONFIRMED"
    assert first["assessment"]["color"] == "RØD"
    assert "Modne observasjoner: 0" in sent[0][0]
    again = run_daily_watch(learning, shadow, guard, now=now,
        read_state=lambda key: store.get(key),
        write_state=lambda key, value: store.__setitem__(key, value), sender=sender)
    assert again["status"] == "ALREADY_SENT"
    assert len(sent) == 1


def test_suppressed_duplicate_is_not_a_delivery_receipt():
    result = run_daily_watch({'status': 'COMPLETED', 'matured': 10},
        {'status': 'COMPLETED'}, {'status': 'COMPLETED'},
        now=datetime(2026, 11, 5, 9, tzinfo=ZoneInfo('America/Fortaleza')),
        read_state=lambda key: {}, write_state=lambda *args: None,
        sender=lambda *args, **kw: (True, 'duplicate suppressed'))
    assert result['sent'] is False
    assert result['delivery'] == 'DUPLICATE_SUPPRESSED'
