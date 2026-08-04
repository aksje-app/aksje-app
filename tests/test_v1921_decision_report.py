from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

import market_intelligence as mi
from app_version import APP_VERSION, REPORT_SCHEMA_VERSION
from decision_report import (
    CONSENSUS_LEVELS,
    REPORT_FOCUS,
    TASK_STATUSES,
    build_change_summary,
    build_decision_report,
    candidate_source_consensus,
)
from report_contracts import build_report_identity, ensure_report_document, section_payload


def _candidate(
    ticker: str,
    *,
    rank: int,
    score: float,
    action: str = "REVIEW",
    ready: bool = False,
    sources: tuple[str, ...] = ("E24",),
    primary: bool = False,
    conflicts: int = 0,
    earnings_date: str = "",
) -> dict:
    news_events = [{"source": source, "title": f"{ticker} news"} for source in sources]
    search_log = [
        {
            "source": source,
            "attempted": True,
            "status": "SUCCESS_WITH_RESULTS",
            "results": 1,
            "source_type": "PRIMARY_OR_DIRECT_RSS" if primary and i == 0 else "PUBLISHED_NEWS",
        }
        for i, source in enumerate(sources)
    ]
    return {
        "rank": rank,
        "ticker": ticker,
        "market": "Norge",
        "investment_score": score,
        "confidence_score": 84,
        "risk_score": 42,
        "portfolio_action": action,
        "status": "ANBEFALT FOR VURDERING" if action != "SKIP" else "IKKE AKTUELL",
        "valid_for_decision": ready,
        "evidence_valid_for_decision": ready,
        "data_contract": {"validity": "VALID", "source": "LIVE"},
        "decision_readiness": {
            "news": "VERIFIED_FACTS_FOUND",
            "insider": "CHECKED_NO_EVENTS",
            "conflicts": conflicts,
        },
        "raw": {
            "current_price": 100 + rank,
            "earnings_date": earnings_date,
            "news_intelligence": {
                "source": ", ".join(sources),
                "events": news_events,
                "search_log": search_log,
            },
            "insider_intelligence": {
                "coverage": "AVAILABLE",
                "official_source": "Oslo Børs" if primary else "",
                "evidence": [],
                "search_log": [],
            },
        },
    }


def _run(report_time: str = "2026-07-25T18:30:00+00:00") -> dict:
    return {
        "run_id": "MI-1921-TEST",
        "created_at": report_time,
        "timezone_name": "Europe/Oslo",
        "job_id": "JOB-1921",
        "job_name": "Beslutningsrapport",
        "trigger": "SCHEDULED",
        "markets": ["Norge"],
        "summary": {"scanned": 3, "deep_analyzed": 3, "proposals": 2, "recommended": 1},
        "data_quality": {"score": 91, "label": "UTMERKET"},
        "combined_data_quality": {"evaluated": 3, "overall_valid": 2},
        "candidates": [
            _candidate("EQNR.OL", rank=1, score=77.2, sources=("E24", "Reuters", "Oslo Børs"), primary=True, earnings_date="2026-07-27"),
            _candidate("DNB.OL", rank=2, score=81.0, action="BUY", ready=True, sources=("E24", "Reuters", "DN"), primary=True),
            _candidate("TEL.OL", rank=3, score=69.0, action="SKIP", ready=False, sources=("E24",)),
        ],
        "changes": {
            "new": [],
            "improved": [{"ticker": "EQNR.OL", "score_delta": 3.2}],
            "weakened": [{"ticker": "TEL.OL", "score_delta": -2.4}],
            "dropped": [],
            "unchanged_count": 1,
        },
        "portfolio_decisions": {"production_threshold": 78, "actions": {"BUY": 1, "REVIEW": 1, "SKIP": 1}},
        "report_status": {"state": "FINAL", "label": "ENDELIG"},
        "report_revision": {"revision": 1, "revision_label": "R1", "content_sha256": "abc"},
        "errors": [],
        "warnings": [],
    }


