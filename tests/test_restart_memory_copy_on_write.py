"""Restart memory must not duplicate unrelated account journals."""
from services.restart_trading import Memory


def test_memory_preserves_unmodified_account_identity():
    other = {"events": [{"payload": {"large": list(range(200))}}]}
    bundle = {"period_id": "p", "accounts": {"paper": {"events": []}, "autonomy": other}}
    memory = Memory(bundle, "restart.json")
    assert memory.bundle["accounts"]["autonomy"] is other
    assert memory.read_json("restart.json") is memory.bundle

    def update(current):
        return {**current, "accounts": {**current["accounts"], "paper": {"events": [1]}}}

    result = memory.mutate_json("restart.json", update)
    assert result["accounts"]["autonomy"] is other
    assert bundle["accounts"]["paper"]["events"] == []
    assert result["accounts"]["paper"]["events"] == [1]
