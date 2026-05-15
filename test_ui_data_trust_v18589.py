from datetime import datetime, timedelta

from ui_trust import normalize_data_trust, format_data_trust_line, explain_blocked_action, ui_consistency_tokens


def test_data_trust_fallback_and_missing():
    status = normalize_data_trust({"fallback_used": True, "missing_fields": ["macro", "news"], "confidence": 41})
    assert status["level"] == "FALLBACK"
    assert status["confidence"] == 41
    assert status["warnings"]


def test_data_trust_stale_timestamp():
    ts = (datetime.now() - timedelta(minutes=95)).isoformat(timespec="seconds")
    status = normalize_data_trust({"updated_at": ts}, stale_after_minutes=60)
    assert status["level"] == "STALE"
    assert status["age_minutes"] >= 90


def test_blocked_action_explanation():
    msg = explain_blocked_action(["Ikke nok cash", "Confidence for lav"], action="Kjøp")
    assert msg.startswith("Kjøp blokkert")
    assert "Ikke nok cash" in msg
    assert "Confidence" in msg


def test_ui_tokens_are_stable():
    tokens = ui_consistency_tokens()
    assert tokens["button_height_px"] >= 36
    assert "blocked" in tokens["button_states"]


def test_format_data_trust_line_contains_label():
    line = format_data_trust_line({"data_quality": "PARTIAL", "confidence": 55})
    assert "Delvis" in line
    assert "55" in line
