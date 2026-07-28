from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import types

import pytest

sys.modules.setdefault("streamlit", types.SimpleNamespace())

import app_version
import autonomy_modes
import autonomous_portfolio as ap
import insider_intelligence as ii
import market_intelligence as mi
from autonomi_core.portfolio_decisions import decision_funnel, layer
from autonomi_core.runtime import full_execution, orchestrator
from autonomous_decision_reduction import apply_decision_reduction
from official_insider_sources import fetch_nasdaq_nordic, fetch_sweden_fi
from report_integrity import canonical_report_view, validate_report_integrity


def _candidate(ticker: str = "AAPL", *, outcome: str = "OVERVÅKES_AUTOMATISK", action: str = "REVIEW") -> dict:
    return {
        "ticker": ticker,
        "name": ticker,
        "market": "USA",
        "investment_score": 80.0,
        "confidence_score": 80.0,
        "risk_score": 20.0,
        "data_quality": 100.0,
        "price": 100.0,
        "sector": "Teknologi",
        "portfolio_action": action,
        "autonomy_outcome_code": outcome,
        "autonomy_outcome_label": "Kjøpskandidat" if outcome == "KJØPSKANDIDAT" else "Overvåkes automatisk",
        "valid_for_decision": True,
        "evidence_valid_for_decision": True,
        "final_decision_ready": action in {"BUY", "KJØP"},
        "analysis_stage": "EVIDENCE_CONTROLLED",
        "decision_readiness": {"news": "CHECKED_NO_EVENTS", "insider": "CHECKED_NO_EVENTS", "conflicts": 0},
        "raw": {
            "score_formula": {"investment_score": 80.0, "weighted_contributions": {}, "contribution_semantics": {}},
            "news_intelligence": {"coverage": "CHECKED_NO_EVENTS", "search_log": []},
            "insider_intelligence": {"coverage": "CHECKED_NO_EVENTS", "search_log": []},
        },
    }


def _report(candidates: list[dict], *, buy_tickers: list[str] | None = None) -> dict:
    buy_tickers = list(buy_tickers or [])
    return {
        "run_id": "MI-19141-TEST",
        "created_at": "2026-07-28T14:07:02+00:00",
        "timezone_name": "Europe/Oslo",
        "job_id": "TEST",
        "job_name": "Dagsrapport",
        "trigger": "MANUAL_TEST",
        "markets": ["USA"],
        "summary": {"scanned": len(candidates), "proposals": len(candidates)},
        "candidates": candidates,
        "proposals": deepcopy(candidates),
        "portfolio_decisions": {"actions": {"BUY": len(buy_tickers), "REVIEW": 0}, "production_threshold": 73.0},
        "decision_funnel": {"production_threshold": 73.0},
        "data_quality": {"score": 100, "label": "UTMERKET"},
        "combined_data_quality": {"evaluated": len(candidates), "overall_valid": len(candidates)},
        "errors": [], "warnings": [], "changes": {},
        "autonomous_chain": {
            "status": "OK",
            "stages": [{
                "name": "AUTONOMOUS_PORTFOLIO", "status": "OK",
                "detail": {
                    "ordinary_buys": len(buy_tickers), "buys": len(buy_tickers),
                    "buy_tickers": buy_tickers, "sells": 0, "sell_tickers": [],
                    "execution_integrity": {"ok": True, "errors": []},
                },
            }],
        },
    }


def test_all_exposed_autonomy_versions_follow_app_version():
    expected = app_version.APP_VERSION
    assert expected == "v19.14.1"
    assert orchestrator.CORE_VERSION == expected
    assert full_execution.VERSION == expected
    assert layer.LAYER_VERSION == expected
    assert decision_funnel.VERSION == expected
    assert ap.VERSION == expected


