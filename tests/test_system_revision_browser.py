"""Actual full-app browser flows with isolated offline state, not authentication tests."""
import json
from io import BytesIO
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
import zipfile
import pytest

pytestmark=pytest.mark.skipif(os.getenv('SYSTEM_BROWSER_TEST')!='1',reason='Enable explicitly; requires a Chromium executable')

@pytest.fixture(scope='module')
def app_server():
    import tempfile
    runtime=tempfile.mkdtemp(prefix='aksje-browser-regression-')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env={**os.environ,'AUDIT_UI_FIXTURE':'1','AUDIT_UI_ACTIVE':'1','APP_RUNTIME_ROOT':runtime,'STORAGE_MODE':'local',
         'DATABASE_URL':'','AUTH_DATABASE_URL':'','AUTH_STORAGE_MODE':'local',
         'RUNTIME_BACKGROUND_ENABLED':'false','REPORT_SCHEDULER_ENABLED':'false',
         'PAPER_TRADING_ENABLED':'false','ALLOW_LOCAL_STORAGE_FALLBACK':'true'}
    with open(runtime+'/server.log','w') as log:
        proc=subprocess.Popen([sys.executable,'-m','streamlit','run','scripts/system_revision_ui_fixture.py',
            '--server.port='+str(port),'--server.headless=true','--browser.gatherUsageStats=false'],env=env,stdout=log,stderr=log)
        base='http://127.0.0.1:'+str(port)
        try:
            for _ in range(100):
                try:
                    if urlopen(base+'/_stcore/health',timeout=1).status==200:break
                except Exception:time.sleep(.2)
            else:raise AssertionError('Full app did not start')
            yield base
        finally:
            proc.terminate();proc.wait(timeout=10)

@pytest.mark.parametrize('width',[1280,375])
def test_paper_zip_download_read_only_and_return(app_server,width):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.environ.get('BROWSER_EXECUTABLE') or None)
        page=browser.new_page(viewport={'width':width,'height':900},accept_downloads=True)
        page.goto(app_server+'/?aa_nav=paper_trading')
        page.get_by_role('heading',name='💼 Handel – Paper Trading',exact=True).wait_for()
        panel=page.locator('[data-testid="stExpander"]').filter(has_text='📦 Paper Trading – diagnose og historikk (ZIP)')
        panel.locator('summary').click()
        page.get_by_role('button',name='Lag diagnose-ZIP',exact=True).click()
        with page.expect_download() as download:
            page.get_by_role('button',name='Last ned Paper Trading diagnose-ZIP',exact=True).click()
        with zipfile.ZipFile(BytesIO(Path(download.value.path()).read_bytes())) as z:
            assert z.testzip() is None
            files={name:json.loads(z.read(name)) for name in z.namelist()}
        assert files['manifest.json']['read_only'] is True
        assert files['manifest.json']['economic_verification']['status']=='IKKE VERIFISERT'
        assert files['paper_trades.json']==[]
        assert files['paper_portfolio.json']['positions']=={}
        assert not page.locator('[data-testid="stException"]').count()
        if width<768:
            page.locator('.st-key-aa_mobile_nav_overview button').click()
        else:
            page.get_by_role('button',name='🏠 Oversikt',exact=True).click()
        page.get_by_role('heading').filter(has_text='God').first.wait_for()
        assert 'aa_nav=dashboard' in page.url
        browser.close()

@pytest.mark.parametrize('width',[1280,375])
def test_report_menu_opens_reports_from_simple_mode(app_server,width):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.environ.get('BROWSER_EXECUTABLE') or None)
        page=browser.new_page(viewport={'width':width,'height':900})
        page.goto(app_server+'/?aa_nav=reports')
        page.get_by_role('heading').filter(has_text='Rapportsenter').first.wait_for(timeout=45000)
        assert not page.locator('[data-testid="stException"]').count()
        # The workspace selector is inside a collapsed expander. Verify the
        # destination and its restoration, rather than a hidden radio's role.
        assert 'aa_tab=reports' in page.url
        page.reload()
        page.get_by_role('heading').filter(has_text='Rapportsenter').first.wait_for(timeout=45000)
        assert not page.locator('[data-testid="stException"]').count()
        browser.close()

@pytest.mark.parametrize('width',[1280,375])
@pytest.mark.parametrize('slug,label',[
    ('overview','Oversikt'),('reports','Rapporter'),('orchestrator','Orkestrering og tidsplan'),
    ('autonomous_portfolio','Autonom portefølje'),('learning_portfolio','Læringsportefølje'),
    ('architecture','Ekspertkontroll'),('operations','Varsler og drift'),
    ('strategy_versions','Strategiversjoner'),('strategy_lab','Strategy Lab'),('engine_details','Motorresultater')])
def test_autonomy_workspace_rendering(app_server,width,slug,label):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.environ.get('BROWSER_EXECUTABLE') or None)
        page=browser.new_page(viewport={'width':width,'height':900})
        page.goto(app_server+'/?aa_nav=autonomy&aa_tab='+slug)
        page.get_by_role('heading',name='🧠 Autonomi',exact=True).wait_for(timeout=30000)
        if slug=='overview':page.get_by_text('Ekspertmodus',exact=True).click()
        page.get_by_text('Aktiv arbeidsflate: '+label+'.',exact=False).first.wait_for(timeout=20000)
        page.wait_for_function("document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state') === 'notRunning'",timeout=30000)
        assert not page.locator('[data-testid="stException"]').count()
        browser.close()
