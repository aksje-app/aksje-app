from superfund_portfolio_overview import portfolio_rows

def test_portfolio_weights_include_cash_and_per_fund_pnl():
    s={"model":{"cash":50000,"positions":{"a":{"id":"a","name":"Brazil ETF","quantity":10,"last_nok":100,"cost_nok":1200,"category":"Latin America Equity","investment_area":"Brasil"}}}}
    equity,rows=portfolio_rows(s)
    assert equity==51000
    assert len(rows)==1
    assert rows[0]["value_nok"]==1000
    assert rows[0]["weight_pct"]==1000/51000*100
    assert rows[0]["pnl_nok"]==-200
    assert rows[0]["pnl_pct"]==-200/1200*100
    assert rows[0]["country"]=="Brasil"

def test_no_invented_sector_when_unknown():
    equity,rows=portfolio_rows({"model":{"cash":0,"positions":{"b":{"name":"Unclassified","quantity":1,"last_nok":20,"cost_nok":20}}}})
    assert equity==20
    assert rows[0]["sector"]=="Ukjent kategori"