def test_simple_mode_defaults_to_core_markets_even_without_or_with_old_mission(monkeypatch):
    monkeypatch.setattr(autonomy_modes, "read_persistent_json", lambda *args, **kwargs: {})
    assert autonomy_modes.load_simple_market_profile()["profile"] == autonomy_modes.CORE_PROFILE
    assert autonomy_modes.resolve_simple_markets(autonomy_modes.CORE_PROFILE) == ["Norge", "Sverige", "USA"]
    assert autonomy_modes.resolve_simple_markets(autonomy_modes.EXTENDED_PROFILE) == ["Danmark", "Finland"]
    assert autonomy_modes.resolve_simple_markets(autonomy_modes.BRAZIL_PROFILE) == ["Brasil"]


def test_hard_buy_authorization_rejects_review_and_accepts_only_completed_buy():
    allowed, reasons = ap.production_buy_authorization(_candidate())
    assert allowed is False
    assert any("ikke Kjøpskandidat" in reason for reason in reasons)

    buy = _candidate(outcome="KJØPSKANDIDAT", action="BUY")
    allowed, reasons = ap.production_buy_authorization(buy)
    assert allowed is True
    assert reasons == []


def test_execution_integrity_rejects_unauthorized_buy_and_same_run_roundtrip():
    watch = _candidate()
    portfolio = {"positions": {"AAPL": {"ticker": "AAPL"}}}
    integrity = ap._validate_execution_integrity(
        [{"ticker": "AAPL", "action": "BUY"}, {"ticker": "AAPL", "action": "SELL"}],
        {"AAPL": watch}, portfolio,
    )
    assert integrity["ok"] is False
    assert any("kjøp uten godkjent beslutningsport" in error for error in integrity["errors"])
    assert any("både kjøp og salg" in error for error in integrity["errors"])


def test_live_report_integrity_blocks_aapl_style_unauthorized_buy():
    report = canonical_report_view(_report([_candidate()], buy_tickers=["AAPL"]))
    validation = validate_report_integrity(report)
    assert validation["ok"] is False
    assert any("produksjonskjøp uten Autonomiutfall Kjøpskandidat" in error for error in validation["errors"])


def test_report_integrity_accepts_watch_without_trade_and_keeps_priority_1_to_3():
    rows = [_candidate("AAPL"), _candidate("MSFT"), _candidate("NVDA")]
    report = canonical_report_view(_report(rows))
    assert report["report_integrity"]["ok"] is True
    assert [row["priority_rank"] for row in report["priority_top3"]] == [1, 2, 3]
    assert report["learning_portfolio_summary"]["production_buys"] == 0


def test_canonical_threshold_uses_actual_production_threshold_not_default_78():
    report = canonical_report_view(_report([_candidate()]))
    reduction = report["autonomous_decision_reduction"]
    assert reduction["production_buy_threshold"] == 73.0
    assert reduction["threshold"] == 73.0
    assert "ikke en egen kjøpsterskel" in reduction["threshold_explanation"]


def test_nested_raw_is_flattened_and_rankings_are_compact():
    row = _candidate()
    row["raw"] = {"latest": 1, "raw": {"older": 2, "raw": {"oldest": 3}}}
    report = canonical_report_view(_report([row]))
    raw = report["candidates"][0]["raw"]
    assert "raw" not in raw
    assert raw["latest"] == 1
    assert len(raw.get("raw_history") or []) <= 3
    assert "raw" not in report["priority_top3"][0]
    assert report["proposals"][0]["proposal_stage"] == "PRELIMINARY_MODEL_OUTPUT"


def test_decision_funnel_mirrors_hard_gate():
    class Params:
        minimum_investment_score = 73
        minimum_data_quality = 55
        maximum_risk_score = 65
        maximum_open_positions = 12
        allow_additions = False

    watch = _candidate()
    funnel = decision_funnel.build_decision_funnel([watch], parameters=Params(), portfolio={"status": "ACTIVE", "positions": {}})
    row = funnel["candidates"][0]
    assert row["eligible_for_theoretical_buy"] is False
    assert row["gates"]["autonomy_outcome_buy"] is False

    buy = _candidate(outcome="KJØPSKANDIDAT", action="BUY")
    funnel = decision_funnel.build_decision_funnel([buy], parameters=Params(), portfolio={"status": "ACTIVE", "positions": {}})
    assert funnel["candidates"][0]["eligible_for_theoretical_buy"] is True


