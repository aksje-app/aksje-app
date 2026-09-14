"""Replay a bounded learning diagnostic package against RC16.31am contracts."""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from typing import Any, Mapping


def _f(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def audit(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    with zipfile.ZipFile(source) as archive:
        diagnostics = json.loads(archive.read("learning/LEARNING_DIAGNOSTICS.json"))
        status = json.loads(archive.read("status.json"))
    sells = [row for row in diagnostics.get("recent_trades") or [] if str(row.get("action") or "").upper() == "SELL"]
    promoted = [row for row in sells if "PROMOTERT" in str(row.get("reason") or "").upper()]
    natural = [row for row in sells if row not in promoted]
    chain = status.get("chain") if isinstance(status.get("chain"), Mapping) else {}
    learning_stage = next((row for row in chain.get("stages") or [] if row.get("name") == "CONTROLLED_LEARNING"), {})
    old_evaluation = dict((learning_stage.get("detail") or {}).get("evaluation") or {})
    account_metrics = dict((next((row for row in chain.get("stages") or [] if row.get("name") == "AUTONOMOUS_PORTFOLIO"), {}).get("detail") or {}).get("learning_account_metrics") or {})
    legacy_performance = dict(diagnostics.get("performance") or {})
    errors: list[str] = []
    if len(sells) < 15:
        errors.append("For få avsluttede læringsutfall til hypoteseanalyse")
    if int(old_evaluation.get("closed_trades") or 0) >= len(sells):
        errors.append("Replay beviser ikke den historiske læringstellingen")
    if abs(_f(legacy_performance.get("return_pct"))) > 100:
        errors.append("Kanonisk observasjonsavkastning er implausibel")
    return {
        "ok": not errors,
        "source": source.name,
        "errors": errors,
        "historical_ordinary_count": int(old_evaluation.get("closed_trades") or 0),
        "recovered_learning_exit_count": len(sells),
        "usable_exit_count_after_rc16_31am": int(old_evaluation.get("closed_trades") or 0) + len(sells),
        "natural_learning_exits": len(natural),
        "promoted_learning_exits": len(promoted),
        "natural_average_return_pct": round(sum(_f(row.get("pnl_pct")) for row in natural) / len(natural), 4) if natural else 0.0,
        "promoted_average_return_pct": round(sum(_f(row.get("pnl_pct")) for row in promoted) / len(promoted), 4) if promoted else 0.0,
        "historical_bad_account_return_pct": _f(account_metrics.get("return_pct")),
        "canonical_observation_return_pct": _f(legacy_performance.get("return_pct")),
        "production_parameters_changed": False,
        "real_transactions": False,
    }


if __name__ == "__main__":
    result = audit(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)

