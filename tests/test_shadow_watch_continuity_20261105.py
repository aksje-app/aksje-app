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
    assert first["assessment"]["color"] == "GUL"
    assert "Modne observasjoner: 0" in sent[0][0]
    again = run_daily_watch(learning, shadow, guard, now=now,
        read_state=lambda key: store.get(key),
        write_state=lambda key, value: store.__setitem__(key, value), sender=sender)
    assert again["status"] == "ALREADY_SENT"
    assert len(sent) == 1
