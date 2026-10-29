"""UI contract: new active portfolio cannot inherit old model losses."""
from pathlib import Path


def test_superfund_primary_portfolio_uses_verified_new_period():
    src = Path("pages/superfund.py").read_text(encoding="utf-8")
    assert "new_period_metrics('super_portfolio')" in src
    assert "Verifisert porteføljeverdi NOK" in src
    assert "economic_period_id" in src
    assert "render_overview(st,s)" not in src
    assert "st.metric('Modellportefølje NOK'" not in src
    assert "st.metric('Avkastning'," not in src
    assert "NOK-regnskap – Superfonds eksisterende modell" not in src


def test_new_period_metrics_are_authoritative():
    src = Path("services/production_routing.py").read_text(encoding="utf-8")
    assert "def metrics(family,*,storage=None)" in src
    assert "verified['verified_nav']" in src
    assert "verified['verified_net_return_pct']" in src
    assert "economic_period_id=chosen['pointer']['period_id']" in src
