from superfund_ranking_digest import create_digest,pages

def test_rankings_are_grouped_deduplicated_and_bounded():
    rows=[
        {"id":"a","isin":"ONE","name":"Fund A","score":9,"category":"ETF","returns_currency":"EUR","returns":{"yield_1w":10,"yield_1m":5,"yield_3m":3}},
        {"id":"a2","isin":"ONE","name":"Fund A duplicate","score":8,"category":"ETF","returns_currency":"EUR"},
        {"id":"b","isin":"TWO","name":"Fund B","score":7,"category":"ETF","returns_currency":"USD"},
        {"id":"c","isin":"THREE","name":"Blocked fund","score":20,"category":"ETF","returns_currency":"EUR","blocks":["SPREAD"]},
    ]
    digest=create_digest(rows,at="2026-10-19T19:00:00+00:00")
    assert digest["qualified_count"]==2
    assert [r["id"] for r in digest["overall"]]==["a","b"]
    assert sorted(digest["groups"])==["ETF (EUR)","ETF (USD)"]
    msgs=pages(digest)
    assert msgs and all(len(x)<=900 for x in msgs)
    assert "Nyheter ikke verifisert" in "".join(msgs)
