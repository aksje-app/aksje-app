from datetime import datetime, timezone, timedelta
from io import BytesIO
from types import SimpleNamespace
from copy import deepcopy
import json
import pandas as pd
import pytest
from pypdf import PdfReader

from quality_valuation import evaluate_company
from quality_turnaround import evaluate_turnaround, reserve_watch_slots
from quality_turnaround_shadow import advance, summary

NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)
RUN = "quality_valuation/runs/20261010T123456123456"


def financial(**changes):
    return {"ticker": "NRC.OL", "price": 9.7, "annual_eps": [.14, -10.54, .51, -4.35],
            "financial_date": "2025-12-31", "roce_history": [.055, -.335, .039, -.073],
            "roce": .055, "free_cash_flow_history": [183, -18, 341, 188],
            "industry": "Railroad infrastructure", "currency": "NOK", **changes}


@pytest.mark.parametrize("eps", [[-1, -2, -3], [0, 0, 0], [.14, -10.54, .51, -4.35]])
@pytest.mark.parametrize("industry", ["Industrials", "Railroad infrastructure", "Oil shipping", "Bank"])
def test_complete_negative_or_zero_history_is_weak_not_missing(eps, industry):
    row = evaluate_company(financial(annual_eps=eps, industry=industry, roe_history=[.12, .13, .14]), as_of=NOW)
    assert row["evidence_ready"] and row["data_status"] == "COMPLETE_FOR_MODEL"
    assert row["review_reason_category"] == "NONPOSITIVE_HISTORICAL_EARNINGS"
    assert row["missing_data_checks"] == []
    assert row["quality_state"] == "WEAK"
    assert row["data_score"] >= 3 and not row["quality_evidence_ready"]
    assert row["fair_price_scenario"] is None and row["normalized_pe"] is None


@pytest.mark.parametrize("changes,check", [
    ({"annual_eps": [0, -1]}, "THREE_ANNUAL_EPS_PERIODS"),
    ({"roce_history": [0]}, "THREE_ROCE_PERIODS"),
    ({"financial_date": "2020-12-31"}, "FINANCIAL_DATE_MISSING_OR_STALE"),
    ({"price": None}, "PRICE"),
    ({"free_cash_flow_history": [], "free_cash_flow": None}, "FREE_CASH_FLOW"),
])
def test_real_gaps_are_named_and_not_called_weak(changes, check):
    row = evaluate_company(financial(**changes), as_of=NOW)
    assert check in row["missing_data_checks"]
    assert row["review_reason_category"] == "MISSING_DATA"
    assert row["overall_grade_label"] == "Ufullstendig grunnlag"


def interim(**changes):
    return {"interim_observed_at": "2026-08-20T00:00:00+00:00", "interim_source": "provider",
            "interim_periods": [
                {"period_end": "2026-06-30", "duration_months": 3, "revenue": 110, "operating_income": 11, "fcf": 4},
                {"period_end": "2025-06-30", "duration_months": 3, "revenue": 100, "operating_income": -2, "fcf": -3},
            ], **changes}


def test_newer_improvement_coexists_with_weak_long_term_quality():
    row = evaluate_company({**financial(), **interim()}, as_of=NOW)
    assert row["quality_state"] == "WEAK" and not row["quality_evidence_ready"]
    signal = row["turnaround"]
    assert signal["status"] == "POSSIBLE_TURNAROUND"
    assert signal["operating_margin_delta_pp"] == pytest.approx(12)
    assert signal["metrics"]["operating_income"]["growth_pct"] is None  # no bogus % from negative base
    assert signal["metrics"]["fcf"]["delta"] == 7
    assert signal["primary_filing_status"] == "NOT_VERIFIED"
    assert signal["price_evidence"] == signal["event_evidence"] == "NOT_AVAILABLE"
    assert not signal["production_effect"]


def test_future_observation_and_future_publication_are_not_backdated_to_fiscal_end():
    assert evaluate_turnaround(interim(), as_of=datetime(2026, 7, 1, tzinfo=timezone.utc))["financial_improvement"] is False
    raw = interim()
    raw["interim_periods"][0]["published_at"] = "2026-11-01"
    assert not evaluate_turnaround(raw, as_of=NOW)["financial_improvement"]
    raw["interim_observed_at"] = "2026-12-01"
    assert "POINT_IN_TIME_INTERIM_AVAILABILITY" in evaluate_turnaround(raw, as_of=NOW)["missing"]


