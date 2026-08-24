#!/usr/bin/env python3
"""Static release audit for the canonical current release.

This audit is intentionally independent of live APIs. It checks the release
contract that previously drifted between GitHub, Render and generated reports.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app_version import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = APP_VERSION
EXPECTED_DOC_TAG = APP_VERSION.replace("-rc", "_RC")
MUTABLE_ROOTS = ("data", "cache", "logs", "runtime", "storage")
REQUIRED_REQUIREMENTS = {
    "streamlit==1.57.0",
    "starlette==1.3.1",
    "pandas==3.0.5",
    "yfinance==1.6.0",
    "requests==2.34.2",
    "psycopg2-binary==2.9.12",
    "reportlab==5.0.0",
    "pypdf==5.9.0",
}


def _check(condition: bool, code: str, detail: str, errors: list[dict]) -> None:
    if not condition:
        errors.append({"code": code, "detail": detail})


def audit(root: Path = ROOT) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []

    version_source = (root / "app_version.py").read_text(encoding="utf-8")
    _check(f'APP_VERSION = "{EXPECTED_VERSION}"' in version_source, "VERSION", f"APP_VERSION er ikke {EXPECTED_VERSION}", errors)
    _check('REPORT_SCHEMA_VERSION = "1.6"' in version_source, "REPORT_SCHEMA", "Rapportskjema er ikke 1.6", errors)

    requirements = {
        line.strip() for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    for item in sorted(REQUIRED_REQUIREMENTS):
        _check(item in requirements, "DEPENDENCY", f"Mangler eksplisitt avhengighet: {item}", errors)

    render = (root / "render.yaml").read_text(encoding="utf-8")
    _check("STREAMLIT_SERVER_USE_STARLETTE" not in render and "useStarlette" not in render,
           "STREAMLIT_CONFIG", "Ugyldig Starlette-konfigurasjon finnes fortsatt", errors)
    _check(render.count('key: PAPER_TRADING_ENABLED') == 3, "RENDER_PAPER_KEYS", "Alle tre Render-tjenestene må angi Paper Trading", errors)
    _check("name: aksje-app-paper-scanner" in render and "startCommand: python scanner_worker.py" in render,
           "RENDER_PAPER_SCANNER", "Render mangler en eksplisitt Paper-skanner", errors)
    _check(render.count('value: "false"') >= 6, "RENDER_FAIL_CLOSED", "Render-standardene er ikke fail-closed", errors)
    _check("key: STORAGE_MODE" in render and "key: ALLOW_LOCAL_STORAGE_FALLBACK" in render,
           "RENDER_STORAGE", "Render mangler eksplisitt lagringspolicy", errors)

    broken_import_hits = []
    tuple_truthiness_hits = []
    for path in root.rglob("*.py"):
        if any(part in {".git", ".pytest_cache", "__pycache__", ".app_runtime"} for part in path.parts):
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "from notification_service import" in text:
            broken_import_hits.append(path.relative_to(root).as_posix())
        if "if ok is not False" in text:
            tuple_truthiness_hits.append(path.relative_to(root).as_posix())
    _check(not broken_import_hits, "NOTIFICATION_IMPORT", f"Ugyldige notification_service-importer: {broken_import_hits}", errors)
    _check(not tuple_truthiness_hits, "NOTIFICATION_RESULT", f"Utrygg varslingsresultatkontroll: {tuple_truthiness_hits}", errors)
    _check(not (root / "streamlit_patch_snippet.py").exists(), "DEAD_SNIPPET", "Ufullstendig legacy-snutt ligger i aktiv rot", errors)

    # .app_runtime is an explicitly ignored local runtime root. Tests may create
    # it during the same process; distribution builders must exclude it.
    mutable_files: list[str] = []
    for folder in MUTABLE_ROOTS:
        base = root / folder
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.name != ".gitkeep":
                mutable_files.append(path.relative_to(root).as_posix())
    _check(not mutable_files, "MUTABLE_RUNTIME", f"Mutable runtimefiler i kildekoden: {mutable_files[:20]}", errors)

    for name in (f"RELEASE_NOTES_{EXPECTED_DOC_TAG}.md", f"ACCEPTANCE_{EXPECTED_DOC_TAG}.md", f"DEPLOY_{EXPECTED_DOC_TAG}.md"):
        _check((root / name).is_file(), "DOCUMENTATION", f"Mangler {name}", errors)

    try:
        from market_universe import market_profile_contract
        contracts = {
            "CORE": market_profile_contract("CORE", ["Alle kjernemarkeder"])["expanded_markets"],
            "EXTENDED_NORDIC": market_profile_contract("EXTENDED_NORDIC", ["Utvidet Norden"])["expanded_markets"],
            "BRAZIL": market_profile_contract("BRAZIL", ["Brasil"])["expanded_markets"],
            "FULL": market_profile_contract("FULL", ["Alle markeder - full skanning"])["expanded_markets"],
        }
        _check(contracts["CORE"] == ["Norge", "Sverige", "USA"], "CORE_MARKETS", str(contracts["CORE"]), errors)
        _check(contracts["EXTENDED_NORDIC"] == ["Danmark", "Finland"], "NORDIC_MARKETS", str(contracts["EXTENDED_NORDIC"]), errors)
        _check(contracts["BRAZIL"] == ["Brasil"], "BRAZIL_MARKET", str(contracts["BRAZIL"]), errors)
        _check(set(contracts["FULL"]) == {"Norge", "Sverige", "USA", "Danmark", "Finland", "Brasil"} and len(contracts["FULL"]) == 6, "FULL_MARKETS", str(contracts["FULL"]), errors)
    except Exception as exc:
        errors.append({"code": "MARKET_PROFILE_IMPORT", "detail": str(exc)})
        contracts = {}

    return {
        "ok": not errors,
        "version": EXPECTED_VERSION,
        "errors": errors,
        "warnings": warnings,
        "market_profiles": contracts,
        "mutable_file_count": len(mutable_files),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit()
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
