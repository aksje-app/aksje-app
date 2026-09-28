from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in [
    "super_portfolio.py", "pages/super_portfolio.py", "trading_engine.py",
    "scanner_worker.py", "controlled_parameter_learning.py", "app.py", "app_version.py",
]:
    ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)

version = (ROOT / "app_version.py").read_text(encoding="utf-8")
super_src = (ROOT / "super_portfolio.py").read_text(encoding="utf-8")
page_src = (ROOT / "pages/super_portfolio.py").read_text(encoding="utf-8")
trading = (ROOT / "trading_engine.py").read_text(encoding="utf-8")
scanner = (ROOT / "scanner_worker.py").read_text(encoding="utf-8")
learning = (ROOT / "controlled_parameter_learning.py").read_text(encoding="utf-8")
app = (ROOT / "app.py").read_text(encoding="utf-8")

assert 'APP_VERSION = "v19.22.0-rc16.33n"' in version
assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.33m"' in version
assert "RISK_EXIT_REFILL" in super_src
assert "WAITING_FOR_QUALIFIED_CANDIDATE" in super_src
assert "pending_risk_refill_slots" in super_src
assert 'bool(rebalance_gate.get("allowed"))' in super_src
assert "vacancy_diagnostics.json" in super_src
assert "current_positions.json" in super_src
assert "SUPER_PORTFOLIO_DECISION" in super_src
assert "SUPER_PORTFOLIO_STOP_SURVEILLANCE" in super_src
assert "Ledige plasser / kontantandel" in page_src
assert '"decision_snapshot"' in trading
assert "_paper_replay_snapshot" in scanner
assert "paper_counterfactual_replay" in learning
assert "INSUFFICIENT_HISTORICAL_DATA" in learning
assert "UNTESTABLE_LEGACY" in learning
assert "Super Portfolio diagnose" in app
assert "market_reports_rc1633n" in app
print("rc16.33n Exit Refill & Counterfactual Replay gate OK")
