from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _function_names(name: str) -> set[str]:
    tree = ast.parse(_source(name))
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _load_standalone_functions(name: str, wanted: set[str]) -> dict:
    tree = ast.parse(_source(name))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    module = ast.Module(body=selected, type_ignores=[])
    namespace = {"Any": object, "Mapping": dict, "Sequence": list}
    exec(compile(ast.fix_missing_locations(module), name, "exec"), namespace)
    return namespace


def test_changed_modules_are_valid_python() -> None:
    for name in (
        "app_version.py",
        "notifier.py",
        "fresh_trend_monitor.py",
        "market_intelligence.py",
        "decision_report.py",
        "report_contracts.py",
        "pages/overview.py",
    ):
        ast.parse(_source(name), filename=name)


def test_release_version_and_safety_statement_are_current() -> None:
    source = _source("app_version.py")
    assert 'APP_VERSION = "v19.22.0-rc16.32t"' in source
    assert 'PREVIOUS_APP_VERSION = "v19.22.0-rc16.32s"' in source
    assert "v19.22.0-rc16.32q: Priority and Portfolio Clarity" in source


def test_notification_priority_is_delivery_only_and_batched() -> None:
    source = _source("fresh_trend_monitor.py")
    names = _function_names("fresh_trend_monitor.py")
    assert {"_notification_priority", "_batch_message"} <= names
    assert "presentation/delivery metadata only" in source
    assert "PAPER – EID" in source
    assert "KANDIDAT – IKKE EID" in source
    assert "Åpne P1 først, deretter P2" in source
    assert '"last_batch_notification": current.get("last_batch_notification")' in source
    assert '"production_scoring_changed": False' in source
    assert '"trade_authority": False' in source


def test_priority_classification_and_batch_order() -> None:
    functions = _load_standalone_functions(
        "fresh_trend_monitor.py", {"_notification_priority", "_batch_message"}
    )
    classify = functions["_notification_priority"]
    batch = functions["_batch_message"]
    assert classify({"status": "FALSKT BREAKOUT", "is_held": True})["code"] == "P1"
    assert classify({"status": "AKSELERERER"})["code"] == "P2"
    assert classify({"status": "AVVENTER BEKREFTELSE"})["code"] == "P3"
    assert classify({"status": "NYTT SIGNAL"})["code"] == "P4"
    title, body = batch([
        {"ticker": "LOW", "status": "NYTT", "priority_level": 4, "scope": "KANDIDAT"},
        {"ticker": "OWN", "status": "FALSKT BREAKOUT", "priority_level": 1, "scope": "PAPER"},
    ])
    assert title.startswith("🔴 2 NYE SIGNALER")
    assert body.index("OWN") < body.index("LOW")


def test_pushover_titles_lead_with_priority_and_ticker() -> None:
    notifier = _source("notifier.py")
    trend = _source("fresh_trend_monitor.py")
    assert 'title = f"🔴 P1 · {title_identity} · PAPER BUY"' in notifier
    assert 'title = f"🔴 P1 · {title_identity} · PAPER SELL"' in notifier
    assert '"priority": max(-2, min(1, int(priority or 0)))' in notifier
    assert "{priority['code']} · {title_identity}" in trend


def test_fixed_reports_include_isolated_super_portfolio_snapshot() -> None:
    report = _source("market_intelligence.py")
    contract = _source("report_contracts.py")
    decision = _source("decision_report.py")
    assert 'run["super_portfolio_snapshot"]' in report
    assert 'section_payload(report_document, "super_portfolio_snapshot"' in report
    assert "ingen handelsmyndighet i Paper Trading eller Autonomi" in report
    assert '"super_portfolio_snapshot"' in contract
    assert '"super_portfolio_snapshot"' in decision


def test_dashboard_has_real_date_range_and_measurement_time() -> None:
    source = _source("pages/overview.py")
    assert "Fra {escape(first_label)}" in source
    assert "Til {escape(last_label)}" in source
    assert '"last_updated": updated_label' in source
    assert "Sist oppdatert:" in source
