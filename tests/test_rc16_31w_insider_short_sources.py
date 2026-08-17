from __future__ import annotations

from types import SimpleNamespace

import insider_intelligence as insider
import official_insider_sources as official
import short_data_sources as short_sources
from insider_transaction_semantics import transaction_type
from short_intelligence import normalize_short_snapshot


class Response:
    def __init__(self, *, text="", payload=None, url="https://source.test"):
        self.text = text; self.content = text.encode(); self._payload = payload; self.url = url
    def raise_for_status(self): return None
    def json(self): return self._payload


def test_swedish_insider_categories_are_not_discarded():
    assert transaction_type({"transaction": "Förvärv"}) == "BUY"
    assert transaction_type({"transaction": "Avyttring"}) == "SELL"


def test_fi_search_removes_legal_suffix(monkeypatch):
    captured = {}
    class Session:
        def get(self, url, **kwargs):
            captured.update(kwargs.get("params") or {})
            return Response(text="Publiceringsdatum;Emittent\n")
    result = official.fetch_sweden_fi("SSAB-A.ST", "SSAB AB (publ)", session=Session())
    assert result["status"] == "SUCCESS_NO_RESULTS"
    assert captured["Utgivare"] == "SSAB"


def test_duplicate_provider_and_primary_insider_trade_counts_once():
    common = {"date": "2026-08-01", "transaction": "Purchase", "insider": "A Person", "shares": 10, "price": 20}
    result = insider.score_transactions("TEST", [
        {**common, "source_type": "SECONDARY_STRUCTURED"},
        {**common, "source_type": "OFFICIAL_PRIMARY", "source_url": "https://official", "document_id": "1"},
    ])
    assert result["buy_count"] == 1
    assert result["primary_verified_fact_count"] == 1


def test_prearranged_single_sale_is_not_automatically_strongly_negative():
    result = insider.score_transactions("TEST", [{
        "date": "2026-08-01", "transaction": "Sale", "insider": "A Person",
        "shares": 10, "price": 20, "planned_10b5_1": True,
    }])
    assert result["score"] > 25
    assert result["signal"] != "STERKT NEGATIV"


def test_sweden_short_register_match_is_verified():
    html = """<table><tr><th>Emittent</th><th>LEI</th><th>Datum</th><th>Summa blankning %</th></tr>
    <tr><td>SSAB AB (publ)</td><td>LEI123</td><td>2026-08-16</td><td>3,28</td></tr></table>"""
    session = SimpleNamespace(get=lambda *args, **kwargs: Response(text=html))
    data = short_sources.fetch_sweden({"ticker": "SSAB-A.ST", "name": "SSAB AB"}, session=session)
    snap = normalize_short_snapshot({"ticker": "SSAB-A.ST", "market": "Sverige", "short_data": data})
    assert snap["verified"] is True
    assert snap["short_interest_pct_outstanding"] == 3.28


def test_no_public_norwegian_position_is_not_reported_as_zero():
    session = SimpleNamespace(get=lambda *args, **kwargs: Response(payload={"positions": []}))
    data = short_sources.fetch_norway({"ticker": "DNB.OL", "name": "DNB Bank ASA"}, session=session)
    snap = normalize_short_snapshot({"ticker": "DNB.OL", "market": "Norge", "short_data": data})
    assert snap["coverage"] == "CHECKED_NO_PUBLIC_POSITION"
    assert snap["short_interest_pct_outstanding"] is None
    assert snap["public_threshold_pct"] == 0.5


def test_report_ui_prioritises_full_pdf_and_explains_zip():
    source = open("market_intelligence.py", encoding="utf-8").read()
    assert "📘 Last ned full rapport med vedlegg" in source
    assert "📄 Last ned kort rapport (3 sider)" in source
    assert "Bygg ZIP med PDF, JSON, tekst og revisjon" in source
