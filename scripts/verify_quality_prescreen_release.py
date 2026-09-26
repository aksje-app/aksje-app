"""Offline release gate for rc16.32zb quality automation."""
from pathlib import Path
import ast

ROOT=Path(__file__).resolve().parents[1]
FILES=[
 "quality_valuation_schedule.py","quality_market_prescreen.py","quality_valuation_store.py",
 "quality_valuation_data.py","quality_valuation_ui.py","pages/overview.py","app_version.py",
]
for name in FILES:
    ast.parse((ROOT/name).read_text(encoding="utf-8"), filename=name)

schedule=(ROOT/"quality_valuation_schedule.py").read_text(encoding="utf-8")
assert "full_market_prescreen(" in schedule
assert "symbols = select_symbols(latest_market)" not in schedule[schedule.index("def run_due_scheduled_screen"):]
assert "SCHEDULED_HOLDING_LIMIT = 5" in schedule
assert "CANDIDATE_BASIS_MAX_AGE_MINUTES = 60" in schedule

prescreen=(ROOT/"quality_market_prescreen.py").read_text(encoding="utf-8")
assert "memory_guard" in prescreen and "deadline_seconds" in prescreen
assert '"coverage_complete":len(rows)==total' in prescreen

store=(ROOT/"quality_valuation_store.py").read_text(encoding="utf-8")
assert "max_age_hours: float = 2.0" in store

data=(ROOT/"quality_valuation_data.py").read_text(encoding="utf-8")
for marker in ("Yahoo info utilgjengelig","Resultatregnskap utilgjengelig","Balanse utilgjengelig","provider_partial"):
    assert marker in data

ui=(ROOT/"quality_valuation_ui.py").read_text(encoding="utf-8")
assert 'st.button("← Tilbake til Marked"' in ui
assert "Markedsgrunnlag:" in ui

overview=(ROOT/"pages"/"overview.py").read_text(encoding="utf-8")
assert '("Kjør kvalitetsvurdering", "quality_valuation", "aa_overview_quality")' in overview
print("GO rc16.32zb: syntax + architecture gates OK")
