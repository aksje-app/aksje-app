import ast
from html import escape
from pathlib import Path
from research_readable_layout import lines

ROOT=Path(__file__).resolve().parents[1]

class Fake:
    def __init__(self): self.output=[]
    def markdown(self, html, **kwargs): self.output.append(html)

def test_text_is_in_flow_blocks_and_escaped():
    fake=Fake()
    lines(fake, "Første linje", "Andre linje <tag>")
    html=fake.output[0]
    assert html.count("display:block") == 2
    assert "min-height:1.6em" in html
    assert "height:auto" in html
    assert "&lt;tag&gt;" in html
    assert "<tag>" not in html

def test_readable_panels_compile_and_use_lines():
    for path in ("research_findings_dashboard.py","strategy_history_progress_view.py"):
        source=(ROOT/path).read_text(encoding="utf-8")
        ast.parse(source)
        assert "from research_readable_layout import lines" in source
        assert "lines(st," in source
