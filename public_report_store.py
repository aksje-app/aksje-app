"""Unlisted, durable PDF delivery shared by Render Cron and the web service."""
from __future__ import annotations

import base64
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from durable_runtime import read_json, write_json
from services.storage_service import get_storage_service
from storage_architecture import runtime_data_path

INDEX_KEY = "public_reports/index.json"
INDEX_PATH = runtime_data_path("public_reports", "index.json")
# Main and technical PDFs are stored as separate durable documents.  Keeping
# 32 payloads preserves approximately the former 16-report retention window.
MAX_REPORTS = 32
RETENTION_HOURS = 336


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _document_key(token: str) -> str:
    return f"public_reports/{token}.json"


def _document_path(token: str):
    return runtime_data_path("public_reports", f"{token}.json")


def publish_durable_pdf(
    run: MutableMapping[str, Any], pdf_bytes: bytes, *,
    token_field: str = "public_report_token",
    filename_field: str = "public_pdf_name",
    document_kind: str = "main",
) -> str:
    token = str(run.get(token_field) or "").strip()
    if not token:
        token = secrets.token_urlsafe(32)
        run[token_field] = token
    now = _now()
    name = Path(str(run.get(filename_field) or "rapport.pdf")).name
    payload = {
        "token": token, "report_id": str(run.get("report_id") or run.get("run_id") or ""),
        "filename": name if name.lower().endswith(".pdf") else f"{name}.pdf",
        "created_at": now.isoformat(timespec="seconds"),
        "expires_at": (now + timedelta(hours=RETENTION_HOURS)).isoformat(timespec="seconds"),
        "document_kind": str(document_kind or "main"),
        "pdf_base64": base64.b64encode(bytes(pdf_bytes)).decode("ascii"),
    }
    write_json(_document_key(token), _document_path(token), payload)
    index = read_json(INDEX_KEY, INDEX_PATH, [])
    rows = [dict(row) for row in index if isinstance(row, Mapping) and row.get("token") != token]
    rows.insert(0, {key: payload[key] for key in ("token", "report_id", "filename", "created_at", "expires_at")})
    write_json(INDEX_KEY, INDEX_PATH, rows[:MAX_REPORTS])
    return token


def load_public_pdf(token: str) -> dict[str, Any]:
    clean = str(token or "").strip()
    if len(clean) < 32 or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for ch in clean):
        return {}
    payload = read_json(_document_key(clean), _document_path(clean), {})
    if not isinstance(payload, Mapping) or str(payload.get("token") or "") != clean:
        return {}
    try:
        expires = datetime.fromisoformat(str(payload.get("expires_at") or "").replace("Z", "+00:00"))
        if expires.astimezone(timezone.utc) < _now():
            return {}
        data = base64.b64decode(str(payload.get("pdf_base64") or ""), validate=True)
    except Exception:
        return {}
    if not data.startswith(b"%PDF-"):
        return {}
    return {**dict(payload), "data": data}


def prune_expired_public_reports(*, now: datetime | None = None) -> dict[str, int]:
    """Remove expired/unindexed PDF payloads while retaining current links."""
    current = (now or _now()).astimezone(timezone.utc)
    storage = get_storage_service()
    index = storage.read_json(INDEX_KEY, [])
    retained: list[dict[str, Any]] = []
    expired_tokens: set[str] = set()
    for value in index if isinstance(index, list) else []:
        if not isinstance(value, Mapping):
            continue
        token = str(value.get("token") or "").strip()
        try:
            expires = datetime.fromisoformat(str(value.get("expires_at") or "").replace("Z", "+00:00"))
            expired = expires.astimezone(timezone.utc) < current
        except Exception:
            expired = True
        if token and expired:
            expired_tokens.add(token)
        elif token:
            retained.append(dict(value))
    live_tokens = {str(row.get("token") or "") for row in retained[:MAX_REPORTS]}
    deleted = 0
    for name in storage.list_json_names():
        if not name.startswith("public_reports/") or name == INDEX_KEY:
            continue
        token = Path(name).stem
        if token in expired_tokens or token not in live_tokens:
            existed = storage.read_json(name, None) is not None
            storage.delete_json(name)
            deleted += int(existed)
    storage.write_json(INDEX_KEY, retained[:MAX_REPORTS])
    return {"deleted_payloads": deleted, "retained_links": len(retained[:MAX_REPORTS])}
