#!/usr/bin/env python3
"""Fail a Render build unless the deterministic production lock is exact."""
from __future__ import annotations

from importlib import metadata
import json
from pathlib import Path
import re

from packaging.specifiers import SpecifierSet
from packaging.version import Version


ROOT = Path(__file__).resolve().parent.parent
TARGET_PYTHON = Version("3.12.13")
EXACT_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([^\s;]+)$")


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", str(name).strip()).lower()


def read_pins(path: Path) -> dict[str, tuple[str, str]]:
    pins: dict[str, tuple[str, str]] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = EXACT_PIN.fullmatch(line)
        if not match:
            raise ValueError(f"{path.name}:{number} er ikke en eksakt ==-pin: {line}")
        package, version = match.groups()
        key = canonical(package)
        if key in pins:
            raise ValueError(f"Duplikatpakke i {path.name}: {package}")
        pins[key] = (package, version)
    return pins


def verify() -> dict[str, object]:
    direct = read_pins(ROOT / "requirements.txt")
    locked = read_pins(ROOT / "requirements.lock")
    missing_roots = sorted(set(direct) - set(locked))
    root_mismatches = sorted(
        name for name in set(direct) & set(locked)
        if direct[name][1] != locked[name][1]
    )
    installed_mismatches: list[dict[str, str]] = []
    incompatible_with_target: list[dict[str, str]] = []
    for name, (display_name, expected) in sorted(locked.items()):
        try:
            distribution = metadata.distribution(display_name)
            actual = distribution.version
            requires_python = str(distribution.metadata.get("Requires-Python") or "").strip()
            if requires_python and TARGET_PYTHON not in SpecifierSet(requires_python):
                incompatible_with_target.append({
                    "package": display_name,
                    "requires_python": requires_python,
                    "target_python": str(TARGET_PYTHON),
                })
        except metadata.PackageNotFoundError:
            actual = "MISSING"
        if actual != expected:
            installed_mismatches.append({
                "package": display_name,
                "expected": expected,
                "actual": actual,
            })
    result = {
        "ok": not (missing_roots or root_mismatches or installed_mismatches or incompatible_with_target),
        "target_python": str(TARGET_PYTHON),
        "direct_dependency_count": len(direct),
        "locked_dependency_count": len(locked),
        "missing_roots": missing_roots,
        "root_version_mismatches": root_mismatches,
        "installed_mismatches": installed_mismatches,
        "incompatible_with_target": incompatible_with_target,
    }
    if not result["ok"]:
        raise RuntimeError(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def main() -> int:
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
