from __future__ import annotations

import ast
import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = (
    "app.py",
    "scheduled_runner.py",
    "scanner_worker.py",
    "autonomous_orchestrator.py",
    "runtime_background.py",
)


def _module_index() -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        parts = list(rel.with_suffix("").parts)
        if parts[-1] == "__init__":
            name = ".".join(parts[:-1])
        else:
            name = ".".join(parts)
        if name:
            modules[name] = rel
    for path in ROOT.glob("*.py"):
        modules[path.stem] = path.relative_to(ROOT)
    return modules


def _local_imports(rel: Path, modules: dict[str, Path]) -> list[Path]:
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8-sig"))
    found: list[Path] = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        for name in names:
            target = modules.get(name) or modules.get(name.split(".")[0])
            if target is not None:
                found.append(target)
    return found


def test_runtime_entrypoint_import_closure_exists() -> None:
    modules = _module_index()
    missing: list[str] = []
    visited: set[Path] = set()
    pending = [Path(name) for name in ENTRYPOINTS]
    while pending:
        rel = pending.pop()
        if rel in visited:
            continue
        visited.add(rel)
        path = ROOT / rel
        if not path.is_file():
            missing.append(str(rel))
            continue
        for target in _local_imports(rel, modules):
            if not (ROOT / target).is_file():
                missing.append(f"{rel} -> {target}")
            elif target not in visited:
                pending.append(target)
    assert not missing, "Manglende lokale runtime-importer: " + ", ".join(sorted(set(missing)))


def test_forecast_backtest_engine_imports_cleanly(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APP_RUNTIME_ROOT", str(tmp_path / ".app_runtime"))
    monkeypatch.setenv("STORAGE_MODE", "local")
    monkeypatch.setenv("ALLOW_LOCAL_STORAGE_FALLBACK", "true")
    module = importlib.import_module("forecast_backtest_engine")
    assert callable(module.run_backtest_learning_batch)
    assert callable(module.summarize_backtest_learning)
