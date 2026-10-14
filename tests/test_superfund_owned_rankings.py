import pytest
from superfund_owned_rankings import owned_rankings

def test_current_scores_recomputed_not_frozen():
    s={"model":{"positions":{"a":{"name":"Fund A","quantity":1,"last_nok":110,"cost_nok":100,"score_at_buy":99},
                              "b":{"name":"Fund B","quantity":1,"last_nok":90,"cost_nok":100,"score_at_buy":-50}}},
       "candidates":[{"id":"a","returns":{"yield_1w":1,"yield_1m":2,"yield_3m":4},"price_at":"2026-10-14T00:00:00Z"},
                     {"id":"b","returns":{"yield_1w":3,"yield_1m":2,"yield_3m":4},"price_at":"2026-10-14T00:00:00Z"}]}
    result={x["id"]:x for x in owned_rankings(s)}
    assert result["a"]["score_now"]==pytest.approx(1.7)
    assert result["b"]["score_now"]==pytest.approx(2.9)
    assert result["b"]["owned_rank"]==1
    assert result["a"]["return_pct"]==pytest.approx(10)
    assert result["a"]["score_at_buy"]==99

def test_missing_quotes_do_not_inherit_purchase_score():
    s={"model":{"positions":{"a":{"name":"A","quantity":1,"last_nok":100,"cost_nok":100,"score_at_buy":5}}},
       "candidates":[{"id":"a","returns":{"yield_1w":2}}]}
    row=owned_rankings(s)[0]
    assert row["score_now"] is None
    assert row["owned_rank"] is None
    assert not row["score_available"]
