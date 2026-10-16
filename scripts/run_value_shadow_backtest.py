"""Offline CLI for point-in-time value Shadow comparison.

Usage:
    python scripts/run_value_shadow_backtest.py input.json
Input: JSON list of historical candidate samples. Output: JSON to stdout.
No network calls, database access, portfolio writes or trade execution.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from services.value_historical_comparison import compare_value_shadow_history


def run(path: str) -> dict:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        return {"status": "BACKTEST_NOT_VERIFIABLE",
                "error": type(exc).__name__, "comparisons": [],
                "shadow_only": True, "can_authorize_buy": False}
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        return {"status": "BACKTEST_NOT_VERIFIABLE", "error": "INVALID_INPUT_SCHEMA",
                "comparisons": [], "shadow_only": True, "can_authorize_buy": False}
    return compare_value_shadow_history(payload)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/run_value_shadow_backtest.py input.json", file=sys.stderr)
        sys.exit(2)
    result = run(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["status"] == "DESCRIPTIVE_COMPARISON_ONLY" else 1)
