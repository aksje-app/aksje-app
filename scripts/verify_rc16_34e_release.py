from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for path in [
    "app_version.py",
    "autonomous_portfolio.py",
    "controlled_parameter_learning.py",
]:
    ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)

version = (ROOT / "app_version.py").read_text(encoding="utf-8")
autonomy = (ROOT / "autonomous_portfolio.py").read_text(encoding="utf-8")
learning = (ROOT / "controlled_parameter_learning.py").read_text(encoding="utf-8")

assert 'APP_VERSION = "v19.22.0-rc16.34e"' in version
assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34d"' in version

render_start = autonomy.index("def render_autonomous_portfolio")
render_block = autonomy[render_start:]
assert "_render_production_parameter_controls_v1934e" in render_block
assert render_block.index("_render_production_parameter_controls_v1934e") < render_block.index("_render_activation_analysis_v1980")
assert 'with st.expander("Faste parametere"' not in render_block
assert "Parameterlagring aktiv" in autonomy
assert "Endringshistorikk og rollback" in autonomy
assert "Rollback siste parameterendring" in autonomy

for token in (
    "RISK_PROPOSALS_PATH",
    "register_risk_reduction_proposal",
    "resolve_risk_reduction_proposal",
    "pending_risk_proposals",
    "risk_reproposal_min_new_closed_trades",
    "risk_reproposal_min_new_mature_observations",
    "blocked_risk_parameters",
):
    assert token in learning

assert '"paper_statistics": dict(paper_snapshot.get("trade_statistics_pct") or {})' in learning
assert '"learning_statistics": stats' in learning
assert '"PAPER: treffrate' in learning
assert '"PRODUKSJON/LÆRING: Profit Factor' in learning
assert "PAPER – separat resultat" in learning
assert "PRODUKSJON/LÆRING – separat evidens" in learning

for token in ("Godkjenn", "Avvis nå", "Utsett", "Ikke foreslå igjen", "Bekreft beslutning"):
    assert token in autonomy
    assert token in learning

print("rc16.34e Autonomy Parameter & Learning UX gate OK")
