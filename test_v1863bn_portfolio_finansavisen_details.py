import py_compile

from portfolio_mixed_analyzer import analyze_mixed_portfolio, build_holdings_from_sources


def test_portfolio_analyzer_clamps_score_with_shared_helper_signature():
    holdings = build_holdings_from_sources(
        stock_rows=[
            {"symbol": "DNB.OL", "asset_type": "Aksje", "weight_pct": 25, "source": "Paper trading"},
            {"symbol": "JNJ", "asset_type": "Aksje", "weight_pct": 25, "source": "Paper trading"},
            {"symbol": "NVDA", "asset_type": "Aksje", "weight_pct": 25, "source": "Paper trading"},
            {"symbol": "PRIO3.SA", "asset_type": "Aksje", "weight_pct": 25, "source": "Paper trading"},
        ]
    )
    result = analyze_mixed_portfolio(holdings, profile="Balansert")

    assert 0 <= result["portfolio_health"] <= 100
    assert result["grade"]
    assert len(result["holdings"]) == 4


def test_paper_trading_portfolio_ui_uses_full_portfolio_without_limit_slider():
    source = open("app.py", encoding="utf-8").read()

    assert "Paper trading analyseres komplett" in source
    assert "_paper_trading_holdings_v18544(limit=None)" in source
    assert "stock_rows_for_analysis = stock_rows if is_paper_source else stock_rows[: int(max_rows)]" in source
    assert "not is_paper_source and stock_rows" in source

    for module in ["app.py", "portfolio_mixed_analyzer.py", "finansavisen_bjellesau.py", "finansavisen_bjellesau_ui.py"]:
        py_compile.compile(module, doraise=True)

