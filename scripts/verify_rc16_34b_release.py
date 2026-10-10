from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for path in [
    "app.py",
    "app_version.py",
    "navigation_state.py",
    "pages/overview.py",
    "pages/super_portfolio.py",
    "ui_library/shell.py",
    "workspace_layout.py",
]:
    ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)

version = (ROOT / "app_version.py").read_text(encoding="utf-8")
app = (ROOT / "app.py").read_text(encoding="utf-8")
overview = (ROOT / "pages" / "overview.py").read_text(encoding="utf-8")
portfolio = (ROOT / "pages" / "super_portfolio.py").read_text(encoding="utf-8")
shell = (ROOT / "ui_library" / "shell.py").read_text(encoding="utf-8")
layout = (ROOT / "workspace_layout.py").read_text(encoding="utf-8")
navigation = (ROOT / "navigation_state.py").read_text(encoding="utf-8")

version_lines = {line.strip() for line in version.splitlines()}
assert (
    'APP_VERSION = "v19.22.0-rc16.34b"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34c"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34d"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34e"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34f"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34g"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34h"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34i"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34j"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34k"' in version_lines
    or 'APP_VERSION = "v19.22.0-rc16.34l"' in version_lines
)
if 'APP_VERSION = "v19.22.0-rc16.34b"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34a"' in version_lines
elif 'APP_VERSION = "v19.22.0-rc16.34c"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34b"' in version_lines
elif 'APP_VERSION = "v19.22.0-rc16.34d"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34c"' in version_lines
elif 'APP_VERSION = "v19.22.0-rc16.34e"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34d"' in version_lines
elif 'APP_VERSION = "v19.22.0-rc16.34f"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34e"' in version_lines
elif 'APP_VERSION = "v19.22.0-rc16.34g"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34f"' in version_lines
elif 'APP_VERSION = "v19.22.0-rc16.34h"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34g"' in version_lines
elif 'APP_VERSION = "v19.22.0-rc16.34i"' in version_lines:
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34h"' in version_lines
else:
    assert ('PREVIOUS_APP_VERSION = "v19.22.0-rc16.34k"' if 'APP_VERSION = "v19.22.0-rc16.34l"' in version_lines else 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34j"' if 'APP_VERSION = "v19.22.0-rc16.34k"' in version_lines else 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.34i"') in version_lines

assert '"super_portfolio":"market"' in shell
assert '"🌍 Super Portfolio": "market"' in navigation
assert '("🌍 Super Portfolio", _render_super_portfolio_market_panel_v1934b)' in layout

direct_marker = "# RC16.34b: Super Portfolio is a true first-class Market page."
assert direct_marker in app
direct = app.index(direct_marker)
overview_marker = app.index("# A+B Overview is a true replacement page.")
assert direct < overview_marker
direct_block = app[direct:overview_marker]
assert '_direct_sp_panel_v1934b == "🌍 Super Portfolio"' in direct_block
assert "render_super_portfolio as _render_super_portfolio_direct_v1934b" in direct_block
assert "st.stop()" in direct_block

assert '"position_rows": position_rows' in overview
assert 'st_module.markdown("### Porteføljen nå")' in overview
assert '"Verdi NOK": row.get("value_nok")' in overview
assert '"P/L NOK": row.get("pnl_nok")' in overview
assert 'st_module.button("🌍 Åpne hele Super Portfolio"' in overview

assert 'st.markdown("### 🚦 Hva skjer nå?")' in portfolio
assert '"Verdi NOK": round(position_value,0)' in portfolio
assert '"P/L NOK": round(position_pnl_nok,0)' in portfolio
assert 'st.markdown("### 📈 Utvikling – totalt")' in portfolio
assert 'st.markdown("### 📉 Utvikling – alle aksjer")' in portfolio
assert 'st.markdown("### 🧮 Hvem skaper resultatet?")' in portfolio
assert 'with st.expander("🧾 Innsiderkontroll – lesbar visning"' in portfolio

front_start = app.index("def render_super_portfolio_front_window_v1932c")
front_end = app.index("def cached_auto_rank_market", front_start)
front = app[front_start:front_end]
assert "event_lines" not in front
assert 'st.markdown("**Hva krever oppmerksomhet?**")' in front
assert "st.error(" in front and "st.warning(" in front
assert "Porteføljeverdi NOK" in front

print("rc16.34b Super Portfolio E2E gate OK")
