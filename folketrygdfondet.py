from __future__ import annotations

import io
import csv
import html
import json
from datetime import datetime
from typing import Any, Mapping, Sequence

import pandas as pd

from nbim_radar import (
    build_ticker_alias_lookup,
    format_nbim_amount,
    match_nbim_holding_to_ticker,
    parse_number,
)


FOLKETRYGDFONDET_OVERLAY_SETTINGS_KEY = "folketrygdfondet_overlay_v1864k"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _safe_json_value(value: Any) -> Any:
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _safe_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _safe_json_value(value) for key, value in dict(row).items()}


def _norm_key(value: Any) -> str:
    return "".join(ch for ch in _clean(value).lower() if ch.isalnum())


def _first(row: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    normalized = {_norm_key(key): value for key, value in row.items()}
    for alias in aliases:
        key = _norm_key(alias)
        if key in normalized and normalized[key] not in {None, ""}:
            return normalized[key]
    return None


def _read_excel_sheets(data: bytes, filename: str = "") -> list[tuple[str, pd.DataFrame]]:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    engine = "xlrd" if suffix == "xls" else "openpyxl" if suffix == "xlsx" else None
    try:
        loaded = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None, engine=engine)
    except ImportError as exc:
        if suffix == "xlsx":
            raise RuntimeError("Mangler openpyxl for .xlsx-filer. Installer openpyxl eller lagre filen som .xls.") from exc
        raise RuntimeError("Mangler xlrd for gamle .xls-filer. Installer xlrd eller lagre filen som .xlsx.") from exc
    except Exception as exc:
        raise RuntimeError(f"Kunne ikke lese Folketrygdfondet-regneark: {exc}") from exc
    return [(str(name), frame) for name, frame in loaded.items() if isinstance(frame, pd.DataFrame)]


def _frame_to_dict_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    aliases = {
        "selskap", "navn", "company", "name", "utsteder", "issuer",
        "ticker", "symbol", "isin", "land", "country", "marked",
        "beholdning", "aksjer", "shares", "eierandel", "verdi", "markedsverdi",
    }
    best_idx = 0
    best_score = -1
    scan_rows = min(len(frame.index), 25)
    for idx in range(scan_rows):
        values = [_norm_key(value) for value in frame.iloc[idx].tolist()]
        score = sum(1 for value in values if value in aliases)
        if score > best_score:
            best_score = score
            best_idx = idx
    headers = [_clean(value) or f"kolonne_{idx + 1}" for idx, value in enumerate(frame.iloc[best_idx].tolist())]
    out: list[dict[str, Any]] = []
    for _, raw in frame.iloc[best_idx + 1 :].iterrows():
        item = {headers[idx]: raw.iloc[idx] for idx in range(min(len(headers), len(raw)))}
        if any(_clean(value) for value in item.values()):
            out.append(item)
    return out


def normalize_folketrygdfondet_holding(row: Mapping[str, Any]) -> dict[str, Any]:
    name = _clean(_first(row, ("selskap", "navn", "company", "name", "utsteder", "issuer", "verdipapir")))
    ticker = _clean(_first(row, ("ticker", "symbol", "bloomberg ticker", "exchange ticker"))).upper()
    country = _clean(_first(row, ("land", "country", "marked", "market")))
    shares = parse_number(_first(row, ("beholdning", "aksjer", "shares", "antall aksjer", "antall")))
    market_value_nok = parse_number(_first(row, ("markedsverdi", "verdi", "market value", "market value nok", "verdi nok")))
    ownership_pct = parse_number(_first(row, ("eierandel", "eierandel %", "ownership", "ownership %", "andel")))
    return {
        "ticker": ticker,
        "name": name or ticker,
        "country": country or "Norway",
        "shares": shares,
        "market_value_nok": market_value_nok,
        "ownership_pct": ownership_pct,
        "isin": _clean(_first(row, ("isin", "isin code"))).upper(),
        "source": "Folketrygdfondet",
    }


