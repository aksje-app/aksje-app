from datetime import datetime, timezone
import pandas as pd
import pytest
from market_health_breadth_fallback import compute_sp500_breadth

def test_breadth_requires_genuine_200day_constituent_coverage():
    tickers=[f"S{i:03d}" for i in range(500)]
    csv_text="Symbol,Security\n"+"".join(f"{t},{t}\n" for t in tickers)
    dates=pd.date_range(end="2026-10-16", periods=210,freq="B")
    def history_provider(batch):
        data={t:[float(i + 1) for i in range(210)] for t in batch}
        return pd.concat({"Close": pd.DataFrame(data,index=dates)},axis=1)
    result=compute_sp500_breadth(constituents_csv=csv_text,history_provider=history_provider,now=datetime(2026,10,18,tzinfo=timezone.utc))
    assert result["value"]==100.
    assert "500/500" in result["source"]

def test_breadth_refuses_incomplete_series():
    tickers=[f"S{i:03d}" for i in range(500)]
    csv_text="Symbol,Security\n"+"".join(f"{t},{t}\n" for t in tickers)
    dates=pd.date_range(end="2026-10-16", periods=20,freq="B")
    def history_provider(batch):
        return pd.concat({"Close":pd.DataFrame({t:[1.]*20 for t in batch},index=dates)},axis=1)
    with pytest.raises(ValueError,match="Insufficient"):
        compute_sp500_breadth(constituents_csv=csv_text,history_provider=history_provider,now=datetime(2026,10,18,tzinfo=timezone.utc))
