"""Render/GitHub deploy smoke check for v18.5.10.

Default mode is safe to run before local dependency installation:
- verifies Render-critical files
- verifies project modules that should import without starting Streamlit
- verifies that required dependencies are declared in requirements.txt

Set STRICT_DEP_IMPORTS=1 to also import third-party packages after `pip install -r requirements.txt`.
If DATABASE_URL is set, the script also verifies that the generic runtime-state
Postgres table can be initialized.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

REQUIRED_FILES = [
    "app.py",
    "requirements.txt",
    "Procfile",
    "runtime.txt",
    ".python-version",
    "render.yaml",
    "core_models.py",
    "universe_engine.py",
    "services/service_registry.py",
]

PROJECT_IMPORTS = [
    "core_models",
    "universe_engine",
    "services.service_registry",
]

REQUIRED_REQUIREMENTS = [
    "streamlit",
    "pandas",
    "numpy",
    "plotly",
    "yfinance",
    "requests",
    "psycopg2-binary",
    "python-dotenv",
]

STRICT_DEP_IMPORTS = [
    "streamlit",
    "pandas",
    "numpy",
    "plotly",
    "yfinance",
    "psycopg2",
]


def _requirements_text() -> str:
    path = Path("requirements.txt")
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore").lower()


def _check_imports(modules: list[str]) -> list[str]:
    errors: list[str] = []
    for module in modules:
        try:
            importlib.import_module(module)
        except Exception as exc:
            errors.append(f"{module}: {exc}")
    return errors


def main() -> int:
    missing = [path for path in REQUIRED_FILES if not Path(path).exists()]
    if missing:
        print("Mangler filer:", ", ".join(missing))
        return 1

    req_text = _requirements_text()
    missing_requirements = [pkg for pkg in REQUIRED_REQUIREMENTS if pkg.lower() not in req_text]
    if missing_requirements:
        print("Mangler krav i requirements.txt:", ", ".join(missing_requirements))
        return 1

    import_errors = _check_imports(PROJECT_IMPORTS)
    if import_errors:
        print("Prosjektimport-feil:")
        for item in import_errors:
            print("-", item)
        return 1

    if os.getenv("STRICT_DEP_IMPORTS", "").strip() in {"1", "true", "TRUE", "yes", "YES"}:
        dep_errors = _check_imports(STRICT_DEP_IMPORTS)
        if dep_errors:
            print("Tredjepartsimport-feil etter pip install:")
            for item in dep_errors:
                print("-", item)
            return 1
    else:
        print("STRICT_DEP_IMPORTS ikke satt: hopper over import av tredjepartsdeps.")

    if os.getenv("DATABASE_URL", "").strip():
        from services.storage_service import StorageService

        storage = StorageService({})
        try:
            storage.init_runtime_state()
            print("Database/runtime-state: OK")
        except Exception as exc:
            print(f"Database/runtime-state: FEIL - {exc}")
            return 1
    else:
        print("DATABASE_URL ikke satt: OK for lokal test; Render bør ha env var.")

    print("Render health check: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
