from tools.audit_alert_chain_rc16_31cg import audit


def test_every_pushover_producer_uses_the_single_sanitized_sender():
    result = audit()
    assert result["ok"], result["errors"]
    assert result["producer_count"] >= 15
    assert result["central_http_calls"]
    assert {row["file"] for row in result["central_http_calls"]} == {"notifier.py"}
    assert all(result["contracts"].values())
