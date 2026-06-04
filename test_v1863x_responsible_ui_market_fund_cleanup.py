from pathlib import Path
import py_compile

for name in [
    "app.py",
    "analysis_universe_ai.py",
    "fund_etf_analyzer.py",
    "app_version.py",
    "market_universe.py",
    "security_metadata.py",
]:
    py_compile.compile(name, doraise=True)

from app_version import APP_VERSION, get_app_patch_notes
from fund_etf_analyzer import (
    _clamp,
    default_fund_benchmark,
    fund_market_options,
    run_fund_etf_lab,
    select_fund_candidates,
)
from market_universe import BASE_MARKET_SCOPES, expand_market_scope, market_scope_options
from security_metadata import infer_security_listing, resolve_security_metadata


assert APP_VERSION.startswith("v18.6.24")
assert any("Finland" in note and "Brasil" in note for note in get_app_patch_notes())

assert BASE_MARKET_SCOPES == ["USA", "Norge", "Sverige", "Finland", "Danmark", "Brasil"]
assert expand_market_scope("Norden") == ["Norge", "Sverige", "Finland", "Danmark"]
assert "Brasil" in market_scope_options(include_aggregate=True)

fund_markets = fund_market_options()
for label in ["Norge", "Sverige", "Finland", "Danmark", "Brasil", "Norden", "Europa/UCITS"]:
    assert label in fund_markets

assert default_fund_benchmark("High yield-fond", "Norge") == "HYG"
assert default_fund_benchmark("ETF", "Brasil") == "EWZ"
assert _clamp(120) == 100
assert _clamp(-5) == 0

nordic_etfs = select_fund_candidates(source="Auto ETF", fund_type="ETF", market_scope="Norden", max_funds=12)
assert nordic_etfs["symbols"], nordic_etfs
assert any(symbol in nordic_etfs["symbols"] for symbol in ["NORW", "EWD", "EFNL", "EDEN"])
assert "SPY" not in nordic_etfs["symbols"]

brazil_etfs = select_fund_candidates(source="Auto ETF", fund_type="ETF", market_scope="Brasil", max_funds=8)
assert "EWZ" in brazil_etfs["symbols"]

result = run_fund_etf_lab(
    ["HYG", "JNK"],
    data_provider=lambda symbol: None,
    benchmark_provider=lambda symbol: None,
    fund_type="High yield-fond",
    test_mode="Rask",
)
assert result["summary"]["analyzed"] == 2
assert result["summary"]["errors"] == 0
assert result["ranked"][0]["datastatus"] in {"Mangler pris/NAV-historikk", "Pris/NAV funnet"}
assert result["ranked"][0]["data_quality_label"] in {"Lav", "Middels", "Hoy", "Høy"}

for ticker, country in [
    ("NOKIA.HE", "Finland"),
    ("NOVO-B.CO", "Danmark"),
    ("PETR4.SA", "Brasil"),
]:
    meta = resolve_security_metadata(ticker, {"ticker": ticker})
    listing = infer_security_listing(ticker, meta)
    assert listing.get("country") == country
    assert listing.get("market") == country
    assert meta.get("name") and meta.get("name") != ticker
    assert meta.get("sector") and meta.get("sector") not in {"Unknown", "Ukjent"}

app = Path("app.py").read_text(encoding="utf-8", errors="ignore")
analysis = Path("analysis_universe_ai.py").read_text(encoding="utf-8", errors="ignore")

assert 'LIVE_BANNER_MARKETS = ["USA", "Norge", "Sverige", "Finland", "Danmark", "Brasil"]' in app
assert "fund_lab_market_v1863x" in app
assert "auto_lab_fund_market_v1863x" in app
assert "Automatisk benchmark" in app
assert "manglende pris-/NAV-historikk" in app
assert "default_ticker = normalize_user_ticker(search or \"\")" in app
assert 'value=""' in Path("strategy_testing_workspace.py").read_text(encoding="utf-8", errors="ignore")

assert '"Selskap"' in analysis
assert '"Datakvalitet"' in analysis
assert '"Ikke analysert' in analysis
assert "Velg flere markeder uten nedtrekksmeny" in analysis




















