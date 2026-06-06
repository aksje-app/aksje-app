from __future__ import annotations

import datetime as dt
from pathlib import Path
import py_compile


ROOT = Path(__file__).resolve().parent


def test_v1864y_fmp_live_source_contract(monkeypatch):
    py_compile.compile(str(ROOT / "fmp_signals.py"), doraise=True)

    import fmp_signals

    monkeypatch.setenv("FMP_API_KEY", "test_fmp_key")
    today = dt.date.today().isoformat()

    def fake_request(endpoint, params=None):
        if endpoint == "grades-consensus":
            return [{"strongBuy": 2, "buy": 4, "hold": 1, "sell": 0, "strongSell": 0}]
        if endpoint == "price-target-consensus":
            return [{"targetConsensus": 130}]
        if endpoint == "quote":
            return [{"price": 100}]
        if endpoint == "analyst-estimates":
            return [{"date": "2026", "estimatedEpsAvg": 5.2, "estimatedRevenueAvg": 1200000000, "numberAnalystsEstimatedEps": 8}]
        if endpoint == "grades":
            return [{"publishedDate": today, "action": "upgrade", "newGrade": "Buy", "previousGrade": "Hold"}]
        if endpoint == "earnings":
            return [{"date": today, "epsEstimated": 1.0, "epsActual": 1.25}]
        if endpoint == "insider-trading/search":
            return [{
                "transactionDate": today,
                "acquisitionOrDisposition": "A",
                "securitiesTransacted": 5000,
                "price": 20,
                "reportingName": "Primary Insider",
            }]
        if endpoint == "actively-trading-list":
            return [
                {"symbol": "EQNR.OL", "exchange": "Oslo Stock Exchange", "country": "Norway"},
                {"symbol": "VOLV-B.ST", "exchange": "Nasdaq Stockholm", "country": "Sweden"},
                {"symbol": "AAPL", "exchangeShortName": "NASDAQ", "country": "US"},
            ]
        return []

    monkeypatch.setattr(fmp_signals, "_request_json", fake_request)

    packet = fmp_signals.fetch_fmp_signal_packet("EQNR.OL")
    assert packet["enabled"] is True
    assert packet["hits"] == 3
    assert packet["analyst"]["score"] > 6
    assert "Price target" in packet["analyst"]["detail"]
    assert packet["earnings"]["epsSurprisePct"] == 25.0
    assert packet["insider"]["buy_count"] == 1
    assert packet["insider"]["score"] > 6

    nordic = fmp_signals.fmp_candidate_tickers("Norden", limit=5)
    assert nordic == ["EQNR.OL", "VOLV-B.ST"]

