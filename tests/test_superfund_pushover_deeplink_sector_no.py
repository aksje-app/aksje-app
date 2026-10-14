from pathlib import Path
from superfund_presentation import norwegian_fund_sector, notification_batch, detail_lines

def test_energy_sector_translated_in_alert_and_detail():
    row={'id':'test:78','name':'State Street SPDR S&P U.S. ENERGY SELECT SECTOR UCITS ETF (Acc)',
         'side':'STERK UKEUTVIKLING','returns':{'yield_1w':7.33},'returns_currency':'EUR'}
    assert norwegian_fund_sector(row)=='Energi – olje og gass (USA)'
    text,count=notification_batch([row])
    assert count==1 and 'Sektor: Energi – olje og gass (USA)' in text
    assert ('Sektor','Energi – olje og gass (USA)') in detail_lines(row)

def test_unknown_sector_not_invented():
    assert norwegian_fund_sector({'name':'Global Equity ETF'}) is None

def test_push_url_uses_one_time_mobile_deep_link():
    source=Path('superfund_runtime.py').read_text()
    assert "'mobile_nav':'superfund'" in source
    assert "'aa_fund':str(first['id'])" in source
