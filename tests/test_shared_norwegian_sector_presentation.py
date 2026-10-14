from norwegian_report_language import sector_label
from superfund_presentation import norwegian_fund_sector

def test_major_sectors_in_norwegian():
    assert sector_label('Information Technology') == 'Teknologi'
    assert sector_label('Consumer Discretionary') == 'Syklisk forbruk'
    assert sector_label('Health Care') == 'Helse'
    assert sector_label('Energy') == 'Energi'
    assert sector_label('Utilities') == 'Forsyning'
    assert sector_label('Chemicals') == 'Kjemikalier'
    assert sector_label('Sector: Financials') == 'Sektor: Finans'

def test_unrecognized_value_keeps_its_original_label():
    assert sector_label('Specialist Industry') == 'Specialist Industry'

def test_fund_sector_presentation_is_translated():
    assert norwegian_fund_sector({'name':'Other Fund', 'category':'Information Technology'}) == 'Teknologi'
    assert norwegian_fund_sector({'name':'Other Fund', 'category':'Miscellaneous'}) is None
    assert norwegian_fund_sector({'name':'State Street SPDR S&P U.S. ENERGY SELECT SECTOR UCITS ETF (Acc)'}) == 'Energi – olje og gass (USA)'
