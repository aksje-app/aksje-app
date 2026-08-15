from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: validate_rc16_31n_report_reconciliation.py RUN_JSON PORTFOLIO_AFTER OUTPUT_PDF")
    run_path, portfolio_path, output_path = map(Path, sys.argv[1:])
    run = json.loads(run_path.read_text(encoding="utf-8"))
    portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
    from app_version import APP_VERSION
    from autonomous_portfolio import load_parameters
    from market_intelligence import build_pdf
    from report_contracts import ensure_report_document, section_payload
    from report_portfolio_intelligence import assert_portfolio_report_integrity

    params = load_parameters().normalized()
    portfolio["maximum_open_positions"] = int(params.maximum_open_positions)
    portfolio["reserve_cash_pct"] = float(params.reserve_cash_pct)
    portfolio["snapshot_timing"] = "ETTER_AUTONOMI"
    portfolio["snapshot_run_id"] = str(run.get("run_id") or "")
    run["version"] = APP_VERSION
    run["app_version"] = APP_VERSION
    run["autonomous_portfolio_snapshot"] = portfolio
    run.pop("decision_report", None)
    run.pop("report_document", None)
    document = ensure_report_document(run, None)
    accounting = section_payload(document, "portfolio_intelligence", {}) or {}
    assert_portfolio_report_integrity(accounting)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(build_pdf(run))
    result = {
        "version": APP_VERSION,
        "output": str(output_path),
        "open_positions": accounting.get("open_positions"),
        "position_rows": len(accounting.get("positions") or []),
        "portfolio_equity": accounting.get("portfolio_equity"),
        "cash": accounting.get("cash"),
        "invested_pct": accounting.get("invested_pct"),
        "cash_pct": accounting.get("cash_pct"),
        "available_purchase_limit": accounting.get("available_purchase_limit"),
        "reconciliation": accounting.get("reconciliation"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
