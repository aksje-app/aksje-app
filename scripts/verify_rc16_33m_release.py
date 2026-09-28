from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in ["paper_risk_policy.py","trading_engine.py","scanner_worker.py","controlled_parameter_learning.py","app_version.py"]:
    ast.parse((ROOT/path).read_text(encoding="utf-8"), filename=path)

version=(ROOT/"app_version.py").read_text(encoding="utf-8")
trading=(ROOT/"trading_engine.py").read_text(encoding="utf-8")
scanner=(ROOT/"scanner_worker.py").read_text(encoding="utf-8")
learning=(ROOT/"controlled_parameter_learning.py").read_text(encoding="utf-8")
assert 'APP_VERSION = "v19.22.0-rc16.33m"' in version
assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.33l"' in version
assert "MAX_TRAILING_STOP_PCT" in trading
assert "strict_profit_protection_levels" in trading
assert "select_replacement_position" in scanner
assert "_closed_paper_trades" in learning
assert "Autonomi: daglig Paper + læring" in learning
print("rc16.33m Paper Learning Recovery gate OK")
