from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

LEGACY_VERSION_PATTERN = re.compile(r"v18[._-]?(?:[0-9]+[._-]?)+", re.IGNORECASE)


def _python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if not any(part.startswith(".") for part in p.parts))


def audit_ui_cleanup(root: str | Path) -> dict[str, Any]:
    base = Path(root).resolve()
    files = _python_files(base)
    duplicate_functions: dict[str, list[str]] = {}
    legacy_markers: Counter[str] = Counter()
    streamlit_calls: Counter[str] = Counter()
    parse_errors: list[dict[str, str]] = []

    for path in files:
        rel = str(path.relative_to(base))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text, filename=rel)
        except SyntaxError as exc:
            parse_errors.append({"file": rel, "error": str(exc)})
            continue

        names = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        counts = Counter(names)
        repeated = sorted(name for name, count in counts.items() if count > 1)
        if repeated:
            duplicate_functions[rel] = repeated

        for marker in LEGACY_VERSION_PATTERN.findall(text):
            legacy_markers[marker.lower()] += 1

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "st":
                    streamlit_calls[node.func.attr] += 1

    return {
        "root": str(base),
        "python_files": len(files),
        "parse_errors": parse_errors,
        "files_with_duplicate_function_names": duplicate_functions,
        "legacy_version_markers_top": legacy_markers.most_common(20),
        "streamlit_calls": dict(streamlit_calls.most_common()),
        "shared_ui_library_present": (base / "ui_library" / "__init__.py").exists(),
        "summary": {
            "duplicate_function_files": len(duplicate_functions),
            "parse_error_count": len(parse_errors),
            "legacy_marker_occurrences": sum(legacy_markers.values()),
        },
    }


def write_ui_cleanup_report(root: str | Path, output: str | Path) -> dict[str, Any]:
    report = audit_ui_cleanup(root)
    Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Audit UI duplication and legacy markers.")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--output", default="UI_CLEANUP_AUDIT_v18_6_83.json")
    args = parser.parse_args()
    result = write_ui_cleanup_report(args.root, args.output)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
