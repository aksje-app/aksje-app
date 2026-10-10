"""Execute actual router functions, fresh sessions and user-visible evidence."""
import ast
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
from navigation_state import *
from quality_stability_contract import is_supported_deep_link_nav
from superfund_presentation import decision_context, candidate_views, candidate_card, resolve_identity, investment_focus


def router(st):
    source=ast.parse(Path('app.py').read_text())
    names={'_apply_nav_target_v18658','_apply_mobile_nav_query_v18646','_clear_control_center_nav_state_v18663'}
    module=ast.Module(body=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[])
    namespace={**globals(),'st':st,'_persist_ui_state_v18658':lambda **kw:None,
               '_load_ui_state_v18658':lambda:{'nav':'dashboard'},
               '_query_params_plain_v18646':lambda:dict(st.query_params)}
    exec(compile(module,'app.py','exec'),namespace)
    return namespace


def test_superfund_refresh_restores_actual_router_before_start_fallback():
    st=SimpleNamespace(session_state={},query_params={'aa_nav':'superfund','aa_group':'Fond','aa_panel':'Superfond','aa_tab':'Kandidater'})
    router(st)['_apply_mobile_nav_query_v18646']()
    assert st.session_state['active_nav_target_v18674c']=='superfund'
    assert st.session_state['sf_section']=='Kandidater'
    assert st.query_params['aa_nav']=='superfund'
    # Another non-action run must leave route intact.
    router(st)['_apply_mobile_nav_query_v18646']()
    assert st.session_state['active_nav_target_v18674c']=='superfund'


def test_native_click_lease_wins_over_stale_start_url_and_panel():
    from tests.test_mobile_native_navigation import Fake
    from ui_library.shell import render_shell
    st=Fake('aa_mobile_nav_superfund')
    st.session_state={'persistent_nav_bootstrap_done_v18661':True,'active_nav_target_v18674c':'dashboard',
                      'ai_control_center_active_panel_v1863aj':'Old panel'}
    st.query_params={'aa_nav':'dashboard','aa_panel':'Old panel','aa_tab':'reports','mobile_nav':'dashboard','panel':'Old panel'}
    render_shell(st,'overview')
    route=st.session_state[GLOBAL_NAVIGATION_ROUTE_LEASE_KEY_V19220_RC14]
    consume_global_navigation_route_v19220_rc14(st)
    ns=router(st);ns['_apply_nav_target_v18658'](route['nav'])
    ns['_apply_mobile_nav_query_v18646']()
    assert st.session_state['active_nav_target_v18674c']=='superfund'
    assert st.query_params['aa_panel']=='Superfond'
    assert st.reruns==1
    assert st.query_params.get('aa_tab')!='reports'
    assert 'mobile_nav' not in st.query_params and 'panel' not in st.query_params


def test_all_visible_shell_links_are_supported_on_new_session():
    from ui_library.shell import DESKTOP_ROUTES,MOBILE_ROUTES,MORE_ROUTES,_LEGACY_TARGETS
    for item in DESKTOP_ROUTES+MOBILE_ROUTES+MORE_ROUTES:
        assert is_supported_deep_link_nav(_LEGACY_TARGETS[item.slug]),item.slug


def test_orders_get_actual_returns_price_and_bounded_history_without_fabrication():
    row={'id':'A','name':'Xtrackers MSCI Brazil UCITS ETF','kind':'etf','isin':'LU123','price':901,'currency':'EUR',
         'score':20,'returns':{'yield_1w':19.43,'yield_1m':16.56,'yield_3m':29.60},'rank':1,'blocks':[],
         'observations':[{'price_at':f'2026-01-{n:02d}','nok_price':100+n} for n in range(1,70)],
         'risk':5,'cost_pct':.34}
    original=deepcopy(row);context=decision_context(row)
    assert len(context['price_history_nok'])==60 and row==original
    assert context['price']==901 and context['returns']['yield_1w']==19.43
    top=candidate_views([row])['top_candidates'][0]
    assert top['price_history_nok']==context['price_history_nok']
    # Existing snapshot's thin identity can reuse candidate evidence.
    s={'fund_identity':{'A':{'name':row['name']}},'candidates':[row]}
    assert resolve_identity(s,{'id':'A','side':'BUY'})['price']==901
    html=candidate_card(top,True)
    assert '19.43%' in html and '901.00 EUR' in html
    assert 'Registreringsland' not in html and 'Rangeringspoeng' not in html
    assert 'indeksnavn' in investment_focus(row)


def test_unknown_development_is_not_reported_as_zero():
    html=candidate_card({'name':'Unknown','returns':{},'blocks':[]})
    assert '0.00%' not in html and 'Ikke oppgitt' in html
