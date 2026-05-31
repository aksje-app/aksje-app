from pathlib import Path
import py_compile


def test_shared_ranking_files_compile():
    for name in [
        "ranking_universe_adapters.py",
        "market_selector.py",
        "universe_engine.py",
        "services/universe_service.py",
        "app.py",
    ]:
        py_compile.compile(name, doraise=True)


def test_top_picks_uses_shared_ranking_with_legacy_fallback():
    source = Path("market_selector.py").read_text(encoding="utf-8", errors="ignore")
    block = source[source.find("def build_top_picks"):]

    assert "build_shared_top_picks" in block
    assert "except Exception" in block
    assert "picks = [r for r in results" in block


def test_market_ranking_cache_adds_shared_result_after_explicit_scan_only():
    app = Path("app.py").read_text(encoding="utf-8", errors="ignore")
    start = app.find("def cached_auto_rank_market")
    end = app.find("def _sort_ranked_items", start)
    block = app[start:end]

    assert "not force_manual_fetch" in block
    assert "not _heavy_update_allowed()" in block
    assert "return []" in block
    assert "auto_rank_market(" in block
    assert block.find("auto_rank_market(") < block.find("enrich_existing_ranking_rows")
    assert "latest_shared_rankings_v1863br" in block


def test_smart_ai_and_universe_service_persist_shared_ranking_from_existing_rows():
    engine = Path("universe_engine.py").read_text(encoding="utf-8", errors="ignore")
    service = Path("services/universe_service.py").read_text(encoding="utf-8", errors="ignore")

    assert "attach_shared_ranking_to_smart_result" in engine
    assert "shared_ranking" in engine
    assert "enrich_existing_ranking_rows" in service
    assert "latest_shared_rankings_v1863br" in service


def test_top_picks_control_center_remains_button_gated():
    app = Path("app.py").read_text(encoding="utf-8", errors="ignore")
    start = app.find("def render_top_picks_control_center_v1863s")
    end = app.find("def render_alpha_radar_control_center_v1863ap", start)
    block = app[start:end]

    assert "run_clicked = st.button" in block
    assert "if run_clicked and source_tickers:" in block
    assert block.find("cached_auto_rank_market") > block.find("if run_clicked and source_tickers:")






