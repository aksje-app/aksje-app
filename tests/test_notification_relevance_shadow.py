from notification_relevance_shadow import classify, summarize
from superfund_presentation import notification_batch

def test_critical_alert_is_never_filtered():
    assert classify({"side":"SHADOW SELL","id":"DNO.OL"})["bucket"]=="critical"

def test_fast_climb_with_positive_trend_is_interesting():
    result=classify({"side":"STERK UKEUTVIKLING","challenger":{"rank":5,"rank_gain":11},"short_trend":{"last_1_sessions_pct":1.2}})
    assert result["bucket"]=="interesting"

def test_weak_midrank_alert_goes_to_daily_shadow_bucket():
    result=classify({"side":"STERK UKEUTVIKLING","challenger":{"rank":17,"rank_gain":None},"short_trend":{"last_1_sessions_pct":-0.65}})
    assert result["bucket"]=="daily"

def test_superfund_alert_shows_rank_movement_and_no_fake_comparison():
    e={"id":"x","name":"Testfond","side":"STERK UKEUTVIKLING",
       "returns":{"yield_1w":3.3},"returns_currency":"EUR",
       "challenger":{"rank":17,"total":28,"rank_gain":11,"same_group_held":0,"outperforms_held":0}}
    message,count=notification_batch([e])
    assert count==1
    assert "28 → 17" in message
    assert "Ingen direkte sammenlignbare" in message
    assert "bedre enn 0 av 0" not in message

def test_shadow_summary_never_blocks():
    x=summarize([{"side":"SHADOW SELL","id":"a"},{"side":"STERK UKEUTVIKLING","id":"b"}])
    assert x["shadow_only"] is True
    assert len(x["rows"])==2
