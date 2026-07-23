"""Brazil CVM VLMO primary-source reader with weekly durable cache."""
from __future__ import annotations

import csv
import io
import re
import time
import unicodedata
import zipfile
from datetime import datetime, timezone
from typing import Any, Mapping

from storage_architecture import runtime_data_path

CVM_DATASET = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/VLMO/DADOS"
CACHE_FILE = runtime_data_path("insider_intelligence") / "cvm_vlmo_cache.zip"
CACHE_TTL = 6 * 24 * 3600


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _field(row: Mapping[str, Any], *tokens: str) -> str:
    normalized = {_norm(key): value for key, value in row.items()}
    for key, value in normalized.items():
        if all(token in key for token in tokens):
            return str(value or "").strip()
    return ""


def _number(value: Any) -> float:
    text = str(value or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _download(year: int, session: Any) -> bytes:
    if CACHE_FILE.is_file() and time.time() - CACHE_FILE.stat().st_mtime < CACHE_TTL:
        return CACHE_FILE.read_bytes()
    url = f"{CVM_DATASET}/vlmo_cia_aberta_{year}.zip"
    response = session.get(url, timeout=35, headers={"User-Agent": "AI-Aksje-Analyzer/19.0.11"})
    response.raise_for_status()
    data = bytes(response.content)
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_bytes(data)
    return data


def fetch_cvm_transactions(ticker: str, company: str, lookback_days: int = 90, session: Any = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    result = {
        "source": "CVM – Valores Mobiliários Negociados e Detidos",
        "source_type": "PRIMARY_REGULATORY", "attempted": True,
        "status": "SUCCESS_NO_RESULTS", "results": 0, "checked_at": now.isoformat(timespec="seconds"),
        "url": f"{CVM_DATASET}/", "transactions": [], "error": "",
    }
    try:
        if session is None:
            import requests
            session = requests.Session()
        archive = zipfile.ZipFile(io.BytesIO(_download(now.year, session)))
        wanted = _norm(company)
        company_tokens = [token for token in wanted.split() if len(token) > 3][:4]
        rows: list[dict[str, Any]] = []
        for name in archive.namelist():
            if not name.lower().endswith(".csv"):
                continue
            content = archive.read(name)
            text = content.decode("latin-1", errors="replace")
            for raw in csv.DictReader(io.StringIO(text), delimiter=";"):
                issuer = _field(raw, "denominacao", "companhia") or _field(raw, "nome", "companhia")
                if company_tokens and sum(token in _norm(issuer) for token in company_tokens) < min(2, len(company_tokens)):
                    continue
                date = _field(raw, "data", "negocio") or _field(raw, "data", "movimentacao") or _field(raw, "data", "referencia")
                try:
                    parsed = datetime.fromisoformat(date[:10]).replace(tzinfo=timezone.utc)
                    if (now - parsed).days > lookback_days:
                        continue
                except Exception:
                    continue
                movement = _field(raw, "tipo", "movimentacao") or _field(raw, "tipo", "negocio")
                movement_norm = _norm(movement)
                kind = "BUY" if "aquis" in movement_norm or "compra" in movement_norm else "SELL" if "venda" in movement_norm or "alien" in movement_norm else ""
                if not kind:
                    continue
                shares = abs(_number(_field(raw, "quantidade")))
                price = abs(_number(_field(raw, "preco")))
                document_id = _field(raw, "protocolo") or _field(raw, "id", "documento")
                rows.append({
                    "date": date[:10], "type": kind,
                    "insider": _field(raw, "nome", "pessoa") or _field(raw, "nome", "administrador") or "Rapporteringspliktig",
                    "role": _field(raw, "cargo") or _field(raw, "funcao") or "Ikke oppgitt",
                    "shares": shares, "price": price, "value": round(shares * price, 2),
                    "currency": "BRL", "source": result["source"], "source_url": result["url"],
                    "document_id": document_id or f"CVM-VLMO-{now.year}-{ticker}",
                    "verification": "VERIFIED_PRIMARY", "published_at": date[:10],
                    "retrieved_at": result["checked_at"],
                })
        result["transactions"] = rows
        result["results"] = len(rows)
        result["status"] = "SUCCESS_WITH_RESULTS" if rows else "SUCCESS_NO_RESULTS"
    except Exception as exc:
        result["status"] = "ERROR"
        result["error"] = str(exc)[:300]
    return result
