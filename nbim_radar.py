from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime
from typing import Any, Mapping, Sequence


NBIM_OVERLAY_SETTINGS_KEY = "nbim_radar_overlay_v1863bd"
NBIM_SOURCE_URL = "https://www.nbim.no/en/the-fund/investments/"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _clean(value).lower())


def parse_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _clean(value).replace("\u00a0", " ").replace(" ", "")
    text = text.replace("%", "")
    if not text:
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        if re.search(r",\d{1,4}$", text):
            text = text.replace(",", ".")
        else:
            text = text.replace(",", "")
    elif text.count(".") > 1 or re.search(r"\.\d{3}$", text):
        text = text.replace(".", "")
    try:
        return float(text)
    except Exception:
        return None


def _first(row: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    normalized = {_normalize_key(key): value for key, value in row.items()}
    for alias in aliases:
        key = _normalize_key(alias)
        if key in normalized and normalized[key] not in {None, ""}:
            return normalized[key]
    return None


def normalize_nbim_holding(row: Mapping[str, Any]) -> dict[str, Any]:
    ticker = _clean(_first(row, ("ticker", "symbol", "isin ticker", "exchange ticker", "bloomberg ticker"))).upper()
    name = _clean(_first(row, ("name", "company", "company name", "issuer", "security name")))
    country = _clean(_first(row, ("country", "market", "domicile")))
    sector = _clean(_first(row, ("sector", "industry", "gics sector")))
    market_value_nok = parse_number(_first(row, ("market value nok", "market_value_nok", "value nok", "verdi nok", "market value")))
    market_value_usd = parse_number(_first(row, ("market value usd", "market_value_usd", "value usd")))
    ownership_pct = parse_number(_first(row, ("ownership", "ownership %", "ownership_pct", "eierandel", "eierandel %")))
    voting_pct = parse_number(_first(row, ("voting", "voting %", "voting_pct", "stemmerett", "stemmerett %")))
    shares = parse_number(_first(row, ("shares", "number of shares", "holding", "beholdning", "aksjer")))
    return {
        "ticker": ticker,
        "name": name or ticker,
        "country": country,
        "sector": sector,
        "market_value_nok": market_value_nok,
        "market_value_usd": market_value_usd,
        "ownership_pct": ownership_pct,
        "voting_pct": voting_pct,
        "shares": shares,
    }


def read_nbim_csv_bytes(data: bytes) -> list[dict[str, Any]]:
    text = data.decode("utf-8-sig", errors="replace")
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except Exception:
        dialect = csv.excel
    rows: list[dict[str, Any]] = []
    for raw in csv.DictReader(io.StringIO(text), dialect=dialect):
        if not isinstance(raw, Mapping):
            continue
        item = normalize_nbim_holding(raw)
        if item.get("ticker") or item.get("name"):
            rows.append(item)
    return rows


def _holding_key(row: Mapping[str, Any]) -> str:
    ticker = _clean(row.get("ticker")).upper()
    if ticker:
        return f"ticker:{ticker}"
    return "name:" + _normalize_key(row.get("name"))


def _comparison_value(row: Mapping[str, Any]) -> tuple[str, float | None]:
    for key in ("shares", "ownership_pct", "market_value_nok", "market_value_usd"):
        value = parse_number(row.get(key))
        if value is not None:
            return key, value
    return "missing", None


def compare_nbim_holdings(previous: Sequence[Mapping[str, Any]], current: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    prev_map = {_holding_key(row): dict(row) for row in previous if _holding_key(row) != "name:"}
    cur_map = {_holding_key(row): dict(row) for row in current if _holding_key(row) != "name:"}
    changes: list[dict[str, Any]] = []
    now = datetime.now().isoformat(timespec="seconds")
    for key, cur in cur_map.items():
        prev = prev_map.get(key)
        metric, cur_value = _comparison_value(cur)
        prev_value = _comparison_value(prev or {})[1] if prev else None
        if not prev:
            change_type = "Ny"
            delta_pct = None
        elif cur_value is None or prev_value in {None, 0}:
            change_type = "Uendret"
            delta_pct = None
        else:
            delta_pct = ((cur_value - float(prev_value)) / abs(float(prev_value))) * 100.0
            if delta_pct >= 5.0:
                change_type = "Okt"
            elif delta_pct <= -5.0:
                change_type = "Redusert"
            else:
                change_type = "Uendret"
        changes.append({
            **cur,
            "change_type": change_type,
            "change_metric": metric,
            "change_pct": None if delta_pct is None else round(delta_pct, 2),
            "previous_value": prev_value,
            "current_value": cur_value,
            "detected_at": now,
        })
    for key, prev in prev_map.items():
        if key in cur_map:
            continue
        metric, prev_value = _comparison_value(prev)
        changes.append({
            **prev,
            "change_type": "Solgt ut",
            "change_metric": metric,
            "change_pct": -100.0,
            "previous_value": prev_value,
            "current_value": None,
            "detected_at": now,
        })
    priority = {"Ny": 0, "Okt": 1, "Redusert": 2, "Solgt ut": 3, "Uendret": 4}
    return sorted(changes, key=lambda item: (priority.get(str(item.get("change_type")), 9), -abs(float(item.get("change_pct") or 0.0))))


def score_nbim_change(change: Mapping[str, Any]) -> float:
    change_type = _clean(change.get("change_type"))
    delta = abs(parse_number(change.get("change_pct")) or 0.0)
    ownership = parse_number(change.get("ownership_pct")) or 0.0
    size_bonus = min(10.0, ownership * 4.0)
    if change_type == "Ny":
        return min(88.0, 70.0 + size_bonus)
    if change_type == "Okt":
        return min(86.0, 62.0 + min(delta / 3.0, 16.0) + size_bonus)
    if change_type == "Redusert":
        return max(25.0, 45.0 - min(delta / 4.0, 14.0))
    if change_type == "Solgt ut":
        return 22.0
    return 52.0 + min(size_bonus, 6.0)


def build_nbim_overlay(changes: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    overlay: dict[str, dict[str, Any]] = {}
    for change in changes:
        ticker = _clean(change.get("ticker")).upper()
        if not ticker:
            continue
        score = score_nbim_change(change)
        title = f"NBIM/Oljefondet: {change.get('change_type') or 'Holding'}"
        detail = (
            f"{change.get('name') or ticker}; metric {change.get('change_metric') or '-'}; "
            f"endring {change.get('change_pct') if change.get('change_pct') is not None else 'ukjent'}%; "
            f"eierandel {change.get('ownership_pct') if change.get('ownership_pct') is not None else '-'}%."
        )
        overlay[ticker] = {
            "nbim_signal_score": round(score, 1),
            "nbim_change_type": change.get("change_type"),
            "nbim_change_pct": change.get("change_pct"),
            "nbim_market_value_nok": change.get("market_value_nok"),
            "nbim_ownership_pct": change.get("ownership_pct"),
            "nbim_evidence": [{
                "type": "Oljefond",
                "title": title,
                "source": "NBIM/Oljefondet",
                "published": str(change.get("detected_at") or ""),
                "url": NBIM_SOURCE_URL,
                "detail": detail,
            }],
        }
    return overlay


def save_nbim_overlay(overlay: Mapping[str, Mapping[str, Any]]) -> int:
    from settings_store import load_settings, save_settings

    clean = {str(key).upper(): dict(value) for key, value in overlay.items() if key and isinstance(value, Mapping)}
    settings = load_settings() or {}
    settings[NBIM_OVERLAY_SETTINGS_KEY] = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "overlay": clean,
    }
    save_settings(settings)
    return len(clean)


def load_nbim_overlay() -> dict[str, dict[str, Any]]:
    try:
        from settings_store import load_settings

        settings = load_settings() or {}
        raw = settings.get(NBIM_OVERLAY_SETTINGS_KEY)
        if isinstance(raw, Mapping) and isinstance(raw.get("overlay"), Mapping):
            return {str(key).upper(): dict(value) for key, value in raw["overlay"].items() if isinstance(value, Mapping)}
    except Exception:
        return {}
    return {}


def apply_nbim_overlay(row: Mapping[str, Any], overlay: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    out = dict(row)
    ticker = _clean(out.get("ticker")).upper()
    data = (overlay or load_nbim_overlay()).get(ticker)
    if isinstance(data, Mapping):
        out.update(dict(data))
    return out


def nbim_changes_to_json(changes: Sequence[Mapping[str, Any]]) -> bytes:
    return json.dumps(list(changes), ensure_ascii=False, indent=2, default=str).encode("utf-8")


__all__ = [
    "NBIM_OVERLAY_SETTINGS_KEY",
    "apply_nbim_overlay",
    "build_nbim_overlay",
    "compare_nbim_holdings",
    "load_nbim_overlay",
    "nbim_changes_to_json",
    "normalize_nbim_holding",
    "parse_number",
    "read_nbim_csv_bytes",
    "save_nbim_overlay",
    "score_nbim_change",
]
