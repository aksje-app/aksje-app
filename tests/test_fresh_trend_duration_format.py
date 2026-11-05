"""Long follow-up intervals are readable in Pushover messages."""
from pathlib import Path


def test_fresh_trend_message_formats_hours_and_minutes():
    source = (Path(__file__).resolve().parents[1] / "fresh_trend_monitor.py").read_text(encoding="utf-8")
    assert "hours, remainder = divmod(minutes, 60)" in source
    assert 'since_label = f"siden sist ({hours} t {remainder} min)"' in source
    assert 'since_label = f"siden sist ({minutes} min)"' in source
