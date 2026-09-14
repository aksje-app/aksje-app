"""Static release audit for every Pushover producer and Fresh Trend contract."""
from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def audit() -> dict:
    producers = []
    direct_http = []
    parse_errors = []
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in {"tests", ".pytest_cache", "__pycache__"} for part in path.parts):
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except Exception as exc:
            parse_errors.append(f"{path.relative_to(ROOT)}: {type(exc).__name__}: {exc}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if name == "send_pushover_alert":
                producers.append({"file": str(path.relative_to(ROOT)), "line": node.lineno})
            if name == "post" and node.args and isinstance(node.args[0], ast.Constant) and "pushover.net" in str(node.args[0].value):
                direct_http.append({"file": str(path.relative_to(ROOT)), "line": node.lineno})

    expected_contract = {
        "notifier.py": ("fit_pushover_message", "PUSHOVER_MESSAGE_LIMIT", "_recent_duplicate"),
        "fresh_trend_monitor.py": ("_stabilize_progress", "rs_reference_scope", "invariant_errors", "datadekning", "Retning nå:"),
        "trend_intelligence.py": ("FULL_STAGE1_UNIVERSE", "rs_full_stage1_universe", "volume_bar_complete"),
        "candidate_market_data.py": ("volume_comparison_basis", "ikke tidsjustert", "market_bar_interval"),
    }
    missing = []
    for filename, needles in expected_contract.items():
        source = (ROOT / filename).read_text(encoding="utf-8")
        missing.extend(f"{filename}: {needle}" for needle in needles if needle not in source)
    illegal_http = [row for row in direct_http if row["file"] != "notifier.py"]
    errors = parse_errors + missing + [f"Direkte Pushover HTTP utenom notifier: {row}" for row in illegal_http]
    return {
        "ok": not errors,
        "producer_count": len(producers),
        "producers": producers,
        "central_http_calls": direct_http,
        "errors": errors,
        "contracts": {
            "single_sender": not illegal_http,
            "line_safe_compaction": not any("fit_pushover_message" in value for value in missing),
            "fresh_trend_invariants": not any("fresh_trend_monitor.py" in value for value in missing),
            "full_universe_rs": not any("trend_intelligence.py" in value for value in missing),
            "honest_volume_basis": not any("candidate_market_data.py" in value for value in missing),
        },
    }


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
