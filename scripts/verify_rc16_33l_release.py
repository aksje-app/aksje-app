from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / "super_portfolio.py").read_text(encoding="utf-8")
version = (ROOT / "app_version.py").read_text(encoding="utf-8")
ast.parse(src, filename="super_portfolio.py")

assert ('APP_VERSION = "v19.22.0-rc16.33l"' in version
        or 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.33l"' in version
        or "rc16.33l" in version)
assert "PROFIT_PROTECT_TRIGGER_PCT = 2.0" in src
assert "PROFIT_RETENTION_2_3_PCT = 40.0" in src
assert "PROFIT_RETENTION_3_5_PCT = 55.0" in src
assert "PROFIT_RETENTION_5_8_PCT = 65.0" in src
assert "PROFIT_RETENTION_8_PLUS_PCT = 70.0" in src
assert '"PROFIT_PROTECTION_EXIT"' in src
assert '"CONFIRMED_PROFIT_PROTECTION_EXIT"' in src
assert '"mfe_retained_pct"' in src
assert '"profit_giveback_pct"' in src
assert "gevinstbeskyttelse fra +2% MFE" in src
print("rc16.33l profit-protection gate OK")
