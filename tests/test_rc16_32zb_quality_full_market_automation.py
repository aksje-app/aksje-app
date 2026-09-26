from datetime import datetime, timedelta, timezone
from pathlib import Path
import ast

ROOT=Path(__file__).resolve().parents[1]

def _src(name):
    text=(ROOT/name).read_text(encoding="utf-8")
    ast.parse(text, filename=name)
    return text

def test_scheduled_quality_uses_full_market_not_saved_top15():
    src=_src("quality_valuation_schedule.py")
    assert "full_market_prescreen(" in src
    assert "candidate_basis_refreshed" in src
    assert "market_universe_count" in src
    assert "market_examined_count" in src
    assert "analysis_symbols = list(dict.fromkeys([*holdings, *finalists]))" in src
    run_block=src[src.index("def run_due_scheduled_screen"):]
    assert "symbols = select_symbols(latest_market)" not in run_block

def test_candidate_basis_age_is_measurable_and_limit_is_60():
    import quality_valuation_schedule as q
    now=datetime(2026,9,26,12,0,tzinfo=timezone.utc)
    latest={"generated_at":(now-timedelta(minutes=61)).isoformat()}
    assert q.CANDIDATE_BASIS_MAX_AGE_MINUTES == 60
    assert q.market_run_age_minutes(latest, now) == 61.0

def test_holdings_do_not_consume_candidate_finalist_capacity():
    src=_src("quality_valuation_schedule.py")
    assert "SCHEDULED_CANDIDATE_LIMIT = 15" in src
    assert "SCHEDULED_HOLDING_LIMIT = 5" in src
    assert "SCHEDULED_ANALYSIS_LIMIT = 20" in src
    assert "finalists = list(prescreen.get" in src
    assert "holdings = _holding_symbols" in src

def test_report_freshness_is_two_hours_and_coverage_is_exposed():
    src=_src("quality_valuation_store.py")
    assert "max_age_hours: float = 2.0" in src
    assert '"market_coverage_complete"' in src
    assert '"candidate_basis_generated_at"' in src

def test_provider_calls_are_individually_guarded():
    src=_src("quality_valuation_data.py")
    assert 'warnings.append("Yahoo info utilgjengelig")' in src
    assert 'warnings.append("Resultatregnskap utilgjengelig")' in src
    assert 'warnings.append("Balanse utilgjengelig")' in src
    assert '"provider_partial": bool(warnings)' in src

def test_prescreen_has_memory_deadline_and_explicit_coverage():
    src=_src("quality_market_prescreen.py")
    assert "memory_guard" in src and "deadline_seconds" in src
    assert '"coverage_complete":len(rows)==total' in src
    assert '"stop_reason":stop_reason' in src

def test_quality_pdf_labels_deep_vs_market_coverage():
    src=_src("quality_valuation_ui.py")
    assert "dybdeanalyse" in src
    assert "Markedsgrunnlag:" in src
    assert "full dekning" in src
