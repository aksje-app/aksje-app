from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_overview_order_and_direct_action():
    src=(ROOT/"pages/overview.py").read_text(encoding="utf-8")
    assert src.index("QUALITY V2 · SHADOW") < src.index("SUPER PORTEFØLJE")
    assert '▶ Kjør kvalitetsvurdering' in src
    assert "aa_overview_quality_top" in src

def test_manual_latest_is_independent_and_ui_reloads_it():
    store=(ROOT/"quality_valuation_store.py").read_text(encoding="utf-8")
    ui=(ROOT/"quality_valuation_ui.py").read_text(encoding="utf-8")
    assert 'MANUAL_LATEST = f"{ROOT}/manual_latest"' in store
    assert "def load_latest_manual" in store
    assert 'snapshot.get("run_mode") != "SCHEDULED_SHADOW"' in store
    assert "load_latest_manual()" in ui
    assert "⌂ Hovedsiden" in ui

def test_warning_presentation_separates_uncertainty_types():
    ui=(ROOT/"quality_valuation_ui.py").read_text(encoding="utf-8")
    assert "def _warning_kind" in ui
    assert '"Datagrunnlag"' in ui
    assert '"Verdsettelse"' in ui
    assert '"Risiko/kvalitet"' in ui

def test_v2_mobile_layout_has_explicit_fact_cells():
    theme=(ROOT/"ui_library/theme.py").read_text(encoding="utf-8")
    assert ".aa-v2-shadow-facts>span" in theme
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in theme
