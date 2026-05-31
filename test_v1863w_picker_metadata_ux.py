from pathlib import Path

from security_metadata import infer_security_listing, resolve_security_metadata
from stocks import BRAZILIAN_STOCKS, DANISH_STOCKS, FINNISH_STOCKS, NORWEGIAN_STOCKS, SWEDISH_STOCKS


analysis = Path("analysis_universe_ai.py").read_text(encoding="utf-8", errors="ignore")
security = Path("security_metadata.py").read_text(encoding="utf-8", errors="ignore")
layout = Path("workspace_layout.py").read_text(encoding="utf-8", errors="ignore")

assert "ai_universe_market_single_v1863w" in analysis
assert "ai_universe_market_chip_" in analysis
assert 'scopes = st.multiselect(' not in analysis
assert 'sectors = st.multiselect(' not in analysis
assert 'APP_SECURITY_METADATA_VERSION = "v18.6.3w"' in security
assert 'render_forecast_section(default_ticker="")' in layout

for ticker in ["UPM.HE", "WRT1V.HE", "VWS.CO", "BBDC4.SA", "TEL.OL", "HM-B.ST"]:
    meta = resolve_security_metadata(ticker, {"ticker": ticker})
    assert meta["name"] != ticker
    assert meta["sector"] not in {"", "Unknown", "Ukjent"}
    assert meta["risk"] not in {"", "Unknown", "Ukjent"}

for ticker in NORWEGIAN_STOCKS + SWEDISH_STOCKS + FINNISH_STOCKS + DANISH_STOCKS + BRAZILIAN_STOCKS:
    meta = resolve_security_metadata(ticker, {"ticker": ticker})
    assert meta["sector"] not in {"", "Unknown", "Ukjent"}, ticker
    assert meta["risk"] not in {"", "Unknown", "Ukjent"}, ticker

assert infer_security_listing("UPM.HE")["market"] == "Finland"
assert infer_security_listing("NOVO-B.CO")["market"] == "Danmark"
assert infer_security_listing("PETR4.SA")["market"] == "Brasil"







