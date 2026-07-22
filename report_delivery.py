"""Direct, unlisted PDF delivery through Streamlit's static file server."""
from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any, Mapping, MutableMapping

PROJECT_ROOT = Path(__file__).resolve().parent
PUBLIC_REPORT_DIR = PROJECT_ROOT / "static" / "reports"


def ensure_public_pdf_name(run: MutableMapping[str, Any]) -> str:
    current = str(run.get("public_pdf_name") or "").strip()
    if current and Path(current).name == current and current.lower().endswith(".pdf"):
        return current
    name = f"report_{secrets.token_urlsafe(24)}.pdf"
    run["public_pdf_name"] = name
    return name


def publish_pdf(run: MutableMapping[str, Any], pdf_bytes: bytes) -> Path:
    PUBLIC_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    name = ensure_public_pdf_name(run)
    target = PUBLIC_REPORT_DIR / name
    temporary = target.with_suffix(".pdf.tmp")
    temporary.write_bytes(bytes(pdf_bytes))
    temporary.replace(target)
    return target


def public_report_url(run: Mapping[str, Any]) -> str:
    name = str(run.get("public_pdf_name") or "").strip()
    if not name or Path(name).name != name:
        return ""
    explicit = str(os.getenv("REPORT_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if explicit:
        return f"{explicit}/{name}"
    external = str(os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    if external:
        return f"{external}/app/static/reports/{name}"
    legacy = str(os.getenv("REPORT_BASE_URL") or "").strip().rstrip("/")
    if legacy:
        return f"{legacy}/app/static/reports/{name}"
    return ""
