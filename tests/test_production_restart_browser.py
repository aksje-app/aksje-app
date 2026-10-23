"""PC/mobile and actual exports for approved production-mode NOK accounts."""
import os,socket,subprocess,sys,time
from urllib.request import urlopen
import pytest
from test_production_restart import ready,activate
from test_revision_trade_postgres import pg
from test_simulation_restart import sources,certificate

pytestmark=pytest.mark.skipif(os.getenv('SYSTEM_BROWSER_TEST')!='1',reason='Explicit isolated browser gate')


@pytest.fixture
def browser_server(ready):
    r=ready
    for family in ('paper','autonomy','super_portfolio'):activate(r,family)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base='http://127.0.0.1:'+str(port)
    env={**os.environ,'DATABASE_URL':r['pg'].database_url,'STORAGE_MODE':'postgres','ALLOW_LOCAL_STORAGE_FALLBACK':'false',
         'APP_RUNTIME_ROOT':str(r['pg'].base_dir/'browser-runtime'),'AUTH_DATABASE_URL':'','AUTH_REQUIRE_PERSISTENT':'false'}
    process=subprocess.Popen([sys.executable,'-m','streamlit','run','scripts/production_restart_ui_fixture.py',
        '--server.port='+str(port),'--server.headless=true','--browser.gatherUsageStats=false'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                if urlopen(base+'/_stcore/health',timeout=1).status==200:break
            except Exception:time.sleep(.2)
        else:raise AssertionError('Production-mode fixture did not start')
        yield base
    finally:process.terminate();process.wait(timeout=10)


@pytest.mark.parametrize('width',[390,1440])
@pytest.mark.parametrize('family',['paper','autonomy','super_portfolio'])
def test_approved_nok_navigation_graphs_and_downloads(browser_server,family,width,tmp_path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.getenv('BROWSER_EXECUTABLE') or None,args=['--no-sandbox'])
        try:
            page=browser.new_page(viewport={'width':width,'height':950},accept_downloads=True)
            page.goto(browser_server);page.get_by_text('Valgt NOK-konto:',exact=False).wait_for(timeout=30000)
            page.get_by_role('combobox').first.click()
            page.get_by_role('option',name=family,exact=True).click()
            label={'paper':'Paper Trading','autonomy':'Autonomi','super_portfolio':'Superporteføljen'}[family]
            page.get_by_role('heading',name=label+' – dokumentert NOK-periode',exact=True).wait_for(timeout=30000)
            page.locator('.st-key-'+family+'_restart_csv').get_by_role('button').wait_for(timeout=30000)
            assert page.locator('[data-testid="stException"]').count()==0
            page.locator('[data-testid*="VegaLite"]').first.wait_for(timeout=30000)
            for fmt in ('CSV','XLSX','PDF','ZIP'):
                with page.expect_download(timeout=30000) as pending:
                    page.locator('.st-key-'+family+'_restart_'+fmt.lower()).get_by_role('button',name='Last ned valgt NOK-periode ('+fmt+')',exact=True).click()
                download=pending.value;assert download.suggested_filename.startswith(family+'_');dest=tmp_path/download.suggested_filename;download.save_as(dest)
                assert dest.stat().st_size>50
                if fmt=='CSV':assert family in dest.read_text(encoding='utf-8-sig')
                if fmt=='PDF':assert dest.read_bytes().startswith(b'%PDF')
                if fmt in ('XLSX','ZIP'):assert dest.read_bytes().startswith(b'PK')
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2')
        finally:
            browser.close()
