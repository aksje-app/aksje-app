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
            class AppAddress(str):
                pass
            address = AppAddress(base)
            address.runtime_root = Path(runtime)
            yield address
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


@pytest.mark.parametrize('width', [1280, 375])
@pytest.mark.parametrize('route', [
    'dashboard', 'analysis', 'top_picks', 'long_engine', 'ai', 'fx_alerts',
    'market', 'super_portfolio', 'superfund', 'system', 'quality_valuation',
    'quality_reports', 'drift_center', 'jobs', 'approvals', 'operations',
])
def test_active_routes_and_control_inventory(app_server, width, route, tmp_path):
    """Open active routes and every rendered tab; inventory is not an action pass."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get('BROWSER_EXECUTABLE') or None)
        page = browser.new_page(viewport={'width': width, 'height': 900}, accept_downloads=True)
        from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
        finished = []
        def observe_socket(ws):
            def receive(frame):
                if not isinstance(frame, bytes):
                    return
                message = ForwardMsg()
                message.ParseFromString(frame)
                if message.WhichOneof('type') == 'script_finished' and message.script_finished == ForwardMsg.FINISHED_SUCCESSFULLY:
                    finished.append(True)
            ws.on('framereceived', receive)
        page.on('websocket', observe_socket)
        import uuid
        probe = uuid.uuid4().hex
        page.goto(app_server + '/?aa_nav=' + route + '&audit_probe=' + probe)
        receipt = app_server.runtime_root / ('render-complete-' + probe + '.json')
        deadline = time.monotonic() + 30
        while not receipt.exists() and time.monotonic() < deadline:
            assert not page.locator('[data-testid="stException"]').count(), page.locator('[data-testid="stException"]').all_text_contents()
            page.wait_for_timeout(100)
        assert receipt.exists(), 'App script did not complete: ' + route
        deadline = time.monotonic() + 30
        while not finished and time.monotonic() < deadline:
            page.wait_for_timeout(100)
        assert finished, 'Browser did not receive the completed rendering: ' + route
        # React applies websocket deltas asynchronously. The navigation shell
        # must have real text before taking the control inventory.
        if width < 768:
            page.locator('.st-key-aa_mobile_nav_overview button').wait_for(state='attached', timeout=30000)
        else:
            page.get_by_role('button', name='Logg ut', exact=True).wait_for(state='attached', timeout=30000)
        page.wait_for_timeout(300)
        page.wait_for_function("document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state') === 'notRunning'", timeout=45000)
        assert not page.locator('[data-testid="stException"]').count(), page.locator('[data-testid="stException"]').all_text_contents()
        assert page.get_by_role('heading').count(), 'Expected actual page content'
        # Tabs use real Streamlit callbacks/reruns, including panels hidden at first render.
        tabs = page.get_by_role('tab').all_text_contents()
        for label in dict.fromkeys(tabs):
            tab = page.get_by_role('tab', name=label, exact=True).first
            if tab.is_visible():
                tab.click()
                page.wait_for_function("document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state') === 'notRunning'", timeout=45000)
                assert not page.locator('[data-testid="stException"]').count(), label
        controls = page.evaluate('''() => [...document.querySelectorAll('button,input,select,a,[role="combobox"],[role="slider"]')].map(e => ({tag:e.tagName,role:e.getAttribute('role'),label:e.innerText||e.getAttribute('aria-label')||e.getAttribute('placeholder')||e.name,disabled:!!e.disabled,visible:!!e.getClientRects().length}))''')
        destination = Path(os.environ.get('AUDIT_CONTROL_OUTPUT', str(tmp_path)))
        destination.mkdir(parents=True, exist_ok=True)
        (destination / f'{route}-{width}.json').write_text(json.dumps({'route':route,'width':width,'url':page.url,'headings':page.get_by_role('heading').all_text_contents(),'tabs_executed':tabs,'controls_observed':controls},ensure_ascii=False,indent=2))
        page.screenshot(path=str(destination / f'{route}-{width}.png'), full_page=True)
        browser.close()


@pytest.mark.parametrize('width', [1280, 375])
def test_currency_settings_save_and_reload(app_server, width):
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.environ.get('BROWSER_EXECUTABLE') or None)
        page=browser.new_page(viewport={'width':width,'height':900})
        page.goto(app_server+'/?aa_nav=fx_alerts')
        page.get_by_role('heading',name='Varseloppsett',exact=True).wait_for(timeout=30000)
        page.get_by_label('Nedre grense',exact=True).fill('1.8123')
        page.get_by_label('Øvre grense',exact=True).fill('2.0123')
        for label in ('Aktiv', 'Send Pushover ved brudd'):
            if page.get_by_role('checkbox',name=label,exact=True).is_checked():
                page.get_by_text(label,exact=True).click()
        page.get_by_role('button',name='Lagre varsel',exact=True).click()
        page.get_by_text('Valutavarselet er lagret.',exact=False).wait_for(timeout=30000)
        page.reload()
        expect(page.get_by_label('Nedre grense',exact=True)).to_have_value('1.8123',timeout=30000)
        expect(page.get_by_label('Øvre grense',exact=True)).to_have_value('2.0123')
        assert not page.get_by_role('checkbox',name='Aktiv',exact=True).is_checked()
        assert not page.get_by_role('checkbox',name='Send Pushover ved brudd',exact=True).is_checked()
        assert not page.locator('[data-testid="stException"]').count()
        browser.close()


@pytest.mark.parametrize('width', [1280, 375])
def test_system_settings_and_full_stop_preserve_execution_block(app_server, width):
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.environ.get('BROWSER_EXECUTABLE') or None)
        page=browser.new_page(viewport={'width':width,'height':900})
        page.goto(app_server+'/?aa_nav=system')
        page.get_by_label('Søkintervall minutter',exact=True).wait_for(timeout=30000)
        if page.get_by_role('checkbox',name='Bakgrunnssøk aktiv',exact=True).is_checked():
            page.get_by_text('Bakgrunnssøk aktiv',exact=True).click()
        page.get_by_label('Søkintervall minutter',exact=True).fill('19')
        page.get_by_role('button',name='💾 Lagre søk/cron som ventende',exact=True).click()
        page.get_by_text('Søk/cron lagret som ventende',exact=False).wait_for(timeout=30000)
        page.reload()
        expect(page.get_by_label('Søkintervall minutter',exact=True)).to_have_value('19',timeout=30000)
        assert not page.get_by_role('checkbox',name='Bakgrunnssøk aktiv',exact=True).is_checked()
        page.get_by_role('button',name='⛔ Full stopp / ferie',exact=True).click()
        page.get_by_role('button',name='🔓 Slå av Full stopp',exact=True).wait_for(timeout=30000)
        expect(page.get_by_role('button',name='⚡ Kjør auto-kjøp nå',exact=True)).to_be_disabled()
        page.reload()
        page.get_by_role('button',name='🔓 Slå av Full stopp',exact=True).click(timeout=30000)
        page.get_by_role('button',name='⛔ Full stopp / ferie',exact=True).wait_for(timeout=30000)
        assert not page.locator('[data-testid="stException"]').count()
        browser.close()
