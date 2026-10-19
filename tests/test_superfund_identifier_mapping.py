from superfund_identifier_mapping import resolve_mapping
def test_mapping_rejects_mutual_fund_and_ambiguity():
    isin="IE00B4L5Y983"
    assert resolve_mapping(isin,[{"ticker":"ABC","exchCode":"US","securityType2":"Common Stock"}])["status"]=="UNRESOLVED"
    assert resolve_mapping(isin,[{"ticker":"AAA","exchCode":"US","securityType2":"ETF"},{"ticker":"AAA","exchCode":"LN","securityType2":"ETF"}])["status"]=="AMBIGUOUS"
def test_mapping_accepts_explicit_venue():
    x=resolve_mapping("IE00B4L5Y983",[{"ticker":"ABC","exchCode":"LN","marketSector":"Equity","securityType2":"ETF"}])
    assert x["status"]=="MAPPED" and x["symbol"]=="ABC.L"
