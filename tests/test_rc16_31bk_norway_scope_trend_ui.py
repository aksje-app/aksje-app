from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding='utf-8')


def test_visible_market_override_updates_market_profile_too():
    src = read('autonomous_orchestrator_ui.py')
    assert 'market_profile=infer_market_profile([choice])' in src
    assert 'markets=[choice]' in src
    assert 'Utkast – {choice}' in src


def test_norway_only_is_enforced_in_manual_acceptance_and_runtime():
    bg = read('manual_job_background.py')
    mi = read('market_intelligence.py')
    assert 'job = _apply_manual_norway_stabilization(job, trigger)' in bg
    assert 'PRODUCTION_NORWAY_ONLY' in bg
    assert 'markets=["Norge"]' in bg
    assert 'norway_production_stabilization' in mi
    assert 'trigger_key.startswith("MANUAL")' in mi
    assert 'market_profile=infer_market_profile(["Norge"])' in mi


def test_stabilization_ui_only_exposes_norway():
    src = read('autonomous_orchestrator_ui.py')
    assert 'market_choices = ["Norge"] if norway_stabilization else ORCHESTRATOR_MARKET_CHOICES' in src
    assert 'Produksjonsstabilisering er aktiv' in src


def test_trend_details_cover_top_1_to_10_and_have_period_toggle():
    src = read('market_intelligence.py')
    assert 'Trenddetaljer 1–10' in src
    assert 'for trend_row in candidates[:10]' in src
    assert '["20d", "60d"]' in src
    assert 'rolling(20).mean()' in src
    assert 'rolling(50).mean()' in src
    assert 'RSI14' in src
    assert 'volume_ratio_20' in src
    assert 'distance_from_20d_high_pct' in src
    assert 'rank_change' in src


def test_pdf_uses_20d_chart_with_sma_and_keeps_60d_metrics():
    src = read('market_intelligence.py')
    assert 'start_index = max(0, len(points) - 20)' in src
    assert '"SMA20": sma20[start_index:]' in src
    assert '"SMA50": sma50[start_index:]' in src
    assert 'Grafen viser siste 20 handelsdager med kurs, SMA20 og SMA50' in src
    assert "60d {_fmt_signed(receipt.get('return_60d_pct'))}" in src


def test_full_universe_report_does_not_claim_70_20_10_rotation():
    src = read('market_intelligence.py')
    assert 'Hele det konfigurerte universet grovskannes før shortlist.' in src
    assert '70/20/10-rotasjon brukes derfor ikke i dette steget' in src


def test_bk_release_is_preserved_in_changelog():
    src = read('app_version.py')
    assert 'v19.22.0-rc16.31bk: Norway Scope and Trend UI Closure.' in src
