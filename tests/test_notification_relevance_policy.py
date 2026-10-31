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
