"""Exercise the router with stale state and real Streamlit approval clicks."""
import ast
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
import pytest
from streamlit.testing.v1 import AppTest
import autonomy_parameter_governance as gov
import autonomous_portfolio as ap
import controlled_parameter_learning as learning
from services.storage_service import StorageService
from navigation_state import (consume_global_navigation_route_v19220_rc14,
    install_navigation_rerun_guard_v19220_rc14, set_global_navigation_state,
    GLOBAL_NAVIGATION_ROUTE_LEASE_KEY_V19220_RC14)
from ui_library.shell import render_shell
from tests.test_mobile_native_navigation import Fake

ROOT = Path(__file__).resolve().parents[1]

def test_single_portfolio_click_applies_workspace_through_real_router():
    st = Fake('aa_mobile_nav_portfolio')
    st.session_state.update(active_nav_target_v18674c='autonomy',
        ai_control_center_force_nav_v18663='autonomy',
        ai_control_center_last_applied_nav_v19016='autonomy',
        autonomy_core_workspace_active_slug_v19220_rc7='autonomous_portfolio',
        ai_control_center_active_panel_v1863aj='🧠 Autonomi – Kontrollsenter')
    install_navigation_rerun_guard_v19220_rc14(st)
    render_shell(st, 'autonomy')
    lease = st.session_state[GLOBAL_NAVIGATION_ROUTE_LEASE_KEY_V19220_RC14]
    assert lease['panel'] == ''  # old panel must not overwrite explicit click
    consume_global_navigation_route_v19220_rc14(st)
    tree = ast.parse((ROOT/'app.py').read_text())
    names = {'_clear_control_center_nav_state_v18663', '_apply_nav_target_v18658'}
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    scope = {'st': st, 'set_global_navigation_state': set_global_navigation_state,
             '_persist_ui_state_v18658': lambda **kwargs: None}
    exec(compile(ast.Module(body=functions, type_ignores=[]), 'app.py', 'exec'), scope)
    assert scope['_apply_nav_target_v18658']('portfolio')
    assert st.session_state['autonomy_core_workspace_slug_v1882'] == 'learning_portfolio'
    assert st.session_state['ai_control_center_group_v1863aj'] == 'Autonomi'
    assert st.reruns == 1

@pytest.fixture
def approval_app(tmp_path, monkeypatch):
    store = StorageService(tmp_path, mode='local', database_url='')
    store.write_json(gov.KEY, asdict(ap.AutonomousParameters(maximum_position_pct=1.5)))
    monkeypatch.setattr(gov, '_storage', lambda: store)
    monkeypatch.setattr(ap, 'load_parameters', lambda: ap.AutonomousParameters(**{
        k:v for k,v in store.read_json(gov.KEY, {}).items() if k in ap.AutonomousParameters.__dataclass_fields__}))
    monkeypatch.setattr(learning, '_read', lambda *args: [])
    p = gov.queue_proposal('maximum_position_pct', 1.5, .8, 'PF 0.86', {'dataset':'Autonomi', 'profit_factor':.86})
    app = AppTest.from_string('''import streamlit as st
from autonomy_parameter_governance import render_decisions
st.session_state['auth_user'] = {'username':'per'}
render_decisions(st)
st.write('Etter beslutningen')
''').run()
    assert not app.exception
    return app, store, p

def test_one_approval_click_commits_and_removes_proposal(approval_app):
    app, store, p = approval_app
    assert app.button[0].disabled
    app.checkbox[0].check().run()
    app.button(key='autonomy_params'+p['proposal_id']+'APPROVE').click().run()
    assert not app.exception
    doc = store.read_json(gov.KEY)
    assert doc['maximum_position_pct'] == .8
    assert doc[gov.META]['proposals'][0]['status'] == 'APPLIED'
    assert len(doc[gov.META]['history']) == 1
    assert 'IVERKSATT' in app.success[0].value
    assert not app.button
    app.run()  # subsequent render must never commit again
    assert len(store.read_json(gov.KEY)[gov.META]['history']) == 1

@pytest.mark.parametrize('decision,status', [('REJECT','REJECTED'),('DEFER','DEFERRED')])
def test_other_decisions_commit_in_one_click(approval_app, decision, status):
    app, store, p = approval_app
    app.button(key='autonomy_params'+p['proposal_id']+decision).click().run()
    assert not app.exception
    doc = store.read_json(gov.KEY)
    assert doc['maximum_position_pct'] == 1.5
    assert doc[gov.META]['proposals'][0]['status'] == status
    assert app.success

def test_failed_commit_does_not_claim_success(approval_app, monkeypatch):
    app, store, p = approval_app
    monkeypatch.setattr(gov, 'decide', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('Database utilgjengelig')))
    app.checkbox[0].check().run()
    app.button(key='autonomy_params'+p['proposal_id']+'APPROVE').click().run()
    assert app.error[0].value == 'Database utilgjengelig'
    assert not app.success
    assert store.read_json(gov.KEY)['maximum_position_pct'] == 1.5
    assert store.read_json(gov.KEY)[gov.META]['proposals'][0]['status'] == 'PENDING'

def test_mobile_content_style_excludes_fixed_navigation():
    source=(ROOT/'autonomous_portfolio.py').read_text()
    assert '[data-testid="stHorizontalBlock"]:not(.st-key-aa_mobile_nav_native *, .st-key-aa_mobile_more_native *)' in source
    theme=(ROOT/'ui_library/theme.py').read_text()
    assert '.st-key-aa_mobile_nav_native :is([data-testid="column"],[data-testid="stColumn"])' in theme
