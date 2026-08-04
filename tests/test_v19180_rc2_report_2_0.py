from io import BytesIO
import json
from pathlib import Path
from pypdf import PdfReader
import market_intelligence as mi
from app_version import APP_VERSION


def _text(pdf: bytes) -> str:
    return "\n".join((p.extract_text() or "") for p in PdfReader(BytesIO(pdf)).pages)


def test_report_2_0_front_page_and_traceability():
    source = Path('/mnt/data/v19_18_report2_build/morning.json')
    run = json.loads(source.read_text())
    before = [(r.get('ticker'), r.get('investment_score'), r.get('portfolio_action')) for r in run.get('candidates', [])]
    text = _text(mi.build_pdf(run))
    after = [(r.get('ticker'), r.get('investment_score'), r.get('portfolio_action')) for r in run.get('candidates', [])]
    assert APP_VERSION == 'v19.18.0-rc2'
    assert before == after
    for needle in (
        'Executive Summary', 'Prioritert vurderingsrekkefølge 1–3',
        'Markedsdatakvalitet', 'Dokumentasjonsgrad', 'Kildedekning',
        'Beslutningsstyrke', 'Analyse-ID', 'Sporbarhet: program',
    ):
        assert needle in text
    assert text.index('Prioritert vurderingsrekkefølge 1–3') < text.index('Endringer siden forrige rapport')
    assert 'Pålitelighet\n49/100' not in text