def test_mismatched_duration_or_season_and_stale_interim_cannot_confirm():
    for field, value in (("duration_months", 6), ("period_end", "2025-03-31")):
        raw = interim()
        raw["interim_periods"][1][field] = value
        assert "COMPARABLE_PRIOR_YEAR_PERIOD" in evaluate_turnaround(raw, as_of=NOW)["missing"]
    raw = interim(interim_observed_at="2027-04-01")
    result = evaluate_turnaround(raw, as_of=datetime(2027, 4, 1, tzinfo=timezone.utc))
    assert not result["financial_improvement"] and "FRESH_INTERIM_STATEMENTS" in result["missing"]


def test_seasonal_revenue_growth_without_margin_improvement_is_not_turnaround():
    raw = interim()
    raw["interim_periods"][1]["operating_income"] = 15
    assert evaluate_turnaround(raw, as_of=NOW)["status"] == "NO_IMPROVEMENT"


def test_quarterly_provider_keeps_period_identity_missing_values_and_real_fcf_sign():
    from quality_valuation_data import interim_financial_periods
    columns = pd.to_datetime(["2026-06-30", "2025-06-30"])
    income = pd.DataFrame([[110, 100], [11, -2], [float("nan"), -1]], index=["Total Revenue", "Operating Income", "Diluted EPS"], columns=columns)
    cash = pd.DataFrame([[10, 5], [3, -4]], index=["Operating Cash Flow", "Capital Expenditure"], columns=columns)
    periods = interim_financial_periods(SimpleNamespace(quarterly_income_stmt=income, quarterly_cashflow=cash), [])
    assert periods[0]["eps"] is None
    assert periods[0]["fcf"] == 7 and periods[1]["fcf"] == 1
    assert periods[0]["period_end"] == "2026-06-30"
    assert "published_at" not in periods[0]


def test_below_finalist_cut_watch_and_official_event_get_analysis_without_new_buy_signal():
    ranked = [{"ticker": f"X{i}.OL"} for i in range(25)]
    ranked[-1].update(earnings_growth=10, momentum_score=80, trend_score=70)
    selected, watch = reserve_watch_slots(ranked, 15, ["X23.OL"])
    assert len(selected) == 15 and {"X23.OL", "X24.OL"} <= set(watch)
    assert not any(row.get("buy_signal") for row in selected)
    assert len({row["ticker"] for row in selected}) == 15


def screen(now, prices=None, complete=True):
    prices = prices or {"NRC.OL": 10, "BASE.OL": 10}
    rows = [{"ticker": t, "price": p, "currency": "NOK", "observed_at": now.isoformat(),
             "quality_evidence_ready": t == "BASE.OL", "turnaround": {"financial_improvement": t == "NRC.OL", "observed_at": now.isoformat()}}
            for t, p in prices.items()]
    return {"state": "COMPLETED" if complete else "PARTIAL", "generated_at": now.isoformat(), "run_key": RUN,
            "groups": {"test": rows}}


def test_forward_shadow_frozen_baskets_same_capital_costs_and_sampled_drawdown():
    start = screen(NOW)
    state = advance({}, start)
    assert len(state["cohorts"]) == 1
    before = deepcopy(state)
    assert advance(state, start) == state  # idempotent
    falling = advance(state, screen(NOW + timedelta(days=10), {"NRC.OL": 8, "BASE.OL": 10}))
    assert state == before  # pure; no mutation of previous immutable evidence
    cohort = falling["cohorts"][0]
    assert cohort["watch"]["max_drawdown_pct"] > 20
    assert cohort["baseline"]["net_value"] < 100  # entry + hypothetical exit costs
    done = advance(falling, screen(NOW + timedelta(days=31), {"NRC.OL": 11, "BASE.OL": 10.5}))
    result = done["cohorts"][0]
    assert result["closed_at"] and result["excess_return_pp"] == pytest.approx(4.990005)
    assert result["false_positive_count"] == 0
    assert summary(done)["completed_cohorts"] == 1
    assert summary(done)["by_currency"]["NOK"]["completed"] == 1


