from datetime import datetime, timezone

from quality_valuation import evaluate_company, run_screen
from quality_valuation_store import preview_expired_run_keys
from quality_valuation_ui import build_screen_pdf
from quality_valuation_alerts import transition_messages


NOW = datetime(2026, 9, 25, tzinfo=timezone.utc)


def company(**changes):
    return {
        "ticker": "NHY.OL", "industry": "Aluminium", "country": "Norge",
        "price": 120, "trailing_eps": 20, "annual_eps": [20, 9, 10],
        "roce": 0.18, "roce_history": [0.18, 0.17, 0.19],
        "free_cash_flow": 100, "financial_date": "2025-12-31",
        **changes,
    }


def test_peak_earnings_reveals_normalized_multiple_and_unverified_proxy():
    result = evaluate_company(company(), assumed_pe=15, as_of=NOW)
    assert result["reported_pe"] == 6
    assert result["normalized_pe"] == 12
    assert result["entry_range_scenario"] == [135, 150]
    assert "Aluminium" in result["market_drivers"]
    assert any("Lav rapportert P/E" in warning for warning in result["warnings"])
    assert not result["verified_exposure"]


def test_missing_or_stale_evidence_cannot_become_attractive():
    for row in (company(annual_eps=[20]), company(financial_date="2020-12-31"),
                company(roce=None, roce_history=[]), company(free_cash_flow=None)):
        result = evaluate_company(row, assumed_pe=15, as_of=NOW)
        assert result["group"] == "Ufullstendig / krever vurdering"
        assert result["entry_range_scenario"] is None


def test_without_explicit_multiple_no_valuation_price_is_presented():
    result = evaluate_company(company(), as_of=NOW)
    assert result["fair_price_scenario"] is None
    assert result["entry_range_scenario"] is None


def test_negative_year_is_included_in_normalization():
    result = evaluate_company(company(annual_eps=[-30, 10, 12]), assumed_pe=15, as_of=NOW)
    assert result["normalized_eps"] == 10


def test_peer_valuation_requires_three_other_comparable_names():
    from quality_valuation import add_peer_context
    results = [evaluate_company(company(ticker=f"X{i}.OL", price=95 + i), as_of=NOW) for i in range(4)]
    add_peer_context(results)
    assert all(row.get("peer_count") == 3 for row in results)
    assert all(row.get("entry_range_scenario") for row in results)
    single = [evaluate_company(company(), as_of=NOW)]
    add_peer_context(single)
    assert single[0]["entry_range_scenario"] is None


def test_run_is_bounded_and_progress_counts_actual_completed_symbols():
    progress = []
    result = run_screen(["NHY.OL", "NHY.OL", "YAR.OL"], lambda ticker: company(ticker=ticker),
                        assumed_pe=15, progress=progress.append)
    assert result["selected"] == result["completed"] == 2
    assert [row["completed"] for row in progress] == [0, 1, 1, 2]
    assert result["shadow_only"] is True
    limited = run_screen(["NHY.OL", "YAR.OL"], lambda ticker: company(ticker=ticker),
                         memory_guard=lambda: False)
    assert limited["state"] == "PARTIAL" and limited["completed"] == 0


def test_inactive_and_unknown_markets_are_rejected_before_provider_call():
    for symbol in ("PETR4.SA", "ABC.F", "THIS IS INVALID"):
        try:
            run_screen(["NHY.OL", symbol], lambda ticker: (_ for _ in ()).throw(AssertionError("provider called")))
        except ValueError as exc:
            assert "marked" in str(exc)
        else:
            assert False, symbol
    assert run_screen(["NOVO-B.CO"], lambda ticker: company(ticker=ticker))["selected"] == 1


def test_retention_only_marks_own_expired_runs():
    now = datetime(2026, 9, 25, tzinfo=timezone.utc)
    names = ["quality_valuation/runs/20260301T120000000000", "quality_valuation/runs/20260924T120000000000",
             "quality_valuation/latest", "portfolio/positions", "quality_valuation/runs/unparseable"]
    assert preview_expired_run_keys(names, now=now) == names[:1]


def test_pdf_has_one_mobile_return_control_invisible_when_printed():
    from io import BytesIO
    from pypdf import PdfReader
    pdf = build_screen_pdf({"state": "COMPLETED", "generated_at": NOW.isoformat(), "groups": {"Kvalitetsselskap": [evaluate_company(company(), as_of=NOW)]}})
    assert pdf.startswith(b"%PDF")
    annotations = PdfReader(BytesIO(pdf)).pages[0]["/Annots"]
    assert len(annotations) == 2  # One visible label and its clickable link.
    assert all(int(item.get_object().get("/F", 0)) & 4 == 0 for item in annotations)
    assert "aa_nav=market" in str(annotations[1].get_object())


def test_quality_push_requires_verified_filings_and_change():
    first = run_screen(["NHY.OL"], lambda ticker: company(ticker=ticker), assumed_pe=15)
    assert transition_messages({}, first) == []
    candidate = first["groups"]["Attraktivt priset kandidat"][0]
    candidate.update(valuation_basis_verified=True, filings_verified=True, market_drivers_verified=True)
    first["state"] = "COMPLETED"
    assert [event["kind"] for event in transition_messages({}, first)] == ["NEW"]
    assert transition_messages(first, first) == []


def test_unverified_regional_gas_does_not_silently_use_us_natural_gas():
    import quality_valuation_data as data
    assert "Europeisk gass" not in data.PROXY_SYMBOLS
    assert data.observed_driver_prices(["Europeisk gass", "Aluminium"]) == {}


def test_live_provider_calculates_roce_from_three_financial_periods():
    import sys
    import types
    import pandas as pd
    from quality_valuation_data import live_financial_snapshot

    periods = pd.to_datetime(["2025-12-31", "2024-12-31", "2023-12-31"])
    annual = pd.DataFrame([[10, 9, -2], [20, 18, 10]], index=["Diluted EPS", "EBIT"], columns=periods)
    balance = pd.DataFrame([[150, 140, 130], [50, 50, 50]], index=["Total Assets", "Current Liabilities"], columns=periods)
    security = types.SimpleNamespace(info={"sector": "Materials", "industry": "Aluminium", "currentPrice": 120,
                                           "freeCashflow": 25, "trailingEps": 10}, income_stmt=annual, balance_sheet=balance)
    original = sys.modules.get("yfinance")
    sys.modules["yfinance"] = types.SimpleNamespace(Ticker=lambda ticker: security)
    try:
        result = live_financial_snapshot("NHY.OL")
    finally:
        if original is None:
            sys.modules.pop("yfinance", None)
        else:
            sys.modules["yfinance"] = original
    assert result["annual_eps"] == [10, 9, -2]
    assert result["roce_history"] == [0.2, 0.2, 0.125]
    assert result["financial_date"] == "2025-12-31"


def test_roce_does_not_pair_ebit_with_balance_from_another_year():
    import pandas as pd
    from quality_valuation_data import _dated_values

    annual = pd.DataFrame([[20, 30]], index=["EBIT"], columns=pd.to_datetime(["2025-12-31", "2023-12-31"]))
    balance = pd.DataFrame([[100, 100]], index=["Total Assets"], columns=pd.to_datetime(["2024-12-31", "2023-12-31"]))
    ebit = _dated_values(annual, ("EBIT",))
    assets = _dated_values(balance, ("Total Assets",))
    assert ebit.keys() & assets.keys() == {"2023-12-31"}
