"""Dependency-free runner for this project's plain assert regression tests."""
from __future__ import annotations

import importlib.util
import inspect
import os
import sys
import tempfile
from pathlib import Path


class MonkeyPatch:
    def __init__(self) -> None:
        self.undo_actions = []

    def setattr(self, target, name, value) -> None:
        existed = hasattr(target, name)
        previous = getattr(target, name, None)
        setattr(target, name, value)
        self.undo_actions.append(lambda: setattr(target, name, previous) if existed else delattr(target, name))

    def setitem(self, mapping, key, value) -> None:
        existed, previous = key in mapping, mapping.get(key)
        mapping[key] = value
        self.undo_actions.append(lambda: mapping.__setitem__(key, previous) if existed else mapping.pop(key, None))

    def setenv(self, key, value) -> None:
        existed, previous = key in os.environ, os.environ.get(key)
        os.environ[key] = str(value)
        self.undo_actions.append(lambda: os.environ.__setitem__(key, previous) if existed else os.environ.pop(key, None))

    def delenv(self, key, raising=True) -> None:
        existed, previous = key in os.environ, os.environ.get(key)
        if not existed and raising:
            raise KeyError(key)
        os.environ.pop(key, None)
        self.undo_actions.append(lambda: os.environ.__setitem__(key, previous) if existed else None)

    def undo(self) -> None:
        for action in reversed(self.undo_actions):
            action()
        self.undo_actions.clear()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    passed = failed = 0
    failures = []
    for path in sorted((root / "tests").glob("test_*.py")):
        name = f"offline_{path.stem}"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        for test_name, function in sorted(inspect.getmembers(module, inspect.isfunction)):
            if not test_name.startswith("test_"):
                continue
            monkeypatch = MonkeyPatch()
            try:
                with tempfile.TemporaryDirectory(prefix="ai-analyzer-test-") as tmp:
                    fixtures = {}
                    for parameter in inspect.signature(function).parameters:
                        if parameter == "monkeypatch":
                            fixtures[parameter] = monkeypatch
                        elif parameter == "tmp_path":
                            fixtures[parameter] = Path(tmp)
                        else:
                            raise RuntimeError(f"Ukjent fixture: {parameter}")
                    function(**fixtures)
                passed += 1
            except Exception as exc:
                failed += 1
                failures.append(f"{path.name}::{test_name}: {type(exc).__name__}: {exc}")
            finally:
                monkeypatch.undo()
    for failure in failures:
        print(f"FAILED {failure}")
    print(f"Regression: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
