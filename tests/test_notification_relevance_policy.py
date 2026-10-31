from notification_relevance_policy import classify


def test_currency_exempt():
    assert classify({'category': 'currency'}) == 'exempt'


def test_candidates_not_pushed():
    assert classify({'category': 'candidate', 'rank': 1}) == 'in_app'


def test_unverified_buy_not_pushed():
    assert classify({'category': 'buy_signal', 'ticker': 'ABC'}) == 'in_app'


def test_verified_actionable_buy():
    assert classify({'category': 'buy_signal', 'ticker': 'ABC', 'signal_id': 'abc-1', 'verified': True, 'requires_action': True, 'threshold_met': True}) == 'send'


def test_unknown_sender_not_silently_blocked():
    assert classify({'category': 'unknown'}) == 'legacy'


def test_verified_sell_signal():
    assert classify({'category': 'sell_signal', 'ticker': 'XYZ', 'signal_id': 'sell-1', 'verified': True, 'requires_action': True, 'threshold_met': True}) == 'send'


def test_missing_signal_id_stays_in_app():
    assert classify({'category': 'buy_signal', 'ticker': 'XYZ', 'verified': True, 'requires_action': True, 'threshold_met': True}) == 'in_app'


def test_notifier_opt_in_contract_static():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "notifier.py").read_text()
    assert "relevance_event=None" in source
    assert 'if relevance_event is not None:' in source
    assert 'if decision == "in_app":' in source


def test_currency_sender_not_migrated_static():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "currency_alert_service.py").read_text()
    assert "send_pushover_alert" in source
    assert "relevance_event=" not in source


def test_fresh_trend_batches_and_observations_suppressed_static():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "fresh_trend_monitor.py").read_text()
    assert 'relevance_event={"category": "routine"}' in source
    assert 'relevance_event={"category": "observation"} if int(event.get("priority_level") or 4) > 2 else None' in source


def test_critical_alerts_preserved():
    assert classify({'category': 'critical'}) == 'legacy'


def test_trade_receipts_preserved():
    assert classify({'category': 'trade_execution'}) == 'legacy'


def test_signal_requires_all_guards():
    base = {'category': 'buy_signal', 'ticker': 'DNO', 'signal_id': '1', 'verified': True, 'requires_action': True, 'threshold_met': True}
    for field in ('verified', 'requires_action', 'threshold_met'):
        event = dict(base)
        event[field] = False
        assert classify(event) == 'in_app'


def test_learning_reports_are_in_app_only_static():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / 'learning_observation_engine.py').read_text()
    assert source.count('relevance_event={"category": "routine"}') >= 2