def test_shadow_missing_quote_partial_or_future_data_does_not_fake_completion():
    state = advance({}, screen(NOW))
    assert advance(state, screen(NOW + timedelta(days=31), complete=False)) == state
    missing = advance(state, screen(NOW + timedelta(days=31), {"BASE.OL": 10}))
    assert not missing["cohorts"][0].get("closed_at")
    assert missing["cohorts"][0]["watch"]["missing_prices"] == ["NRC.OL"]
    future = screen(NOW)
    future["groups"]["test"][0]["turnaround"]["observed_at"] = (NOW + timedelta(days=1)).isoformat()
    assert advance({}, future)["cohorts"] == []


def test_tracked_stock_is_priced_after_leaving_finalists_but_not_replaced():
    state = advance({}, screen(NOW))
    later = screen(NOW + timedelta(days=31), {"BASE.OL": 10})
    later["turnaround_shadow_prices"] = {"NRC.OL": {"price": 9, "currency": "NOK", "observed_at": later["generated_at"], "latest_trade_date": "2026-11-09"}}
    done = advance(state, later)
    assert done["cohorts"][0]["closed_at"]
    assert set(done["cohorts"][0]["watch"]["positions"]) == {"NRC.OL"}
    assert done["cohorts"][0]["false_positive_count"] == 1


def test_scheduled_reused_quote_is_available_before_screen_completion(monkeypatch):
    from contextlib import contextmanager
    import quality_valuation_schedule as schedule
    import quality_turnaround_shadow as shadow
    state = advance({}, screen(NOW))
    later = NOW + timedelta(days=31)
    clock = {"time": later}

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["time"]

    @contextmanager
    def acquired():
        yield True

    monkeypatch.setattr(shadow, "datetime", Clock)
    monkeypatch.setattr("services.storage_service.get_storage_service", lambda: SimpleNamespace(read_json=lambda *a: state))
    monkeypatch.setattr(schedule, "scheduled_slot", lambda now: "test-slot")
    monkeypatch.setattr(schedule, "_latest_market_run", lambda: {})
    monkeypatch.setattr(schedule, "_scheduled_markets", lambda: ["NORGE"])
    monkeypatch.setattr(schedule, "_full_universe", lambda markets: ["NRC.OL", "BASE.OL"])
    monkeypatch.setattr(schedule, "_holding_symbols", lambda latest: [])
    monkeypatch.setattr(schedule, "_publish_pdf", lambda result: None)
    monkeypatch.setattr("quality_valuation_store.load_latest", lambda: {})
    monkeypatch.setattr("quality_valuation_control.single_manual_screen", acquired)
    monkeypatch.setattr("quality_valuation_ui.required_report_busy", lambda: False)
    monkeypatch.setattr("quality_valuation_data.memory_budget_ok", lambda: True)
    monkeypatch.setattr("quality_filing_discovery.refresh", lambda **kw: {})
    monkeypatch.setattr("quality_valuation_alerts.transition_messages", lambda *a: [])
    monkeypatch.setattr("quality_market_prescreen.full_market_prescreen", lambda *a, **kw: {
        "finalists": ["BASE.OL"], "rows": [{"ticker": "NRC.OL", "last_price": 9, "currency": "NOK", "latest_trade_date": later.date().isoformat()}]})

    def finish_screen(*args, **kwargs):
        clock["time"] = later + timedelta(seconds=1)
        return screen(clock["time"], {"BASE.OL": 10})

    saved = []
    monkeypatch.setattr("quality_valuation.run_screen", finish_screen)
    monkeypatch.setattr("quality_valuation_store.persist_screen", lambda result: saved.append(deepcopy(result)) or RUN)
    assert schedule.run_due_scheduled_screen(now=later)["state"] == "COMPLETED"
    completed = advance(state, saved[0])
    assert completed["cohorts"][0]["closed_at"]
    assert completed["cohorts"][0]["watch"]["positions"]["NRC.OL"]["last_price"] == 9


def test_capacity_refuses_new_cohorts_and_keeps_evidence():
    state = advance({}, screen(NOW))
    cohort = state["cohorts"][0]
    cohort["closed_at"] = NOW.isoformat()
    cohort["excess_return_pp"] = 0
    cohort["false_positive_count"] = 0
    state["cohorts"] = [deepcopy(cohort) for _ in range(120)]
    result = advance(state, screen(NOW + timedelta(days=1)))
    assert len(result["cohorts"]) == 120
    assert result["capacity_status"] == "FULL_EXPORT_AND_REVIEW_REQUIRED"


