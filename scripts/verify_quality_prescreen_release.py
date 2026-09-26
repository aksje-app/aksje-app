"""Self-contained release gate for full-market prescreen.

Run: python scripts/verify_quality_prescreen_release.py
No network, database or third-party provider is required.
"""
from __future__ import annotations
import ast
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "quality_market_prescreen.py"

# Gate 1: exact production source must parse.
source = SOURCE.read_text(encoding="utf-8")
ast.parse(source, filename=str(SOURCE))

# Gate 2: import exact production module with provider dependency stubbed.
fake_provider = types.ModuleType("candidate_market_data")
calls = []

def fake_enrich(rows, **kwargs):
    assert rows and all(isinstance(row, dict) and row.get("ticker") for row in rows)
    calls.extend(row["ticker"] for row in rows)
    return [{
        "ticker": row["ticker"],
        "last_price": 100.0 + i,
        "trailing_pe": 14.0 + (i % 5),
        "roe": 15.0 + (i % 20),
        "debt_to_equity": 20.0,
        "earnings_growth": float(i % 12),
        "revenue_growth": float(i % 9),
        "momentum_score": 40.0 + (i % 30),
        "trend_score": 45.0 + (i % 25),
        "data_fetch_status": "OK",
        "raw_fields_available": ["price", "fundamentals"],
    } for i, row in enumerate(rows)]

fake_provider.enrich_candidate_rows = fake_enrich
sys.modules["candidate_market_data"] = fake_provider
sys.path.insert(0, str(ROOT))
import quality_market_prescreen as q

# Gate 3: same Norway universe size observed in production screenshot.
universe = [f"NO{i:03d}.OL" for i in range(295)]
progress = []
result = q.full_market_prescreen(
    universe,
    finalist_limit=20,
    chunk_size=60,
    progress=lambda done, total, ticker: progress.append((done, total, ticker)),
)
assert result["universe_count"] == 295
assert result["examined_count"] == 295
assert result["usable_count"] == 295
assert result["failed_count"] == 0
assert len(result["finalists"]) == 20
assert len(calls) == 295 and calls == universe
assert progress[0][0:2] == (1, 295)
assert progress[-1][0:2] == (295, 295)
assert len(set(result["finalists"])) == 20
print("GO: syntax OK; 295/295 examined; 20 finalists; row contract OK")
