"""Actual browser layout checks; enabled explicitly by the release gate."""
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen
import pytest

pytestmark=pytest.mark.skipif(os.getenv('SF_BROWSER_TEST')!='1',reason='Browser checks run in release CI')


@pytest.fixture(scope='module')
def server():
    env={**os.environ,'PYTHONPATH':'.'}
    process=subprocess.Popen([sys.executable,'-m','streamlit','run','scripts/superfund_ui_fixture.py','--server.port=8599','--server.headless=true','--browser.gatherUsageStats=false'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                if urlopen('http://localhost:8599/_stcore/health',timeout=1).status==200:break
            except Exception:time.sleep(.2)
        else:raise AssertionError('Fixture server did not start')
        yield 'http://localhost:8599'
    finally:process.terminate();process.wait(timeout=10)


@pytest.mark.parametrize('width',[375,430,1280])
def test_superfund_all_menus_wrap_without_overlap(server,width):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        p=browser.new_page(viewport={'width':width,'height':900},device_scale_factor=1)
        p.goto(server)
        p.get_by_role('heading',name='Superfondportefølje',exact=True).wait_for()
        p.locator('.sf-card').first.wait_for()
        # Streamlit renders collapsed content too; expand the complete menu set.
        for label in ['Kandidater','Rapporter og nedlastinger','Nyheter og kilder','Læring og skygge','Parametre','Diagnoser']:
            p.locator('[data-testid="stExpander"] summary').filter(has_text=label).first.click()
        p.get_by_role('heading',name='Topp 25 · grunnkrav oppfylt',exact=True).wait_for()
        problems=p.evaluate('''() => {
          const errors=[];
          for (const card of document.querySelectorAll('.sf-card')) {
            if (!card.getClientRects().length) continue;
            const box=card.getBoundingClientRect();
            if (box.right>innerWidth+2 || box.left< -2) errors.push('card outside viewport');
            let bottom=card.querySelector('h3').getBoundingClientRect().bottom;
            for(const fact of card.querySelectorAll('.sf-fact')) {
              const r=fact.getBoundingClientRect();
              if(r.top<bottom-1) errors.push('overlapping facts');
              if(r.bottom>box.bottom+1) errors.push('fact outside card');
              bottom=r.bottom;
            }
          }
          for (const caption of document.querySelectorAll('.st-key-superfund_page [data-testid="stCaptionContainer"]')) {
            if(caption.getClientRects().length && caption.scrollHeight>caption.clientHeight+2) errors.push('caption clipped');
          }
          for (const a of document.querySelectorAll('.st-key-superfund_page [data-testid="stLinkButton"] a')) {
            if(!a.getClientRects().length)continue;
            const style=getComputedStyle(a);
            if(style.color===style.backgroundColor) errors.push('invisible link');
          }
          return errors;
        }''')
        Path('dist/browser').mkdir(parents=True,exist_ok=True)
        p.screenshot(path=f'dist/browser/superfund-{width}.png',full_page=True)
        assert not problems,problems
        assert p.locator('.sf-card').get_by_text('1725.7',exact=True).count()==1
        browser.close()