def test_decision_report_is_read_only_for_ranking_and_trading_fields():
    run = _run()
    before = deepcopy(run["candidates"])
    document = ensure_report_document(run)
    assert run["candidates"] == before
    assert APP_VERSION.startswith("v19.22.0-rc")
    assert REPORT_SCHEMA_VERSION == "1.6"
    assert document["schema_version"] == "1.6"
    assert run["decision_report"]["schema_version"] == "1.4"


def test_every_timed_report_has_distinct_focus_and_matching_mission():
    cases = {
        "2026-07-25T05:00:00+00:00": "MORGENRAPPORT",
        "2026-07-25T11:00:00+00:00": "DAGSRAPPORT",
        "2026-07-25T16:00:00+00:00": "KVELDSRAPPORT",
        "2026-07-25T23:00:00+00:00": "NATTRAPPORT",
    }
    focus_sets = []
    for created_at, report_type in cases.items():
        identity = build_report_identity("SCHEDULED", created_at=created_at, timezone_name="Europe/Oslo")
        run = _run(created_at)
        payload = build_decision_report(run, None, identity)
        assert identity["type"] == report_type
        assert payload["overview"]["focus"] == REPORT_FOCUS[report_type]
        focus_sets.append(tuple(payload["overview"]["focus"]))
    assert len(set(focus_sets)) == 4


def test_candidate_contract_has_blockers_change_conditions_validity_and_three_confidences():
    run = _run()
    doc = ensure_report_document(run)
    candidates = section_payload(doc, "candidate_decisions", [])
    eqnr = candidates[0]
    assert any("under beslutningsterskel" in item for item in eqnr["blockers"])
    assert any("må nå minst" in item for item in eqnr["change_conditions"])
    assert eqnr["validity"]["valid_until"]
    assert eqnr["validity"]["price_range"]["minimum"] < eqnr["validity"]["price_range"]["maximum"]
    assert set(eqnr["confidence"]) >= {"data_coverage", "source_confidence", "decision_confidence"}
    assert "sannsynlighet for gevinst" in eqnr["confidence"]["note"]


def test_source_consensus_is_explainable_and_conflicts_fail_to_conflicting():
    strong = candidate_source_consensus(_candidate("AAA.OL", rank=1, score=80, sources=("E24", "Reuters", "Oslo Børs"), primary=True))
    assert strong["level"] == "STERK"
    assert strong["primary_source_present"] is True
    assert strong["independent_sources"] >= 3
    conflicting_candidate = _candidate("BBB.OL", rank=2, score=80, sources=("E24", "Reuters"), conflicts=1)
    conflicting = candidate_source_consensus(conflicting_candidate)
    assert conflicting["level"] == "MOTSTRIDENDE"
    assert conflicting["level"] in CONSENSUS_LEVELS


def test_reliability_explains_deductions_and_is_not_return_probability():
    run = _run()
    run["errors"] = ["Testfeil"]
    run["report_status"] = {"state": "PROVISIONAL", "label": "FORELØPIG"}
    ensure_report_document(run)
    reliability = run["report_reliability"]
    assert reliability["score"] < 100
    assert reliability["deductions"]
    assert any(row["code"] == "RUN_ERRORS" for row in reliability["deductions"])
    assert any(row["code"] == "PROVISIONAL" for row in reliability["deductions"])
    assert reliability["not_investment_probability"] is True


def test_next_run_tasks_are_traceable_and_use_declared_statuses():
    run = _run()
    ensure_report_document(run)
    tasks = run["next_run_tasks"]
    assert tasks
    assert any(row["kind"] == "NEAR_THRESHOLD" and row["subject"] == "EQNR.OL" for row in tasks)
    assert any(row["kind"] == "UPCOMING_EVENT" for row in tasks)
    assert all(row["status"] in TASK_STATUSES for row in tasks)
    assert all(row["task_id"].startswith("TASK-") and row["source_report_id"] == run["run_id"] for row in tasks)


