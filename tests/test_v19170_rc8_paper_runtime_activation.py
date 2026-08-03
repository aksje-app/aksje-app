from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_safety_reads_persistent_drift_request():
    text = (ROOT / "runtime_safety.py").read_text(encoding="utf-8")
    assert "def _paper_runtime_request" in text
    assert "drift_paper_trading_enabled" in text
    assert "effective_enabled = bool(enabled or runtime_requested)" in text
    assert "source=source" in text


def test_drift_center_persists_runtime_paper_state():
    text = (ROOT / "drift_center.py").read_text(encoding="utf-8")
    assert 'settings["paper_trading_runtime_enabled"] = value' in text
    assert "Paper Trading – aktiveringsdiagnostikk" in text
    assert '"Ønsket status"' in text
    assert '"Effektiv status"' in text
    assert '"Kilde"' in text


def test_step_four_no_longer_depends_on_later_step_five():
    text = (ROOT / "drift_center.py").read_text(encoding="utf-8")
    block = text[text.index("if step == 4:"):text.index("if step == 5:")]
    assert "paper_storage_enabled" not in block
    assert "Kilde:" in block
