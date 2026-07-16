from __future__ import annotations

import argparse
import ast
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

ROOT = Path(__file__).resolve().parent


def python_files() -> List[Path]:
    ignored = {".venv", "venv", ".app_runtime", "__pycache__", "tests"}
    return sorted(p for p in ROOT.rglob("*.py") if not any(part in ignored for part in p.parts))


def analyze_file(path: Path) -> Dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    row = {"file": str(path.relative_to(ROOT)), "lines": len(text.splitlines()), "imports": [], "functions": 0, "classes": 0, "syntax_ok": True}
    try:
        tree = ast.parse(text)
    except SyntaxError:
        row["syntax_ok"] = False
        return row
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                row["imports"].extend(alias.name.split(".")[0] for alias in node.names)
            elif node.module:
                row["imports"].append(node.module.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            row["functions"] += 1
        elif isinstance(node, ast.ClassDef):
            row["classes"] += 1
    return row


def build_report() -> Dict:
    rows = [analyze_file(path) for path in python_files()]
    local_names = {Path(row["file"]).stem for row in rows}
    graph: Dict[str, Set[str]] = defaultdict(set)
    imports = Counter()
    for row in rows:
        src = Path(row["file"]).stem
        for imp in row["imports"]:
            imports[imp] += 1
            if imp in local_names and imp != src:
                graph[src].add(imp)

    cycles: List[List[str]] = []
    visiting: Set[str] = set()
    visited: Set[str] = set()

    def dfs(node: str, path: List[str]) -> None:
        if node in visiting:
            if node in path:
                cycle = path[path.index(node):] + [node]
                if cycle not in cycles:
                    cycles.append(cycle)
            return
        if node in visited:
            return
        visiting.add(node)
        for nxt in graph.get(node, set()):
            dfs(nxt, path + [nxt])
        visiting.remove(node)
        visited.add(node)

    for node in list(graph):
        dfs(node, [node])

    largest = sorted(rows, key=lambda row: row["lines"], reverse=True)[:25]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "files": len(rows),
        "lines": sum(row["lines"] for row in rows),
        "functions": sum(row["functions"] for row in rows),
        "classes": sum(row["classes"] for row in rows),
        "syntax_errors": [row["file"] for row in rows if not row["syntax_ok"]],
        "largest_files": largest,
        "top_imports": imports.most_common(30),
        "possible_import_cycles": cycles[:50],
        "architecture_layers": {
            "ui": ["app.py", "*_ui.py", "workspace_layout.py"],
            "services": ["core_architecture.py", "storage_service.py", "notification_service.py (gradvis migrering)"],
            "domain": ["trading_engine.py", "decision_engine.py", "paper_trading_professional.py"],
            "analytics": ["ai_discovery_analytics.py", "ai_learning_foundation.py", "performance_monitor.py"],
            "storage": ["storage_architecture.py", "storage_service.py", "db.py"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Static architecture/code metrics audit")
    parser.add_argument("--output", default="ARCHITECTURE_AUDIT_v18_6_80.json")
    args = parser.parse_args()
    report = build_report()
    output = ROOT / args.output
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "files": report["files"], "lines": report["lines"], "cycles": len(report["possible_import_cycles"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
