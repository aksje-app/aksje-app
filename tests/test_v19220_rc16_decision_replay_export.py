from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

import report_replay_export as exporter
from autonomi_core.portfolio_decisions.layer import assess_candidate
from autonomous_portfolio import AutonomousParameters, recommended_learning_profile
from replay_engine import replay_report


def _context() -> dict:
    return {
        "positions": [],
        "position_count": 0,
        "cash": 500000.0,
        "total_value": 500000.0,
        "sector_exposure": {},
        "country_exposure": {},
        "currency_exposure": {},
        "limits": {
            "max_position_pct": 5.0,
            "max_sector_pct": 20.0,
            "max_positions": 12,
            "min_cash_pct": 10.0,
            "max_pair_correlation": 0.85,
        },
        "max_country_pct": 45.0,
        "max_currency_pct": 55.0,
        "minimum_liquidity_score": 40.0,
        "maximum_candidate_risk_score": 65.0,
        "minimum_investment_score": 73.0,
        "minimum_data_quality": 55.0,
        "allow_additions": False,
        "source": "TEST_SNAPSHOT",
    }


def _danske() -> dict:
    return {
        "ticker": "DANSKE.CO",
        "market": "Danmark",
        "sector": "Financial Services",
        "price": 240.0,
        "investment_score": 74.32,
        "data_quality": 95.0,
        "risk_score": 38.0,
        "liquidity_score": 86.0,
        "valid_for_decision": True,
        "evidence_valid_for_decision": True,
        "mission_eligible": True,
        "strategy_matches": ["Value Trend"],
        "technical_entry_wait": False,
        "status": "OBSERVASJONSLISTE",
        "portfolio_action": "REVIEW",
        "proposed_position_pct": 3.0,
    }


def test_rc16_breaks_circular_watch_dependency_without_lowering_thresholds():
    row = _danske()
    decision = assess_candidate(row, _context())
    assert decision["action"] == "BUY"
    assert decision["first_blocker_code"] == ""
    assert decision["thresholds"]["minimum_investment_score"] == 73.0
    assert all(decision["gates"].values())


@pytest.mark.parametrize(
    ("update", "code"),
    [
        ({"evidence_valid_for_decision": False}, "EVIDENCE_NOT_READY"),
        ({"investment_score": 72.99}, "SCORE_BELOW_THRESHOLD"),
        ({"data_quality": 54.9}, "DATA_QUALITY_BELOW_THRESHOLD"),
        ({"risk_score": 65.1}, "RISK_ABOVE_THRESHOLD"),
        ({"technical_entry_wait": True}, "TECHNICAL_ENTRY_WAIT"),
    ],
)
def test_rc16_remains_fail_closed_with_explicit_first_blocker(update, code):
    row = _danske()
    row.update(update)
    decision = assess_candidate(row, _context())
    assert decision["action"] != "BUY"
    assert code in decision["blocker_codes"]
    assert decision["first_blocker_code"]


def test_offline_replay_compares_stored_action_with_rc16_action():
    run = {"report_id": "MI-TEST", "run_id": "RUN-TEST", "portfolio_context": _context(), "candidates": [_danske()]}
    result = replay_report(run)
    assert result["status"] == "COMPLETED"
    assert result["changed_count"] == 1
    assert result["results"][0]["original_action"] == "REVIEW"
    assert result["results"][0]["rc16_action"] == "BUY"


def test_single_report_zip_contains_identity_snapshots_manifest_and_valid_hashes():
    run = {
        "report_id": "MI-20260805-162022",
        "run_id": "MBJ-TEST",
        "app_version": "v19.22.0-rc16",
        "created_at": "2026-08-05T16:20:25+02:00",
        "portfolio_context": _context(),
        "candidates": [_danske()],
        "api_key": "must-not-leak",
        "source_url": "https://example.test/news?token=secret&symbol=DANSKE.CO",
    }
    payload, manifest = exporter.build_single_report_package(run, pdf_bytes=b"%PDF-1.4\n%%EOF")
    assert manifest["identity"]["report_id"] == "MI-20260805-162022"
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        required = {
            "MANIFEST.json", "SHA256SUMS.txt", "report/report.pdf", "report/report.txt",
            "report/report.json", "report/input_snapshot.json", "report/decision_trace.json",
            "report/replay_result_rc16.json", "report/source_manifest.json",
        }
        assert required <= names
        exported = json.loads(archive.read("report/report.json"))
        assert exported["api_key"] == "REDACTED"
        assert "secret" not in exported["source_url"]
        sums = {}
        for line in archive.read("SHA256SUMS.txt").decode().splitlines():
            digest, name = line.split("  ", 1)
            sums[name] = digest
        for name, digest in sums.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest


