from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for path in [
    "app_version.py",
    "super_portfolio.py",
    "controlled_parameter_learning.py",
    "autonomous_portfolio.py",
]:
    ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)

version = (ROOT / "app_version.py").read_text(encoding="utf-8")
portfolio = (ROOT / "super_portfolio.py").read_text(encoding="utf-8")
learning = (ROOT / "controlled_parameter_learning.py").read_text(encoding="utf-8")
autonomy = (ROOT / "autonomous_portfolio.py").read_text(encoding="utf-8")

version_lines = {line.strip() for line in version.splitlines()}
assert (
    'APP_VERSION = "v19.22.0-rc16.34c"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34d"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34e"' in version_lines
)
if 'APP_VERSION = "v19.22.0-rc16.34c"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34b"' in version_lines
elif 'APP_VERSION = "v19.22.0-rc16.34d"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34c"' in version_lines
else:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34d"' in version_lines

assert "Never renormalize capped weights" not in portfolio  # implementation, not prose dependency
assert "remaining = 100.0" in portfolio
assert "weight > cap + eps" in portfolio
assert "HARD_POSITION_CAP" in portfolio
assert 'pos["target_weight_pct"] = capped_weight' in portfolio
assert "overskytende beholdes som kontanter" in portfolio

assert "RESULTAT: Paper-porteføljen" in learning
assert "RISIKO: Drawdown" in learning
assert "NESTE STEG:" in learning
assert "HANDLING:" in learning
assert "Teknisk:" in learning

assert "KONTROLL:" in autonomy
assert "HVA SKJEDDE:" in autonomy
assert "KONTANTER:" in autonomy
assert "Ingen manuell handling nødvendig" in autonomy

assert "SUPERPORTEFØLJE – STOPPKONTROLL" in portfolio
assert "stoppsituasjonen er forbedret – ingen handling" in portfolio

print("rc16.34c hard position cap & plain reports gate OK")