def read_folketrygdfondet_xls_bytes(data: bytes, filename: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sheet_name, frame in _read_excel_sheets(data, filename):
        for raw in _frame_to_dict_rows(frame):
            item = normalize_folketrygdfondet_holding(raw)
            if item.get("ticker") or item.get("name") or item.get("isin"):
                item["sheet"] = sheet_name
                rows.append(item)
    return rows


def annotate_folketrygdfondet_holdings(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    alias_lookup = build_ticker_alias_lookup()
    annotated: list[dict[str, Any]] = []
    for row in rows or []:
        item = dict(row)
        match = match_nbim_holding_to_ticker(item, alias_lookup)
        item["matched_ticker"] = _clean(match.get("ticker")).upper()
        item["ticker_match_quality"] = match.get("quality") or ""
        item["ticker_match_alias"] = match.get("alias") or ""
        item["folketrygdfondet_signal"] = "Institusjonell eier"
        item["detected_at"] = datetime.now().isoformat(timespec="seconds")
        annotated.append(item)
    return annotated


def build_folketrygdfondet_overlay(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    overlay: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        ticker = _clean(row.get("matched_ticker") or row.get("ticker")).upper()
        if not ticker:
            continue
        overlay[ticker] = {
            "folketrygdfondet_owner": True,
            "folketrygdfondet_name": row.get("name") or ticker,
            "folketrygdfondet_market_value_nok": row.get("market_value_nok"),
            "folketrygdfondet_ownership_pct": row.get("ownership_pct"),
            "folketrygdfondet_shares": row.get("shares"),
            "folketrygdfondet_source": "Folketrygdfondet",
        }
    return overlay


def save_folketrygdfondet_overlay(
    overlay: Mapping[str, Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]] | None = None,
    *,
    source_as_of: str = "",
    source_file: str = "",
) -> int:
    from settings_store import load_settings, save_settings

    clean = {str(key).upper(): _safe_row(value) for key, value in overlay.items() if key and isinstance(value, Mapping)}
    saved_rows = [_safe_row(row) for row in (rows or []) if isinstance(row, Mapping)]
    settings = load_settings() or {}
    settings[FOLKETRYGDFONDET_OVERLAY_SETTINGS_KEY] = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "source_as_of": str(source_as_of or ""),
        "source_file": str(source_file or ""),
        "overlay": clean,
        "rows": saved_rows,
    }
    save_settings(settings)
    return len(clean)


def load_folketrygdfondet_snapshot() -> dict[str, Any]:
    try:
        from settings_store import load_settings

        settings = load_settings() or {}
        raw = settings.get(FOLKETRYGDFONDET_OVERLAY_SETTINGS_KEY)
        if isinstance(raw, Mapping):
            overlay = raw.get("overlay") if isinstance(raw.get("overlay"), Mapping) else {}
            rows = raw.get("rows") if isinstance(raw.get("rows"), list) else []
            return {
                "updated_at": raw.get("updated_at") or "",
                "source_as_of": raw.get("source_as_of") or raw.get("as_of_date") or "",
                "source_file": raw.get("source_file") or "",
                "overlay": {str(key).upper(): dict(value) for key, value in overlay.items() if isinstance(value, Mapping)},
                "rows": [dict(row) for row in rows if isinstance(row, Mapping)],
            }
    except Exception:
        return {"updated_at": "", "overlay": {}, "rows": []}
    return {"updated_at": "", "overlay": {}, "rows": []}


def load_folketrygdfondet_overlay() -> dict[str, dict[str, Any]]:
    return dict(load_folketrygdfondet_snapshot().get("overlay") or {})


def folketrygdfondet_display_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows or []:
        out.append({
            "Ticker": row.get("matched_ticker") or row.get("ticker") or "",
            "Selskap": row.get("name") or "",
            "Land/marked": row.get("country") or "",
            "Eierandel": row.get("ownership_pct") if row.get("ownership_pct") is not None else "",
            "Markedsverdi": format_nbim_amount(row.get("market_value_nok"), "NOK"),
            "Aksjer": row.get("shares") if row.get("shares") is not None else "",
            "Match": row.get("ticker_match_quality") or "",
            "Ark": row.get("sheet") or "",
        })
    return out


def folketrygdfondet_status() -> dict[str, Any]:
    snapshot = load_folketrygdfondet_snapshot()
    rows = snapshot.get("rows") or []
    overlay = snapshot.get("overlay") or {}
    return {
        "updated_at": snapshot.get("updated_at") or "",
        "source_as_of": snapshot.get("source_as_of") or "",
        "source_file": snapshot.get("source_file") or "",
        "rows": len(rows),
        "overlay_tickers": len(overlay),
        "matched_tickers": len(overlay),
        "unmatched_rows": sum(1 for row in rows if not (row.get("matched_ticker") or row.get("ticker"))),
    }


def folketrygdfondet_rows_to_csv(rows: Sequence[Mapping[str, Any]]) -> bytes:
    display = folketrygdfondet_display_rows(rows)
    fields = ["Ticker", "Selskap", "Land/marked", "Eierandel", "Markedsverdi", "Aksjer", "Match", "Ark"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in display:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8-sig")


def folketrygdfondet_rows_to_json(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return json.dumps([_safe_row(row) for row in rows or []], ensure_ascii=False, indent=2).encode("utf-8")


def _html_table(rows: Sequence[Mapping[str, Any]], limit: int = 100) -> str:
    display = folketrygdfondet_display_rows(rows)[:limit]
    if not display:
        return "<p>Ingen rader.</p>"
    columns = list(display[0].keys())
    head = "".join(f"<th>{html.escape(str(col))}</th>" for col in columns)
    body = []
    for row in display:
        body.append("<tr>" + "".join(f"<td>{html.escape(str(row.get(col) or ''))}</td>" for col in columns) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def build_folketrygdfondet_report_html(rows: Sequence[Mapping[str, Any]]) -> bytes:
    rows = [dict(row) for row in rows or [] if isinstance(row, Mapping)]
    matched = sum(1 for row in rows if row.get("matched_ticker") or row.get("ticker"))
    title = "Folketrygdfondet - rapport"
    document = f"""<!doctype html>
<html lang="no">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 28px; color: #111827; }}
    button {{ border: 1px solid #0284c7; background: #0ea5e9; color: white; border-radius: 8px; padding: 9px 14px; font-weight: 700; }}
    h1 {{ margin-bottom: 4px; }}
    .meta {{ color: #4b5563; font-size: 13px; }}
    .cards {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 14px 0; }}
    .card {{ border: 1px solid #d1d5db; background: #f8fafc; border-radius: 8px; padding: 10px; }}
    .card b {{ display: block; font-size: 18px; color: #064e3b; margin-top: 4px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 8px 0 10px 0; }}
    th, td {{ border: 1px solid #d1d5db; padding: 5px 7px; text-align: left; font-size: 12px; vertical-align: top; }}
    th {{ background: #f3f4f6; }}
    @media print {{ button {{ display: none; }} body {{ margin: 16mm; }} tr {{ page-break-inside: avoid; }} }}
  </style>
</head>
<body>
  <button onclick="window.print()">Skriv ut / lagre som PDF</button>
  <h1>{html.escape(title)}</h1>
  <p class="meta">Oppdatert: {html.escape(datetime.now().isoformat(timespec="seconds"))} | Datakilde: lokal XLS/XLSX-import</p>
  <div class="cards">
    <div class="card">Rader lest<b>{len(rows)}</b></div>
    <div class="card">Ticker-match<b>{matched}</b></div>
    <div class="card">Umatchede<b>{len(rows) - matched}</b></div>
  </div>
  <h2>Matchede beholdninger</h2>
  {_html_table(rows, limit=250)}
</body>
</html>"""
    return document.encode("utf-8")


def _pdf_escape(text: Any) -> str:
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_folketrygdfondet_report_pdf(rows: Sequence[Mapping[str, Any]]) -> bytes:
    display_rows = folketrygdfondet_display_rows(rows)
    lines = ["Folketrygdfondet", f"Rader: {len(display_rows)}", ""]
    for row in display_rows[:120]:
        lines.append(
            f"{row.get('Ticker') or '-'} | {row.get('Selskap') or '-'} | {row.get('Land/marked') or '-'} | {row.get('Markedsverdi') or '-'}"
        )
    chunks = [lines[idx : idx + 46] for idx in range(0, len(lines), 46)] or [["Folketrygdfondet"]]
    objects: list[tuple[int, bytes]] = []
    page_refs: list[str] = []
    next_obj = 4
    for chunk in chunks:
        page_obj = next_obj
        content_obj = next_obj + 1
        next_obj += 2
        page_refs.append(f"{page_obj} 0 R")
        y = 800
        commands = ["BT", "/F1 15 Tf", f"50 {y} Td", f"({_pdf_escape(chunk[0])}) Tj", "/F1 9 Tf"]
        y -= 24
        for line in chunk[1:]:
            if y < 45:
                break
            commands.append(f"50 {y} Td")
            commands.append(f"({_pdf_escape(str(line)[:116])}) Tj")
            commands.append(f"-50 {-y} Td")
            y -= 14
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", errors="replace")
        objects.append((page_obj, f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >>".encode()))
        objects.append((content_obj, b"<< /Length " + str(len(stream)).encode() + b" >> stream\n" + stream + b"\nendstream"))
    objects.extend([
        (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        (2, f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>".encode()),
        (3, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
    ])
    objects = sorted(objects, key=lambda item: item[0])
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0] * (max(num for num, _ in objects) + 1)
    for num, body in objects:
        offsets[num] = len(out)
        out.extend(f"{num} 0 obj ".encode() + body + b" endobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(out)


__all__ = [
    "FOLKETRYGDFONDET_OVERLAY_SETTINGS_KEY",
    "annotate_folketrygdfondet_holdings",
    "build_folketrygdfondet_overlay",
    "folketrygdfondet_display_rows",
    "folketrygdfondet_rows_to_csv",
    "folketrygdfondet_rows_to_json",
    "folketrygdfondet_status",
    "build_folketrygdfondet_report_html",
    "build_folketrygdfondet_report_pdf",
    "load_folketrygdfondet_overlay",
    "load_folketrygdfondet_snapshot",
    "normalize_folketrygdfondet_holding",
    "read_folketrygdfondet_xls_bytes",
    "save_folketrygdfondet_overlay",
]
