"""Offline browser fixture: real Superfond UI with representative stored evidence."""
import ast
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import streamlit as st
import pages.superfund as page
from superfund_engine import DEFAULTS
from superfund_presentation import candidate_views
from ui_library.theme import inject_design_system
st.set_page_config(layout='wide')
# Reproduce the actual legacy CSS responsible for clipped captions, without
# importing the application or starting any of its workers.
source=ast.parse(Path('app.py').read_text())
for node in ast.walk(source):
    if isinstance(node,ast.Constant) and isinstance(node.value,str) and '<style' in node.value and 'stCaptionContainer' in node.value:
        st.markdown(node.value,unsafe_allow_html=True)
inject_design_system(st)
rows=[]
for n in range(30):
    rows.append({'id':f'IE{n:010d}:4','isin':f'IE{n:010d}','name':'Et internasjonalt fond med langt navn – Brasil og Latin-Amerika '+str(n),
        'kind':'etf','category':'Latin America Equity' if n%2 else 'Global Equity','returns_currency':'USD' if n%2 else 'EUR',
        'returns_currency_source':'INSTRUMENT_CURRENCY_FALLBACK','score':30-n/10,'rank':n//2+1,'risk':5,'cost_pct':.3,
        'price':901,'currency':'EUR','observations':[{'price_at':'2026-10-08T18:00:00Z','nok_price':100},{'price_at':'2026-10-09T18:03:56+00:00','nok_price':105}],
        'returns':{'yield_1w':19.43,'yield_1m':12.5,'yield_3m':25},'blocks':[],
        'price_at':'2026-10-09T18:03:56+00:00','observed_at':'2026-10-10T18:03:56+00:00','url':'https://www.nordnet.no/etf/liste/test'})
s={'at':'2026-10-10T12:00:00+00:00',**candidate_views(rows),'fund_identity':{rows[0]['id']:rows[0]},
    'model':{'cash':1000000,'initial_capital':1000000,'positions':{},'orders':[{'id':rows[0]['id'],'side':'BUY','reason':'Positiv ukestrend; venter på ny observert kursdato','requested_at':'2026-10-10T12:00:00+00:00'}]},
    'learning':{'paired_dates':12},'shadows':{'fast':{'cash':1000000,'positions':{},'history':[{}]}},'shadow_rules':{'fast':DEFAULTS},
    'coverage':{'complete':True,'listings':3173,'unique_isins':3156},'blocked_counts':{'RISIKO':20},'delivery':{}}
page.snapshot=lambda:s
page.config=lambda:DEFAULTS
page.read=lambda name,default: {'capacity':{'headroom_mb':1725.7,'cpu_pressure_avg10_pct':2.15}} if name=='job.json' else {'items':[{'title':'Lang nyhetstittel om renteutvikling og verdens aksjemarkeder','published':'Sat, 10 Oct 2026 06:37:53 GMT','url':'https://e24.no'}]} if name=='news.json' else {}
from tests.test_superfund_navigation_info import router
from navigation_state import consume_global_navigation_route_v19220_rc14
from ui_library.shell import render_shell,canonical_shell_route
ns=router(st)
fresh=st.session_state.get('global_navigation_route_lease_v19220_rc14',{})
consume_global_navigation_route_v19220_rc14(st)
if str(fresh.get('source','')).startswith('AURORA_MOBILE_NAV'):
    ns['_apply_nav_target_v18658'](fresh['nav'])
    st.session_state['persistent_nav_bootstrap_done_v18661']=True
ns['_apply_mobile_nav_query_v18646']()
route=canonical_shell_route(st.session_state.get('active_nav_target_v18674c','overview'))
render_shell(st,route)
if route!='superfund':
    st.title('Start' if route=='overview' else 'Side: '+route)
    st.stop()
page.render_superfund(st)