def test_complete_export_deduplicates_and_includes_replay_outputs(monkeypatch):
    run = {
        "report_id": "MI-ONE", "run_id": "RUN-ONE", "app_version": "v19.22.0-rc15",
        "created_at": "2026-08-05T12:00:00+00:00", "portfolio_context": _context(), "candidates": [_danske()],
    }
    import market_intelligence as mi
    monkeypatch.setattr(mi, "_load_report_archive", lambda: [dict(run), dict(run)])
    monkeypatch.setattr(mi, "load_archived_run", lambda entry: dict(run))
    monkeypatch.setattr(exporter, "_read_pdf_without_side_effects", lambda *_args, **_kwargs: b"%PDF-1.4\n%%EOF")
    monkeypatch.setattr(exporter, "_collect_runtime_exports", lambda: {
        "autonomy_portfolio/portfolio.json": {"positions": {}},
        "autonomy_portfolio/trades.json": [],
        "learning_portfolio/portfolio.json": {"positions": {}},
        "learning_portfolio/trades.json": [],
    })
    payload, summary = exporter.build_complete_replay_export()
    assert summary["unique_reports_exported"] == 1
    assert summary["duplicates"] == 1
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "replay/REPLAY_RC15_VS_RC16_RESULTS.csv" in names
        assert "replay/REPLAY_CANDIDATE_DIFFS.json" in names
        assert "replay/REPLAY_DECISION_FUNNEL.json" in names
        assert "replay/REPLAY_UNRESOLVED_CASES.csv" in names
        assert "replay/REPLAY_LEARNING_SUMMARY.md" in names
        assert "reports/MI-ONE/report.pdf" in names


def test_recommended_learning_profile_is_large_but_learning_only_and_explicit():
    current = AutonomousParameters(learning_probe_notional_value=2500.0, maximum_position_pct=5.0, minimum_investment_score=73.0)
    recommended = recommended_learning_profile(current)
    assert current.learning_probe_notional_value == 2500.0
    assert recommended.learning_probe_notional_value == 15000.0
    assert recommended.learning_probe_max_buys == 3
    assert recommended.initial_cash == 500000.0
    assert recommended.maximum_position_pct == current.maximum_position_pct
    assert recommended.minimum_investment_score == current.minimum_investment_score


def test_rc16_fragment_and_sidebar_are_final_static_contracts():
    market_source = Path("market_intelligence.py").read_text(encoding="utf-8")
    app_source = Path("app.py").read_text(encoding="utf-8")
    sidebar_source = Path("ui_sidebar_stable.py").read_text(encoding="utf-8")
    render_section = market_source[market_source.index("def render_market_intelligence"):]
    assert "@st.fragment(run_every=\"3s\")" not in render_section
    assert "_live_report_progress_fragment_v19220_rc16()" in render_section
    assert "_replay_export_status_fragment_v19220_rc16()" in render_section
    assert app_source.rstrip().endswith("inject_rc16_final_sidebar_lock(st)")
    assert "width: 224px !important" in sidebar_source
    assert '[data-stale="true"]' in sidebar_source


def test_rc16_report_contract_uses_distinct_quality_labels_and_decision_layers():
    source = Path("market_intelligence.py").read_text(encoding="utf-8")
    assert "Beslutningsjustert markedsdatakvalitet" in source
    assert "Teknisk markedsdatadekning" in source
    assert "Analytiske kjøpsanbefalinger" in source
    assert "Gjennomførbare kjøp nå" in source
    assert "Produksjonsgodkjente kjøp" in source
    # Dense candidate detail sections must start cleanly on a new page.
    assert "story += [PageBreak(), Paragraph(" in source


def test_rc16_public_pdf_name_is_immutable_and_contains_report_identity():
    from report_delivery import ensure_public_pdf_name

    run = {
        "report_id": "MI-20260805-162022",
        "run_id": "MBJ-20260805-161625-3478DB",
        "job_name": "Utkast seks markeder",
        "created_at_local": "2026-08-05T16:20:25+02:00",
    }
    with patch("report_delivery.secrets.token_urlsafe", return_value="fixed-token"):
        first = ensure_public_pdf_name(run)
        second = ensure_public_pdf_name(run)
    assert first == second
    assert "MI-20260805-162022" in first
    assert first.endswith("fixed-token.pdf")


def test_rc16_existing_public_pdf_name_is_never_rewritten():
    from report_delivery import ensure_public_pdf_name

    run = {
        "report_id": "MI-NEW",
        "public_pdf_name": "historisk_uforanderlig_rapport.pdf",
    }
    assert ensure_public_pdf_name(run) == "historisk_uforanderlig_rapport.pdf"
