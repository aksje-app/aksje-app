import quality_valuation_data as qd

class EmptyFrame:
    empty = True

class Fast(dict):
    pass

class FakeTicker:
    fast_info = Fast(lastPrice=123.4, currency="NOK")
    @property
    def info(self):
        raise RuntimeError("metadata blocked")
    @property
    def income_stmt(self):
        raise RuntimeError("statement blocked")
    @property
    def balance_sheet(self):
        raise RuntimeError("statement blocked")
    def history(self, **kwargs):
        return EmptyFrame()

class FakeYF:
    @staticmethod
    def Ticker(_ticker):
        return FakeTicker()

def test_snapshot_survives_optional_yahoo_metadata_failures(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "yfinance", FakeYF)
    row = qd.live_financial_snapshot("EQNR.OL")
    assert row["ticker"] == "EQNR.OL"
    assert row["price"] == 123.4
    assert row["currency"] == "NOK"
    assert row["annual_eps"] == []
    assert row["roce_history"] == []
