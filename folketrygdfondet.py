from __future__ import annotations

import io
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
    engine = "xlrd" if suffix == "xls" else None
    try:
        loaded = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None, engine=engine)
    except ImportError as exc:
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


def save_folketrygdfondet_overlay(overlay: Mapping[str, Mapping[str, Any]]) -> int:
    from settings_store import load_settings, save_settings

    clean = {str(key).upper(): dict(value) for key, value in overlay.items() if key and isinstance(value, Mapping)}
    settings = load_settings() or {}
    settings[FOLKETRYGDFONDET_OVERLAY_SETTINGS_KEY] = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "overlay": clean,
    }
    save_settings(settings)
    return len(clean)


def load_folketrygdfondet_overlay() -> dict[str, dict[str, Any]]:
    try:
        from settings_store import load_settings

        settings = load_settings() or {}
        raw = settings.get(FOLKETRYGDFONDET_OVERLAY_SETTINGS_KEY)
        if isinstance(raw, Mapping) and isinstance(raw.get("overlay"), Mapping):
            return {str(key).upper(): dict(value) for key, value in raw["overlay"].items() if isinstance(value, Mapping)}
    except Exception:
        return {}
    return {}


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
        })
    return out


__all__ = [
    "FOLKETRYGDFONDET_OVERLAY_SETTINGS_KEY",
    "annotate_folketrygdfondet_holdings",
    "build_folketrygdfondet_overlay",
    "folketrygdfondet_display_rows",
    "load_folketrygdfondet_overlay",
    "normalize_folketrygdfondet_holding",
    "read_folketrygdfondet_xls_bytes",
    "save_folketrygdfondet_overlay",
]
