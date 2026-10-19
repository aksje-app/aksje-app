from superfund_nav_backfill import resolve_fund
def test_reject_unverified_quotes():
    assert resolve_fund("LU0154236417",[{"symbol":"FOO","quoteType":"MUTUALFUND"}])["status"]=="UNVERIFIED"
def test_exact_isin():
    assert resolve_fund("LU0154236417",[{"isin":"LU0154236417","symbol":"FOO","quoteType":"MUTUALFUND"}])["symbol"]=="FOO"
