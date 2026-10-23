"""Offline full-app UI fixture; authentication and HTTP providers are substituted.

Never used by app.py/Render. Enable explicitly with isolated /tmp state.
"""
import sys, runpy, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if (os.environ.get('AUDIT_UI_FIXTURE') != '1' or os.environ.get('DATABASE_URL')
    or os.environ.get('AUTH_DATABASE_URL') or os.environ.get('STORAGE_MODE') != 'local'
    or not os.environ.get('APP_RUNTIME_ROOT', '').startswith('/tmp/aksje-browser-')):
    raise RuntimeError('Offline fixture requires isolated temporary state')
import streamlit as st
_audit_runtime_root = Path(os.environ['APP_RUNTIME_ROOT'])
_audit_probe = str(st.query_params.get('audit_probe') or st.session_state.get('_audit_probe') or '')
if _audit_probe:
    st.session_state['_audit_probe'] = _audit_probe
import auth
# Authentication is deliberately out of scope for this local fixture.
user={'username':'offline-audit','role':'admin','active':True}
def fixture_login():
    st.session_state['auth_user']=user
    return user
auth.require_login=fixture_login
# Explicit fixture-only activation exposes menus without starting workers.
if os.environ.get('AUDIT_UI_ACTIVE') == '1':
    import settings_store
    if not hasattr(settings_store, '_audit_original_load_settings'):
        settings_store._audit_original_load_settings = settings_store.load_settings
    def active_settings(_read=settings_store._audit_original_load_settings):
        return {**_read(), 'autonomy_enabled':True}
    settings_store.load_settings=active_settings
import requests
requests.sessions.Session.request=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('Offline audit: external HTTP disabled'))
# Native curl and urllib providers must also fail immediately offline.
try:
    import curl_cffi.requests as curl_requests
    curl_requests.Session.request = requests.sessions.Session.request
except ImportError:
    pass
import socket
original_connect = getattr(socket.socket.connect, '_audit_original', socket.socket.connect)
def local_connect(sock, address, _connect=original_connect):
    if isinstance(address, tuple) and address[0] not in ('localhost','127.0.0.1','::1'):
        raise OSError('Offline audit: non-local socket disabled')
    return _connect(sock,address)
local_connect._audit_original = original_connect
socket.socket.connect = local_connect
import yfinance as yf
import pandas as pd
yf.download=lambda *a,**k: pd.DataFrame()
yf.Ticker.history=lambda *a,**k: pd.DataFrame()
yf.Ticker.get_info=lambda *a,**k: {}
try:
    runpy.run_path(str(ROOT / 'app.py'),run_name='__main__')
finally:
    import json
    # Session-state reads can also yield to a pending st.stop() request.
    # Write the receipt before accessing any Streamlit API in this block.
    _audit_error = sys.exc_info()[1]
    if _audit_probe and (_audit_error is None or type(_audit_error).__name__ == 'StopException'):
        (_audit_runtime_root / ('render-complete-' + _audit_probe + '.json')).write_text(
            json.dumps({'completed':True}))
    keys=('active_nav_target_v18674c','ai_control_center_active_panel_v1863aj',
          'ai_control_center_group_v1863aj','persistent_nav_bootstrap_done_v18661',
          'global_navigation_route_lease_v19220_rc14','navigation_last_source_v19143')
    Path(os.environ['APP_RUNTIME_ROOT'],'ui-navigation.json').write_text(json.dumps(
        {'query':dict(st.query_params),'state':{k:st.session_state.get(k) for k in keys}},default=str))
    # st.stop() leaves a pending stop request: another Streamlit UI call in
    # finally would immediately stop again. Use an out-of-band test receipt.
