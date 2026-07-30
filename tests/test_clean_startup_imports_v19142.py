from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = (
    "app.py",
    "scheduled_runner.py",
    "scanner_worker.py",
    "autonomous_orchestrator.py",
    "runtime_background.py",
)


def _index() -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for path in ROOT.rglob("*.py"):
        if any(part in {".git", ".venv", "__pycache__"} for part in path.parts):
            continue
        rel = path.relative_to(ROOT)
        parts = list(rel.with_suffix("").parts)
        name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        if name:
            modules[name] = rel
        if len(parts) == 1:
            modules[parts[0]] = rel
    return modules


def _imports(path: Path, modules: dict[str, Path]) -> set[Path]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    result: set[Path] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        for name in names:
            target = modules.get(name)
            if target is None:
                # Importing a symbol from a package may still reference the package.
                target = modules.get(name.split(".")[0])
            if target is not None:
                result.add(target)
    return result


def test_all_local_runtime_imports_exist_from_clean_entrypoints() -> None:
    modules = _index()
    pending = [Path(value) for value in ENTRYPOINTS]
    visited: set[Path] = set()
    missing: list[str] = []
    while pending:
        rel = pending.pop()
        if rel in visited:
            continue
        visited.add(rel)
        path = ROOT / rel
        if not path.is_file():
            missing.append(str(rel))
            continue
        for target in _imports(path, modules):
            if not (ROOT / target).is_file():
                missing.append(f"{rel} -> {target}")
            elif target not in visited:
                pending.append(target)
    assert not missing, "Manglende lokale runtime-importer: " + ", ".join(sorted(set(missing)))
    assert Path("forecast_backtest_engine.py") in visited
    assert Path("runtime_safety.py") in visited
    assert Path("paper_trading_guard.py") in visited
