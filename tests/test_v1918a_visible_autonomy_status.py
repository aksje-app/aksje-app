
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_autonomy_overview_imports_status_summary():
    source = (ROOT / "autonomy_overview.py").read_text()
    assert "portfolio_status_summary" in source
    assert "def _render_autonomy_status_box" in source


def test_autonomy_status_box_is_rendered_before_overview_metrics():
    source = (ROOT / "autonomy_overview.py").read_text()
    call = source.index("_render_autonomy_status_box(snapshot)")
    metrics = source.index('top1, top2, top3, top4 = st.columns(4)')
    assert call < metrics


def test_autonomy_status_box_contains_required_user_fields():
    source = (ROOT / "autonomy_overview.py").read_text()
    for text in [
        "Autonomi-runner",
        "Planlegger",
        "Paper trading",
        "Ekte handel",
        "Kandidater mottatt",
        "Teoretiske kjøp",
        "Læringskjøp",
        "Årsak til ingen kjøp",
    ]:
        assert text in source
