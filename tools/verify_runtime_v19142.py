#!/usr/bin/env python3
"""Offline runtime verification without importing Streamlit."""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import py_compile
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ENTRYPOINTS = (
    "app.py", "scheduled_runner.py", "scanner_worker.py",
    "autonomous_orchestrator.py", "runtime_background.py",
)


def module_index() -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if any(part in {".git", ".venv", "__pycache__", ".pytest_cache"} for part in rel.parts):
            continue
        parts = list(rel.with_suffix("").parts)
        name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        if name:
            modules[name] = rel
        if len(parts) == 1:
            modules[parts[0]] = rel
    return modules


def local_imports(rel: Path, modules: dict[str, Path]) -> set[Path]:
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8-sig"))
    found: set[Path] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        for name in names:
            target = modules.get(name) or modules.get(name.split(".")[0])
            if target is not None:
                found.add(target)
    return found


def import_closure() -> tuple[set[Path], list[str]]:
    modules = module_index()
    visited: set[Path] = set()
    pending = [Path(item) for item in ENTRYPOINTS]
    missing: list[str] = []
    while pending:
        rel = pending.pop()
        if rel in visited:
            continue
        visited.add(rel)
        if not (ROOT / rel).is_file():
            missing.append(str(rel))
            continue
        for target in local_imports(rel, modules):
            if not (ROOT / target).is_file():
                missing.append(f"{rel} -> {target}")
            elif target not in visited:
                pending.append(target)
    return visited, sorted(set(missing))


def main() -> int:
    failures: list[str] = []
    compiled = 0
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if any(part in {".git", ".venv", "__pycache__", ".pytest_cache"} for part in rel.parts):
            continue
        try:
            py_compile.compile(str(path), doraise=True)
            compiled += 1
        except Exception as exc:
            failures.append(f"compile {rel}: {exc}")

    visited, missing = import_closure()
    failures.extend(f"missing import: {item}" for item in missing)
    for required in (Path("forecast_backtest_engine.py"), Path("runtime_safety.py"), Path("paper_trading_guard.py")):
        if required not in visited:
            failures.append(f"runtime closure did not reach {required}")

    old = {key: os.environ.get(key) for key in ("PAPER_TRADING_ENABLED", "APP_ENVIRONMENT")}
    try:
        os.environ["APP_ENVIRONMENT"] = "test"
        os.environ["PAPER_TRADING_ENABLED"] = "false"
        from runtime_safety import paper_trading_decision, runtime_safety_snapshot
        decision = paper_trading_decision()
        snapshot = runtime_safety_snapshot()
        if decision.allowed or decision.label != "AV":
            failures.append("paper gate is not fail-closed")
        if snapshot["scheduler_enabled"] or snapshot["background_enabled"]:
            failures.append("test runtime services are not disabled")
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    result = {
        "ok": not failures,
        "version": __import__("app_version").APP_VERSION,
        "compiled_python_files": compiled,
        "runtime_modules_in_closure": len(visited),
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