def test_primary_announcements_remain_metadata_not_verified_financial_numbers():
    from quality_filing_discovery import classify
    result = classify([
        {"id": 1, "publishedTime": "2026-08-20", "issuerSign": "NRC", "title": "Q2 2026 results"},
        {"id": 2, "publishedTime": "2026-10-11", "issuerSign": "NRC", "title": "Contract award"},
        {"id": 3, "publishedTime": "2026-08-20", "issuerSign": "NRC", "title": "Q2 results", "correctedByMessageId": 4},
    ], NOW)
    assert len(result) == 1 and result[0]["source_url"].endswith("/1")
    assert result[0]["numeric_extraction"] == "NOT_PERFORMED"
    assert result[0]["observed_at"] == NOW.isoformat()


def test_read_only_audit_finds_general_error_without_changing_stored_rows():
    from quality_classification_audit import audit_snapshots
    row = evaluate_company(financial(), as_of=NOW)
    row.update(review_reason_category="MISSING_DATA", quality_state="INSUFFICIENT")
    old = {"generated_at": NOW.isoformat(), "run_key": RUN, "groups": {"test": [row]}}
    before = deepcopy(old)
    audit = audit_snapshots([old])
    assert old == before and audit["read_only"]
    assert audit["affected_assessments_by_policy"] == {"CAPITAL_INTENSIVE": 1}
    assert audit["affected_unique_tickers"][0]["ticker"] == "NRC.OL"


def test_run_qualified_return_preserves_exact_selection_in_cards_and_pdf(monkeypatch):
    from public_report_ui import _report_return_href
    from quality_valuation_ui import _quality_report_choice_cards, build_screen_pdf
    assert "qv_report_run=quality_valuation%2Fruns%2F" in _report_return_href("quality_reports", RUN)
    assert "qv_report_run" not in _report_return_href("quality_reports", "../../secret")
    cards = _quality_report_choice_cards({"short_pdf": "a" * 40, "diagnosis": "b" * 40, "run_key": RUN})
    assert "qv_report_run" in cards
    result = screen(NOW)
    result["groups"] = {}
    reader = PdfReader(BytesIO(build_screen_pdf(result)))
    links = [a.get_object()["/A"]["/URI"] for a in reader.pages[0]["/Annots"] if a.get_object().get("/A")]
    assert any("qv_report_run=" in uri for uri in links)


def test_direct_report_return_bypasses_market_form_and_restores_requested_run(monkeypatch):
    import quality_valuation_ui as ui
    import quality_valuation_store as store
    desired = {"run_key": RUN, "selected_market": "Norge"}
    monkeypatch.setattr(store, "load_run", lambda key: desired if key == RUN else {})
    rendered = []
    monkeypatch.setattr(ui, "_render_quality_report_choices", lambda st, result: rendered.append(result))
    st = SimpleNamespace(query_params={"qv_reports": "1", "qv_report_run": RUN}, session_state={})
    ui.render_quality_report_return(st)
    assert rendered == [desired] and st.session_state["qv_result"] == desired


def test_sharing_rejects_external_or_script_urls_and_has_explicit_fallback():
    from public_report_ui import _share_controls_html
    for path in ("https://external.test/file.pdf", "javascript:alert(1)", '/app/static/reports/x.pdf"</script>'):
        with pytest.raises(ValueError):
            _share_controls_html(path)
    html = _share_controls_html("/app/static/reports/public_report_test.pdf")
    assert "shareNav.share({files:[file]" in html and "Last ned PDF" in html
    assert "AbortError" in html and "canShare" in html


def test_diagnostics_include_sources_classification_and_shadow_evidence():
    from quality_valuation_ui import diagnostic_document
    row = evaluate_company({**financial(), **interim()}, as_of=NOW)
    diagnosis = json.loads(diagnostic_document({"groups": {"test": [row]}, "turnaround_shadow": {"status": "OBSERVING"}}))
    saved = diagnosis["groups"]["test"][0]
    assert saved["historical_eps_median"] < 0 and saved["missing_data_checks"] == []
    assert saved["turnaround"]["metrics"]["fcf"]["delta"] == 7
    assert diagnosis["turnaround_shadow"]["status"] == "OBSERVING"