class _Response:
    def __init__(self, *, content: bytes = b"", text: str = "", url: str = "https://official.example/result"):
        self.content = content
        self.text = text or content.decode("utf-8", errors="replace")
        self.url = url
    def raise_for_status(self):
        return None


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_swedish_fi_direct_parser_returns_structured_official_transaction():
    csv_data = (
        "Transaktionsdatum;Person i ledande ställning namn;Befattning;Karaktär;Volym;Pris;Valuta;Publiceringsdatum;Publiceringsid\n"
        "2026-07-20;Anna Test;VD;Förvärv;100;125,50;SEK;2026-07-21;FI-1\n"
    ).encode("utf-8")
    session = _Session([_Response(content=csv_data)])
    result = fetch_sweden_fi("TEST.ST", "Test AB", session=session)
    assert result["status"] == "SUCCESS_WITH_RESULTS"
    assert result["direct_primary_source_checked"] is True
    assert result["transactions"][0]["verification"] == "OFFICIAL_PRIMARY"
    assert result["transactions"][0]["shares"] == 100


def test_nasdaq_direct_parser_returns_structured_manager_transaction():
    rss = b'''<?xml version="1.0"?><rss><channel><item>
    <title>Test Oyj - Managers' transactions</title>
    <description>Nature of transaction: Acquisition; Volume: 200; Unit price: 10.5; Name: Kari Test; Position: CEO; Transaction date: 2026-07-22</description>
    <link>https://official.example/notice</link><guid>N-1</guid><pubDate>Wed, 22 Jul 2026 10:00:00 GMT</pubDate>
    </item></channel></rss>'''
    session = _Session([_Response(content=rss), _Response(content=b"<rss><channel/></rss>")])
    result = fetch_nasdaq_nordic("TEST.HE", "Test Oyj", "Finland", session=session)
    assert result["status"] == "SUCCESS_WITH_RESULTS"
    assert result["direct_primary_source_checked"] is True
    assert result["transactions"][0]["verification"] == "OFFICIAL_EXCHANGE_FEED"


def test_direct_official_source_is_attempted_even_if_yfinance_fails(monkeypatch):
    direct = {
        "status": "SUCCESS_NO_RESULTS", "transactions": [],
        "attempts": [{
            "source": "Offisiell testkilde", "source_type": "OFFICIAL_PRIMARY",
            "attempted": True, "status": "SUCCESS_NO_RESULTS", "results": 0,
            "checked_at": "2026-07-28T12:00:00+00:00", "url": "https://official.example",
            "direct_primary_source_checked": True, "error": "",
        }],
    }
    monkeypatch.setattr(ii, "_load_cache", lambda: {})
    monkeypatch.setattr(ii, "_store_cached_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(ii, "fetch_official_insider_sources", lambda *args, **kwargs: direct)
    monkeypatch.setattr(ii, "discover_with_newsapi", lambda *args, **kwargs: pytest.fail("NewsAPI should not run after a terminal official no-event result"))

    import sys
    class BrokenYF:
        class Ticker:
            def __init__(self, ticker):
                raise RuntimeError("provider down")
    monkeypatch.setitem(sys.modules, "yfinance", BrokenYF)

    result = ii.fetch_insider_intelligence("TEST.ST", force_refresh=True, market="Sverige", company="Test AB")
    assert result["coverage"] == "CHECKED_NO_EVENTS"
    assert result["direct_primary_source_checked"] is True
    assert result["search_log"][0]["source"] == "Offisiell testkilde"
    assert any(row["status"] == "SOURCE_ERROR" for row in result["search_log"] if row["source"].startswith("yfinance"))


def test_user_facing_report_source_has_no_legacy_followup_label_or_raw_english_fallback():
    source = Path(mi.__file__).read_text(encoding="utf-8")
    assert "Evidensport krever oppfølging" not in source
    assert 'rows.append(["Begge", "Ingen registrert søkelogg", "Nei", "NOT_SEARCHED"' not in source
    assert "Konkrete manuelle oppgaver" in source
