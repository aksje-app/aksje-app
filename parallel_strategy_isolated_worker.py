"""Killable subprocess for observational parallel-strategy evaluation."""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path


def main() -> int:
    input_path, output_path, error_path = map(Path, sys.argv[1:4])
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        from autonomous_portfolio import AutonomousParameters
        from services.parallel_strategy_service import get_parallel_strategy_service

        params = AutonomousParameters(**dict(payload.get("autonomy_parameters") or {})).normalized()
        result = get_parallel_strategy_service().evaluate_snapshot(
            dict(payload.get("snapshot") or {}),
            run_id=str(payload.get("run_id") or ""),
            source=str(payload.get("source") or "autonomy_cycle_parallel"),
            purpose="AUTONOMY_CYCLE_PARALLEL",
            portfolio_states=dict(payload.get("portfolio_states") or {}),
            families=list(payload.get("families") or ["technical", "autonomy"]),
            context_metadata={"autonomy_parameters": params},
        )
        output_path.write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")
        return 0
    except Exception as exc:
        error_path.write_text(json.dumps({
            "error": f"{type(exc).__name__}: {str(exc)[:2000]}",
            "traceback": traceback.format_exc(limit=20)[-12000:],
        }, ensure_ascii=False), encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
