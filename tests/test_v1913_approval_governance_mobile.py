from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_navigation_does_not_mutate_instantiated_workspace_key():
    overview = (ROOT / 'autonomy_overview.py').read_text()
    block = overview[overview.index('def _goto'):overview.index('def _safe_public_report_url')]
    assert 'autonomy_core_workspace_v1880' not in block
    assert 'autonomy_core_workspace_slug_v1882' in block

def test_norwegian_learning_portfolio_and_scheduler_labels():
    app = (ROOT / 'app.py').read_text()
    overview = (ROOT / 'autonomy_overview.py').read_text()
    assert '"learning_portfolio": "Læringsportefølje"' in app
    assert "<span class='ar-label'>Planlegger</span>" in overview
    assert 'Behandle i Learning Portfolio' not in overview

def test_approval_card_contains_required_decision_evidence():
    ui = (ROOT / 'approval_governance_ui.py').read_text()
    for label in ('Gammel verdi','Ny verdi','Testresultat','Forventet effekt','Mulig risiko','Reversering','Beslutningskommentar','Bekreft beslutning'):
        assert label in ui

def test_mobile_css_prevents_broken_columns_and_small_targets():
    ui = (ROOT / 'approval_governance_ui.py').read_text()
    assert '@media (max-width: 768px)' in ui
    assert 'min-width:100%' in ui
    assert 'min-height:44px' in ui
    assert 'overflow-wrap:anywhere' in ui

def test_promotion_decision_is_auditable():
    learning = (ROOT / 'controlled_parameter_learning.py').read_text()
    assert 'note: str = ""' in learning
    assert 'item["decision_note"] = note' in learning
    assert 'item["resolved_by"] = "USER"' in learning

def test_mobile_navigation_exposes_critical_destinations():
    app = (ROOT / 'app.py').read_text()
    block = app[app.index('_mobile_nav_html_v1900'):app.index('# --- Lagrede auto-innstillinger ---')]
    for destination in ('dashboard', 'autonomy', 'portfolio', 'reports', 'paper_trading', 'system'):
        assert destination in block
    assert 'overflow-x: auto' in app
