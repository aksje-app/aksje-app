import io
import json
import zipfile
from trade_forensics import classify_exit, diagnostic_manifest, error_evidence


def test_nohal_trigger_gap_is_reported_not_silently_passed():
    row = {"id": 238, "type": "SELL", "ticker": "NOHAL.OL", "price": 28.2, "rule_used": "Maks 3% trailing stop", "rule_limit": "28.91", "pnl_pct": -5.37}
    finding = classify_exit(row)
    assert "EXECUTION_BELOW_TRIGGER" in finding["findings"]
    assert "EXECUTION_QUOTE_NOT_RECORDED" in finding["findings"]
    assert finding["status"] == "REVIEW_REQUIRED"


def test_lly_profit_protection_must_show_realized_loss_and_price_gap():
    row = {"type": "SELL", "ticker": "LLY", "price": 1134.38, "pnl_pct": -2.88, "rule_used": "Profit protection", "rule_limit": "1179.70",
           "evidence_metadata": {"entry_price": 1168, "peak_gain_pct": 2.5, "stop_trigger_price": 1179.7, "market_data_at": "2026-10-08T15:45:00+00:00", "execution_quote": {"price": 1134.375}}}
    finding = classify_exit(row)
    assert "PROFIT_PROTECTION_REALIZED_LOSS" in finding["findings"]
    assert "EXECUTION_BELOW_TRIGGER" in finding["findings"]
    assert "EXECUTION_QUOTE_NOT_RECORDED" not in finding["findings"]


def test_valid_profit_protection_is_not_marked_as_loss():
    row = {"type": "SELL", "ticker": "X", "price": 105, "pnl_pct": 5, "rule_used": "Profit protection", "rule_limit": "103",
           "evidence_metadata": {"market_data_at": "2026-10-08", "execution_quote": {"price": 105}}}
    assert "PROFIT_PROTECTION_REALIZED_LOSS" not in classify_exit(row)["findings"]


def test_manifest_records_real_bytes_and_errors():
    payload = json.dumps(error_evidence([{"at": "2026-10-16", "error_code": "RATE_LIMIT", "error": "429"}])).encode()
    manifest = diagnostic_manifest({"errors.json": payload})
    assert manifest["files"][0]["bytes"] == len(payload)
    assert manifest["strategy_validated"] is False
    with io.BytesIO() as buffer:
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr("errors.json", payload)
            z.writestr("manifest.json", json.dumps(manifest))
        with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as z:
            assert z.testzip() is None
            assert json.loads(z.read("errors.json"))[0]["error_code"] == "RATE_LIMIT"
