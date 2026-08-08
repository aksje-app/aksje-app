"""Direct, unlisted PDF delivery through Streamlit's static file server."""
from __future__ import annotations

import os
import re
import secrets
from pathlib import Path
from typing import Any, Mapping, MutableMapping
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parent
PUBLIC_REPORT_DIR = PROJECT_ROOT / "static" / "reports"


def _public_origin(value: str) -> str:
    parsed = urlsplit(str(value or "").strip())
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def ensure_public_pdf_name(run: MutableMapping[str, Any]) -> str:
    current = str(run.get("public_pdf_name") or "").strip()
    if current and Path(current).name == current and current.lower().endswith(".pdf"):
        return current
    identity = run.get("report_identity") if isinstance(run.get("report_identity"), Mapping) else {}
    label = str(identity.get("label") or run.get("report_type") or "rapport")
    report_id = str(identity.get("report_id") or run.get("report_id") or run.get("run_id") or "ukjent")
    job = str(run.get("job_name") or "analyse")
    date = str(run.get("created_at_local") or run.get("created_at") or "")[:10]
    # RC16: every new public PDF name carries the immutable report identity.
    # The random suffix prevents collisions; an existing stored name is never rewritten.
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{label}_{job}_{report_id}_{date}").strip("_")[:112] or "rapport"
    name = f"{stem}_{secrets.token_urlsafe(12)}.pdf"
    run["public_pdf_name"] = name
    return name


def publish_pdf(run: MutableMapping[str, Any], pdf_bytes: bytes) -> Path:
    PUBLIC_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    name = ensure_public_pdf_name(run)
    target = PUBLIC_REPORT_DIR / name
    temporary = target.with_suffix(".pdf.tmp")
    temporary.write_bytes(bytes(pdf_bytes))
    temporary.replace(target)
    from public_report_store import publish_durable_pdf
    publish_durable_pdf(run, pdf_bytes)
    return target


def public_report_url(run: Mapping[str, Any]) -> str:
    token = str(run.get("public_report_token") or "").strip()
    if token:
        explicit = _public_origin(os.getenv("REPORT_PUBLIC_BASE_URL") or "")
        external = _public_origin(os.getenv("RENDER_EXTERNAL_URL") or "")
        base = external or explicit
        if base:
            return f"{base}/?public_report_token={token}"
    name = str(run.get("public_pdf_name") or "").strip()
    if not name or Path(name).name != name:
        return ""
    explicit = str(os.getenv("REPORT_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if explicit:
        return f"{explicit}/{name}"
    external = str(os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    if external:
        return ""
    legacy = str(os.getenv("REPORT_BASE_URL") or "").strip().rstrip("/")
    if legacy:
        return f"{legacy}/app/static/reports/{name}"
    return ""