def test_event_calendar_is_candidate_relevant_deduplicated_and_localized():
    run = _run()
    ensure_report_document(run)
    events = run["critical_events"]
    assert len(events) == 1
    assert events[0]["ticker"] == "EQNR.OL"
    assert events[0]["title"] == "Resultatpublisering"
    assert events[0]["event_at_local"].endswith("+02:00")


def test_change_summary_tracks_top3_and_action_changes():
    previous = _run()
    previous["run_id"] = "MI-1921-PREV"
    previous["candidates"] = [
        _candidate("DNB.OL", rank=1, score=80, action="REVIEW"),
        _candidate("ORK.OL", rank=2, score=75),
        _candidate("TEL.OL", rank=3, score=72),
    ]
    current = _run()
    summary = build_change_summary(current, previous)
    assert "EQNR.OL" in summary["top3_added"]
    assert "ORK.OL" in summary["top3_removed"]
    assert any(row["ticker"] == "DNB.OL" and row["to"] == "BUY" for row in summary["action_changes"])
    assert summary["top3_changed"] is True


def test_pdf_has_one_page_decision_section_before_full_technical_appendix():
    run = _run()
    pdf = mi.build_pdf(run)
    reader = PdfReader(BytesIO(pdf))
    pages = [page.extract_text() or "" for page in reader.pages]
    assert "Markedsanalyse – beslutningsside" in pages[0]
    assert "Rapportpålitelighet" not in pages[0]
    assert "Top 1-3 - investeringsrangering" in pages[0]
    assert "Oppgaver til neste kjøring" in "\n".join(pages[:2])
    technical_page = next(i for i, text in enumerate(pages) if "Teknisk vedlegg" in text)
    assert technical_page <= 2  # side 1 er beslutningsside, side 2 oppfølging
    assert technical_page > 0
    assert "Full rangering" in pages[technical_page]


def test_text_report_uses_same_decision_sections():
    run = _run()
    document = ensure_report_document(run)
    text = mi.build_text_report(run)
    section_payload(document, "report_reliability", {})
    assert "BESLUTNINGSSTATUS" in text
    assert "Rapportpålitelighet:" not in text
    for label in ("Markedsdatakvalitet", "Rapportens tekniske dokumentasjonsgrad", "Kandidatenes evidensdekning", "Uavhengig kildedekning", "Beslutningsstyrke på rapportnivå"):
        assert label in text
    assert "OPPGAVER TIL NESTE KJØRING" in text
    assert "Kan endres når" in text
    assert "TEKNISK VEDLEGG" in text


def test_archive_contains_decision_fields_and_ui_has_all_filters():
    run = _run()
    entry = mi._archive_entry(run)
    assert set(entry) >= {
        "report_reliability", "report_decision_strength", "candidate_evidence_coverage", "decision_ready_count", "top3_changed", "next_task_count",
        "upcoming_event_count", "has_errors", "reserve_feed_used", "low_reliability",
    }
    source = Path(mi.__file__).read_text(encoding="utf-8")
    for report_type in ("MORGENRAPPORT", "DAGSRAPPORT", "KVELDSRAPPORT", "NATTRAPPORT"):
        assert report_type in source
    for label in ("Datoperiode", "Marked", "Rapportstatus", "Endret Top 3", "Lav beslutningsstyrke", "Reserve-feed"):
        assert label in source

def test_previous_comparison_survives_later_renderer_refresh_without_previous_argument():
    previous = _run()
    previous["run_id"] = "MI-1921-PREVIOUS"
    previous["candidates"] = [
        _candidate("DNB.OL", rank=1, score=80, action="REVIEW"),
        _candidate("ORK.OL", rank=2, score=75),
        _candidate("TEL.OL", rank=3, score=72),
    ]
    current = _run()
    ensure_report_document(current, previous)
    initial = deepcopy(current["decision_report"]["changes"])
    ensure_report_document(current)
    assert current["decision_report"]["changes"] == initial
    assert "EQNR.OL" in initial["top3_added"]
    assert "ORK.OL" in initial["top3_removed"]
