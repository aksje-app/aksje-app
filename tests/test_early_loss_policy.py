import pytest
from early_loss_policy import early_loss_review

BASE=dict(entry_at="2026-10-12T12:00:00Z",observed_at="2026-10-13T12:00:00Z",
          entry_price=100,current_price=99,trading_sessions_since_entry=1,
          data_fresh=True,enabled=True)

def test_disabled_by_default_and_no_order_authority():
    r=early_loss_review(**{**BASE,"enabled":False})
    assert r["action"]=="ORDINARY_STOP_RULES"
    assert not r["execution_authorized"]

@pytest.mark.parametrize("loss,expected",[
    (99.5,"BEHOLD"),(99.0,"OVERVAAK"),
    (98.5,"OVERVAAK"),(98.0,"SELG"),(97.0,"SELG")])
def test_first_five_sessions_loss_thresholds(loss,expected):
    r=early_loss_review(**{**BASE,"current_price":loss})
    assert r["action"]==expected
    assert r["execution_authorized"] is False

def test_confirmed_thesis_failure_at_one_point_five_percent():
    r=early_loss_review(**{**BASE,"current_price":98.5,
        "thesis_valid":False,"score_change":-4})
    assert r["action"]=="SELG"
    assert r["reason_codes"]==["EARLY_CONFIRMED_THESIS_FAILURE"]

def test_loss_without_confirmed_thesis_failure_stays_under_review():
    r=early_loss_review(**{**BASE,"current_price":98.5,"thesis_valid":None})
    assert r["action"]=="OVERVAAK"

def test_existing_position_after_five_sessions_uses_ordinary_rules():
    r=early_loss_review(**{**BASE,"current_price":97,"trading_sessions_since_entry":5})
    assert r["action"]=="ORDINARY_STOP_RULES"
    assert not r["early_policy_applied"]

@pytest.mark.parametrize("change",[
    {"entry_at":None},{"observed_at":"2026-10-10T00:00:00Z"},
    {"data_fresh":False},{"trading_sessions_since_entry":None},
    {"current_price":None}])
def test_missing_or_stale_evidence_cannot_authorize_sale(change):
    r=early_loss_review(**{**BASE,**change})
    assert r["action"]=="OVERVAAK"
    assert not r["execution_authorized"]


def test_all_engine_early_loss_adapters_are_advisory():
    from super_portfolio import preview_early_loss_super_portfolio
    from autonomous_portfolio import preview_early_loss_autonomi
    from superfund_engine import preview_early_loss_superfund
    evidence={"observed_at":"2026-10-13T12:00:00Z","current_price":98,
              "current_nok":98,"data_fresh":True,
              "evaluated_at":"2026-10-13T12:15:00Z",
              "provider_confirmed":True,"session_count_verified":True,
              "trading_sessions_since_entry":1,"early_loss_preview_enabled":True}
    results=[
        preview_early_loss_super_portfolio(
            {"entry_date":"2026-10-12T12:00:00Z","entry_price":100},evidence),
        preview_early_loss_autonomi(
            {"opened_at":"2026-10-12T12:00:00Z","average_price":100},evidence),
        preview_early_loss_superfund(
            {"bought_at":"2026-10-12T12:00:00Z","entry_nok":100},evidence),
    ]
    assert all(r["action"]=="SELG" for r in results)
    assert all(r["execution_authorized"] is False for r in results)
    assert preview_early_loss_superfund({"entry_nok":100},evidence)["action"]=="OVERVAAK"


def test_observation_verification_blocks_unknown_provider_and_old_quote():
    from early_loss_policy import validate_observation
    baseline=dict(observed_at="2026-10-13T12:00:00Z",
                  evaluated_at="2026-10-13T12:10:00Z",
                  provider_confirmed=True,session_count_verified=True)
    assert validate_observation(**baseline)["verified"]
    assert not validate_observation(**{**baseline,"provider_confirmed":False})["verified"]
    assert not validate_observation(**{**baseline,"evaluated_at":"2026-10-13T14:00:00Z"})["verified"]
    assert not validate_observation(**{**baseline,"session_count_verified":False})["verified"]


def test_superfund_uses_stored_purchase_date():
    from superfund_engine import preview_early_loss_superfund
    evidence={"observed_at":"2026-10-13T12:00:00Z",
              "evaluated_at":"2026-10-13T12:05:00Z",
              "provider_confirmed":True,"session_count_verified":True,
              "trading_sessions_since_entry":1,"current_nok":98.0,
              "early_loss_preview_enabled":True}
    result=preview_early_loss_superfund(
        {"bought_at":"2026-10-12T12:00:00Z","entry_nok":100.0},evidence)
    assert result["action"]=="SELG"
    assert result["execution_authorized"] is False
