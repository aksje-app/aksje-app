from learning_progress_view import percent, snapshot

class Storage:
    def read_json(self, key, default=None):
        if key.endswith("index.json"):
            return {"records": [{"engine": "AUTONOMY", "complete_universe": True}, {"engine": "SUPER_PORTFOLIO", "complete_universe": False}]}
        return {"status": "ACTIVE_SHADOW", "observed_trading_dates": 6, "validated": False, "last_at": "2026-10-19T12:00:00Z"}

def test_percent_requires_real_denominator():
    assert percent(72, 100) == 72
    assert percent(0, 0) is None
    assert percent(110, 100) is None

def test_missing_phase_data_is_not_fabricated():
    data = snapshot(Storage(), "AUTONOMY")
    assert data["history_frames"] == 1
    assert data["complete_frames"] == 1
    assert data["shadow_days"] == 6
    assert set(data["phases"].values()) == {None}
    assert data["trials"] is None
