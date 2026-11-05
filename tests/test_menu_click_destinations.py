"""Exercise user clicks from an established session, not just direct URLs."""
import os,time
import pytest
from test_system_revision_browser import app_server
pytestmark=pytest.mark.skipif(os.getenv('SYSTEM_BROWSER_TEST')!='1',reason='Explicit browser gate')

@pytest.mark.parametrize('menu',['sidebar','desktop_header'])
def test_report_click_after_advanced_dashboard(app_server,menu):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.getenv('BROWSER_EXECUTABLE') or None)
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.goto(app_server+'/?aa_nav=dashboard')
        page.get_by_text('Avansert',exact=True).click()
        page.wait_for_function("document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state') === 'notRunning'")
        if menu=='sidebar':page.locator('[data-testid="stSidebar"]').get_by_role('button',name='📚 Rapporter',exact=True).click()
        else:page.locator('.st-key-aa_desktop_nav_reports').get_by_role('button').click()
        page.get_by_role('heading').filter(has_text='Rapportsenter').first.wait_for(timeout=20000)
        assert not page.locator('[data-testid="stException"]').count()
        assert 'aa_tab=reports' in page.url
        browser.close()


@pytest.mark.parametrize('route,heading',[('reports','Rapportsenter'),('autonomy','Autonomi'),('market','Marked'),('quality_valuation','Marked')])
def test_menu_destination_is_independent_of_home_market_provider(app_server,route,heading):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.getenv('BROWSER_EXECUTABLE') or None)
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.goto(app_server+'/?aa_nav='+route+'&audit_fail_banner=1')
        page.get_by_role('heading').filter(has_text=heading).first.wait_for(timeout=20000)
        assert 'home market provider unavailable' not in page.locator('body').inner_text()
        assert not page.locator('[data-testid="stException"]').count()
        assert not page.locator('.st-key-aa_mobile_nav_native').is_visible()
        browser.close()

@pytest.mark.parametrize('width',[390,1440])
def test_main_menus_open_their_content_with_one_click(app_server,width):
    from playwright.sync_api import sync_playwright
    routes=[('reports','Rapportsenter'),('autonomy','Autonomi'),('portfolio','Autonomi'),
            ('market','Marked'),('quality','Marked'),('superfund','Superfond'),('operations','Driftssenter'),('overview','God')]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.getenv('BROWSER_EXECUTABLE') or None)
        page=browser.new_page(viewport={'width':width,'height':950})
        from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
        finished=[]
        def observe(ws):
            def receive(frame):
                if isinstance(frame,bytes):
                    msg=ForwardMsg();msg.ParseFromString(frame)
                    if msg.WhichOneof('type')=='script_finished' and msg.script_finished==ForwardMsg.FINISHED_SUCCESSFULLY:finished.append(True)
            ws.on('framereceived',receive)
        page.on('websocket',observe)
        def click_and_wait(button):
            before=len(finished);button.click();deadline=time.monotonic()+20
            while len(finished)<=before and time.monotonic()<deadline:page.wait_for_timeout(50)
            assert len(finished)>before,'Menu click did not finish a render'
        page.goto(app_server+'/?aa_nav=dashboard')
        page.get_by_role('heading').filter(has_text='God').first.wait_for(timeout=20000)
        for slug,heading in routes:
            started=time.monotonic()
            if width>760:
                click_and_wait(page.locator('.st-key-aa_desktop_nav_'+slug).get_by_role('button'))
            elif slug in {'reports','autonomy','market','operations'}:
                click_and_wait(page.locator('.st-key-aa_mobile_nav_more').get_by_role('button'))
                click_and_wait(page.locator('.st-key-aa_mobile_more_'+slug).get_by_role('button'))
            else:
                click_and_wait(page.locator('.st-key-aa_mobile_nav_'+slug).get_by_role('button'))
            page.get_by_role('heading').filter(has_text=heading).first.wait_for(timeout=20000)
            page.wait_for_function("document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state') === 'notRunning'",timeout=20000)
            assert not page.locator('[data-testid="stException"]').count(),slug
            if slug=='quality':assert 'Kvalitet og prising' in page.locator('.st-key-market_room_view_v1863cb').inner_text()
            print(f'MENU_CLICK width={width} destination={slug} seconds={time.monotonic()-started:.3f}')
        browser.close()
