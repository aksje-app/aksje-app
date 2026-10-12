from super_portfolio import _entry_price_chase_gate, _position_from_row, SuperPortfolioConfig


def test_one_day_spike_blocks_new_entry():
    assert _entry_price_chase_gate({"return_1d": 7.5}) == ["ENTRY_CHASE_ONE_DAY"]


def test_five_day_spike_blocks_new_entry():
    assert _entry_price_chase_gate({"raw_candidate": {"return_5d": 16.0}}) == ["ENTRY_CHASE_FIVE_DAY"]


def test_normal_momentum_remains_eligible():
    assert _entry_price_chase_gate({"return_1d": 4.0, "return_5d": 10.0}) == []


def test_missing_momentum_not_misrepresented_as_spike():
    assert _entry_price_chase_gate({}) == []


def test_snapshot_price_is_labeled_not_a_fill():
    row = {"ticker": "TEST.ST", "price": 123.45, "price_timestamp": "2026-10-12T16:30:00+02:00"}
    pos = _position_from_row(row, 1.5, {}, "2026-10-12T16:35:00+02:00", SuperPortfolioConfig(), [])
    assert pos["entry_price"] == 123.45
    assert pos["entry_price_basis"] == "CANDIDATE_SNAPSHOT_NOT_EXECUTED_FILL"
    assert pos["entry_signal_price_timestamp"] == row["price_timestamp"]


def test_opening_gap_blocks_new_entry():
    from super_portfolio import _entry_opening_gap_gate
    assert _entry_opening_gap_gate({"session_open": 103, "previous_close": 100}) == ["ENTRY_OPEN_GAP_UP"]


def test_small_or_unknown_opening_gap_not_blocked():
    from super_portfolio import _entry_opening_gap_gate
    assert _entry_opening_gap_gate({"session_open": 101, "previous_close": 100}) == []
    assert _entry_opening_gap_gate({"price": 104}) == []


def test_entry_gate_checks_both_momentum_and_opening_gap():
    from super_portfolio import _entry_risk_reasons
    assert _entry_risk_reasons({"return_1d": 8, "session_open": 103, "previous_close": 100}) == [
        "ENTRY_CHASE_ONE_DAY", "ENTRY_OPEN_GAP_UP"
    ]


def test_next_session_cannot_use_same_day_snapshot():
    from datetime import datetime, timezone
    from super_portfolio import _verified_next_session_open
    pending = {}
    row = {"market": "SVERIGE", "ticker": "TEST.ST", "price": 120, "source": "Super Portfolio independent market universe"}
    reasons, fill = _verified_next_session_open(row, pending, datetime(2026, 10, 12, 12, tzinfo=timezone.utc))
    assert reasons == ["ENTRY_AWAIT_NEXT_SESSION"]
    assert fill == 0
    assert pending["entry_signal_price"] == 120


def test_next_session_without_verified_open_stays_pending():
    from datetime import datetime, timezone
    from super_portfolio import _verified_next_session_open
    pending = {"entry_signal_date": "2026-10-09"}
    reasons, fill = _verified_next_session_open(
        {"market": "SVERIGE", "price": 120, "source": "Super Portfolio independent market universe"},
        pending,
        datetime(2026, 10, 12, 12, tzinfo=timezone.utc),
    )
    assert "ENTRY_OPEN_QUOTE_UNVERIFIED" in reasons
    assert fill == 0


def test_next_session_valid_open_can_fill():
    from datetime import datetime, timezone
    from super_portfolio import _verified_next_session_open
    row = {"market": "SVERIGE", "session_open": 100, "previous_close": 99, "session_date": "2026-10-12", "source": "Super Portfolio independent market universe"}
    reasons, fill = _verified_next_session_open(
        row, {"entry_signal_date": "2026-10-09"}, datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
    )
    assert reasons == []
    assert fill == 100
