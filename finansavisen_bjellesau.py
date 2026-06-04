from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import math
import re
import unicodedata
import zipfile
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any, Mapping, Sequence
from xml.etree import ElementTree as ET


FINANSAVISEN_SETTINGS_KEY = "alpha_radar_finansavisen_bjellesau_v1863bk"
FINANSAVISEN_SOURCE_URL = "https://www.finansavisen.no/bjellesauer"
FINANSAVISEN_LATEST_TRADES_URL = "https://www.finansavisen.no/bjellesauer/siste-handler"

PERIOD_OPTIONS = ("1D", "1U", "1M", "3M", "6M", "YTD", "1Y", "3Y", "ALLE")
PERIOD_WEIGHTS = {
    "1D": 1.00,
    "1U": 0.92,
    "1M": 0.82,
    "3M": 0.68,
    "6M": 0.55,
    "YTD": 0.48,
    "1Y": 0.42,
    "3Y": 0.30,
    "ALLE": 0.22,
}

MANUAL_NORWAY_TICKER_MAP = {
    "NORBIT": "NORBT.OL",
    "NORBT": "NORBT.OL",
    "AF GRUPPEN": "AFG.OL",
    "STOREBRAND": "STB.OL",
    "LINK MOBILITY": "LINK.OL",
    "MOWI": "MOWI.OL",
    "ZAPTEC": "ZAP.OL",
    "NORDIC SEMICONDUCTOR": "NOD.OL",
    "AXACTOR": "ACR.OL",
}

_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_period(value: Any) -> str:
    text = _clean(value).upper().replace(" ", "")
    aliases = {
        "1DAG": "1D",
        "1DAY": "1D",
        "1W": "1U",
        "1UKE": "1U",
        "1UK": "1U",
        "1MO": "1M",
        "1MN": "1M",
        "3MO": "3M",
        "6MO": "6M",
        "ALL": "ALLE",
        "ALT": "ALLE",
    }
    text = aliases.get(text, text)
    return text if text in PERIOD_OPTIONS else "6M"


def infer_period_from_filename(filename: str) -> str:
    text = _clean(filename).lower()
    stem = text.rsplit(".", 1)[0]
    tokens = set(re.sub(r"[^a-z0-9]+", " ", stem).split())
    compact_stem = re.sub(r"[^a-z0-9]+", "", stem)
    for marker, period in (
        ("alle", "ALLE"),
        ("all", "ALLE"),
        ("alt", "ALLE"),
        ("3y", "3Y"),
        ("1y", "1Y"),
        ("ytd", "YTD"),
        ("6m", "6M"),
        ("3m", "3M"),
        ("1m", "1M"),
        ("1u", "1U"),
        ("1w", "1U"),
        ("1d", "1D"),
    ):
        if marker in tokens or compact_stem.endswith(marker):
            return period
    return "6M"


def _normalize_header(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _clean(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _normalize_company(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _clean(value)).encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("&", " and ")
    text = re.sub(
        r"\b(the|a/s|as|asa|ab|oyj|oy|plc|inc|corp|corporation|ltd|limited|ag|sa|spa|nv|bv|co|company|group|holding|holdings|asa/adr)\b",
        " ",
        text,
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _ticker_root(value: Any) -> str:
    ticker = _clean(value).upper()
    return ticker.split(".", 1)[0].replace("-", " ")


def _parse_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = _clean(value).replace("\u00a0", " ")
    if not text:
        return None
    multiplier = 1.0
    low = text.lower()
    if re.search(r"\bmrd\b|milliard|billion", low):
        multiplier = 1_000_000_000.0
    elif re.search(r"\bmill\b|\bm\b|million", low):
        multiplier = 1_000_000.0
    elif re.search(r"\btusen\b|\bk\b", low):
        multiplier = 1_000.0
    negative = "-" in text or text.strip().startswith("(")
    text = re.sub(r"[^0-9,.\-]", "", text)
    if not text or text in {"-", ".", ","}:
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
        number = float(text)
    except Exception:
        return None
    if negative and number > 0:
        number = -number
    return number * multiplier


def format_nok(value: Any) -> str:
    number = _parse_number(value)
    if number is None:
        return "-"
    return f"{int(round(number)):,}".replace(",", ".") + " NOK"


def format_percent(value: Any) -> str:
    number = _parse_number(value)
    if number is None:
        return "-"
    text = f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".").rstrip("0").rstrip(",")
    return f"{text} %"


def sort_periods(periods: Sequence[Any]) -> list[str]:
    seen: list[str] = []
    for period in periods:
        normalized = normalize_period(period)
        if normalized not in seen:
            seen.append(normalized)
    return sorted(seen, key=lambda item: PERIOD_OPTIONS.index(item) if item in PERIOD_OPTIONS else 999)


def _excel_serial_to_date(value: float) -> str:
    try:
        return (date(1899, 12, 30) + timedelta(days=int(float(value)))).isoformat()
    except Exception:
        return ""


def _parse_date(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)):
        if 20_000 <= float(value) <= 80_000:
            return _excel_serial_to_date(float(value))
        return ""
    text = _clean(value)
    if not text:
        return ""
    if re.fullmatch(r"\d+(\.\d+)?", text):
        number = float(text)
        if 20_000 <= number <= 80_000:
            return _excel_serial_to_date(number)
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10], fmt).date().isoformat()
        except Exception:
            pass
    match = re.search(r"(\d{1,2})[.](\d{1,2})[.](\d{2,4})", text)
    if match:
        day, month, year = match.groups()
        year = "20" + year if len(year) == 2 else year
        try:
            return date(int(year), int(month), int(day)).isoformat()
        except Exception:
            return ""
    return text[:20]


def _column_index(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", _clean(cell_ref).upper())
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - 64)
    return max(0, index - 1)


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except Exception:
        return []
    strings: list[str] = []
    for si in root.findall("a:si", _NS):
        parts = []
        for node in si.iter():
            if node.tag.endswith("}t") and node.text:
                parts.append(node.text)
        strings.append("".join(parts))
    return strings


def _first_worksheet_path(zf: zipfile.ZipFile, preferred_sheet: str = "Transactions") -> str:
    fallback = "xl/worksheets/sheet1.xml"
    try:
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib.get("Id"): rel.attrib.get("Target") for rel in rels.findall("r:Relationship", _REL_NS)}
        sheets = workbook.findall("a:sheets/a:sheet", _NS)
        chosen = None
        for sheet in sheets:
            if _clean(sheet.attrib.get("name")).lower() == preferred_sheet.lower():
                chosen = sheet
                break
        if chosen is None:
            chosen = sheets[0] if sheets else None
        if chosen is None:
            return fallback
        rid = chosen.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rel_map.get(rid) or ""
        if target.startswith("/"):
            return target.lstrip("/")
        if target.startswith("worksheets/"):
            return "xl/" + target
        if target.startswith("../"):
            return target[3:]
        return "xl/" + target if target else fallback
    except Exception:
        return fallback


def _cell_value(cell: ET.Element, shared: Sequence[str]) -> Any:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        inline = cell.find("a:is", _NS)
        if inline is None:
            return ""
        return "".join(node.text or "" for node in inline.iter() if node.tag.endswith("}t"))
    value_node = cell.find("a:v", _NS)
    if value_node is None or value_node.text is None:
        return ""
    raw = value_node.text
    if cell_type == "s":
        try:
            return shared[int(raw)]
        except Exception:
            return raw
    if cell_type == "b":
        return raw == "1"
    try:
        number = float(raw)
        return int(number) if number.is_integer() else number
    except Exception:
        return raw


def read_xlsx_rows(data: bytes) -> list[list[Any]]:
    """Read values from the first worksheet without openpyxl.

    Finansavisen exports simple XLSX tables. This parser intentionally covers
    that shape only, so the app avoids a heavy dependency and hidden import work.
    """

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        shared = _shared_strings(zf)
        sheet_path = _first_worksheet_path(zf)
        root = ET.fromstring(zf.read(sheet_path))
        rows: list[list[Any]] = []
        for row in root.findall(".//a:sheetData/a:row", _NS):
            values: list[Any] = []
            for cell in row.findall("a:c", _NS):
                idx = _column_index(cell.attrib.get("r", ""))
                while len(values) <= idx:
                    values.append("")
                values[idx] = _cell_value(cell, shared)
            while values and values[-1] == "":
                values.pop()
            if any(_clean(value) for value in values):
                rows.append(values)
        return rows


def _row_dicts_from_xlsx(data: bytes) -> list[dict[str, Any]]:
    rows = read_xlsx_rows(data)
    if not rows:
        return []
    header_index = 0
    for index, values in enumerate(rows[:10]):
        normalized = {_normalize_header(value) for value in values}
        if "investor" in normalized and ("aksje" in normalized or "stock" in normalized):
            header_index = index
            break
    headers = [_clean(value) for value in rows[header_index]]
    out: list[dict[str, Any]] = []
    for values in rows[header_index + 1 :]:
        item = {}
        for index, header in enumerate(headers):
            if header:
                item[header] = values[index] if index < len(values) else ""
        if any(_clean(value) for value in item.values()):
            out.append(item)
    return out


def _first(row: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    normalized = {_normalize_header(key): value for key, value in row.items()}
    for alias in aliases:
        key = _normalize_header(alias)
        if key in normalized and normalized[key] not in {None, ""}:
            return normalized[key]
    return None


def _ticker_alias_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    try:
        from stocks import get_ticker_name_aliases

        aliases = get_ticker_name_aliases()
    except Exception:
        aliases = {}
    for ticker, names in (aliases or {}).items():
        ticker_text = _clean(ticker).upper()
        if not ticker_text:
            continue
        keys = [ticker_text, _ticker_root(ticker_text), *(names or [])]
        for key in keys:
            normalized = _normalize_company(key)
            if normalized:
                lookup.setdefault(normalized, ticker_text)
    for name, ticker in MANUAL_NORWAY_TICKER_MAP.items():
        lookup[_normalize_company(name)] = ticker
        lookup[_normalize_company(ticker)] = ticker
        lookup[_normalize_company(ticker.split(".", 1)[0])] = ticker
    return lookup


def match_finansavisen_stock_to_ticker(stock: Any, ticker_aliases: Mapping[str, str] | None = None) -> dict[str, Any]:
    text = _clean(stock)
    if not text:
        return {"ticker": "", "quality": "mangler", "alias": ""}
    lookup = dict(ticker_aliases or _ticker_alias_lookup())
    normalized = _normalize_company(text)
    ticker = lookup.get(normalized)
    if ticker:
        return {"ticker": ticker, "quality": "navn eksakt", "alias": text}
    upper = text.upper().replace(" ", "-")
    if re.fullmatch(r"[A-Z0-9-]{2,8}", upper):
        mapped = MANUAL_NORWAY_TICKER_MAP.get(upper.replace("-", " ")) or MANUAL_NORWAY_TICKER_MAP.get(upper)
        ticker = mapped or (upper + ".OL")
        return {"ticker": ticker, "quality": "oslo ticker-antakelse", "alias": text}
    best: tuple[int, str, str] | None = None
    tokens = set(normalized.split())
    for alias_key, alias_ticker in lookup.items():
        if len(alias_key) < 3:
            continue
        score = 0
        if normalized.startswith(alias_key + " ") or f" {alias_key} " in f" {normalized} ":
            score = 88
        elif alias_key.startswith(normalized + " ") and len(normalized) >= 5:
            score = 82
        elif len(alias_key.split()) == 1 and alias_key in tokens and alias_key not in {"group", "holding", "capital"}:
            score = 76
        if score and (best is None or score > best[0]):
            best = (score, alias_ticker, alias_key)
    if best:
        quality = "navn sterk" if best[0] >= 82 else "navn mulig"
        return {"ticker": best[1], "quality": quality, "alias": best[2], "score": best[0]}
    return {"ticker": "", "quality": "ingen match", "alias": text}


def _transaction_id(row: Mapping[str, Any]) -> str:
    parts = (
        row.get("investor"),
        row.get("stock_name"),
        row.get("performed_by"),
        row.get("estimated_date"),
        row.get("change_shares"),
        row.get("transaction_value_nok"),
    )
    text = "|".join(_clean(part).lower() for part in parts)
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:20]


def normalize_finansavisen_transaction(
    row: Mapping[str, Any],
    *,
    source_period: str = "6M",
    source_file: str = "",
    ticker_aliases: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    investor = _clean(_first(row, ("Investor", "investor", "navn")))
    stock_name = _clean(_first(row, ("Aksje", "Stock", "Selskap", "Ticker")))
    match = match_finansavisen_stock_to_ticker(stock_name, ticker_aliases=ticker_aliases)
    tx_value = _parse_number(_first(row, ("Transaksjonverdi", "Transaksjonsverdi", "Transaction value", "Verdi")))
    change_shares = _parse_number(_first(row, ("Endring i aksjer", "Endring aksjer", "Change in shares", "Antall")))
    relative_change = _parse_number(_first(row, ("Rel.endring", "Rel endring", "Relativ endring", "Relative change")))
    new_ownership = _parse_number(_first(row, ("Ny eierandel", "New ownership", "Eierandel")))
    new_holding = _parse_number(_first(row, ("Ny beholding", "Ny beholdning", "New holding", "Beholdning")))
    performed_by = _clean(_first(row, ("Utført av", "Utført av", "Utfort av", "Performed by", "Gjennomfort av", "Gjennomført av")))
    estimated_date = _parse_date(_first(row, ("Estimert dato", "Dato", "Date")))
    if tx_value is not None:
        side = "buy" if tx_value > 0 else "sell" if tx_value < 0 else "flat"
    elif change_shares is not None:
        side = "buy" if change_shares > 0 else "sell" if change_shares < 0 else "flat"
    else:
        side = "flat"
    normalized = {
        "transaction_id": "",
        "investor": investor,
        "stock_name": stock_name,
        "matched_ticker": _clean(match.get("ticker")).upper(),
        "ticker_match_quality": match.get("quality") or "",
        "ticker_match_alias": match.get("alias") or "",
        "change_shares": change_shares,
        "relative_change_pct": relative_change,
        "transaction_value_nok": tx_value,
        "new_ownership_pct": new_ownership,
        "new_holding": new_holding,
        "performed_by": performed_by,
        "estimated_date": estimated_date,
        "side": side,
        "source": "Finansavisen Bjellesauer",
        "source_url": FINANSAVISEN_LATEST_TRADES_URL,
        "source_file": _clean(source_file),
        "source_period": normalize_period(source_period),
        "source_periods": [normalize_period(source_period)],
        "imported_at": _now_iso(),
    }
    normalized["transaction_id"] = _transaction_id(normalized)
    return normalized


def parse_finansavisen_transaction_xlsx(
    data: bytes,
    filename: str = "",
    *,
    source_period: str | None = None,
) -> list[dict[str, Any]]:
    if not data:
        return []
    period = normalize_period(source_period or infer_period_from_filename(filename))
    ticker_aliases = _ticker_alias_lookup()
    rows = _row_dicts_from_xlsx(data)
    normalized = [
        normalize_finansavisen_transaction(row, source_period=period, source_file=filename, ticker_aliases=ticker_aliases)
        for row in rows
    ]
    return [row for row in normalized if row.get("investor") and row.get("stock_name")]


def merge_finansavisen_transactions(
    existing: Sequence[Mapping[str, Any]] | None,
    new_rows: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for raw in list(existing or []) + list(new_rows or []):
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        tx_id = _clean(row.get("transaction_id")) or _transaction_id(row)
        row["transaction_id"] = tx_id
        periods = []
        for period in list(row.get("source_periods") or []) + [row.get("source_period")]:
            normalized = normalize_period(period)
            if normalized not in periods:
                periods.append(normalized)
        row["source_periods"] = periods or ["6M"]
        row["source_period"] = periods[0] if periods else normalize_period(row.get("source_period"))
        if tx_id in by_id:
            current = by_id[tx_id]
            for period in row["source_periods"]:
                if period not in current["source_periods"]:
                    current["source_periods"].append(period)
            merged_periods = list(current["source_periods"])
            if PERIOD_WEIGHTS.get(row["source_period"], 0.0) > PERIOD_WEIGHTS.get(current.get("source_period"), 0.0):
                current.update(
                    {
                        key: value
                        for key, value in row.items()
                        if key not in {"source_period", "source_periods"} and _has_value(value)
                    }
                )
            current["source_periods"] = sort_periods(merged_periods)
            current["source_period"] = max(current["source_periods"], key=lambda period: PERIOD_WEIGHTS.get(period, 0.0))
        else:
            row["source_periods"] = sort_periods(row["source_periods"])
            by_id[tx_id] = row

    def sort_key(row: Mapping[str, Any]) -> tuple[str, float, str]:
        return (
            _clean(row.get("estimated_date")),
            abs(float(row.get("transaction_value_nok") or 0.0)),
            _clean(row.get("investor")),
        )

    return sorted(by_id.values(), key=sort_key, reverse=True)


def _days_since(iso_date: Any) -> int | None:
    text = _clean(iso_date)
    if not text:
        return None
    try:
        return max(0, (date.today() - datetime.strptime(text[:10], "%Y-%m-%d").date()).days)
    except Exception:
        return None


def _period_weight(row: Mapping[str, Any]) -> float:
    periods = list(row.get("source_periods") or [row.get("source_period")])
    return max(PERIOD_WEIGHTS.get(normalize_period(period), 0.0) for period in periods)


def _score_bucket(rows: Sequence[Mapping[str, Any]]) -> tuple[float, str, list[str]]:
    gross = sum(abs(float(row.get("transaction_value_nok") or 0.0)) for row in rows)
    buy_value = sum(max(0.0, float(row.get("transaction_value_nok") or 0.0)) for row in rows)
    sell_value = sum(abs(min(0.0, float(row.get("transaction_value_nok") or 0.0))) for row in rows)
    net = buy_value - sell_value
    unique_investors = len({_clean(row.get("investor")).lower() for row in rows if _clean(row.get("investor"))})
    period_weight = max((_period_weight(row) for row in rows), default=0.0)
    latest_days = min([value for value in (_days_since(row.get("estimated_date")) for row in rows) if value is not None] or [999])
    repeat_pairs: dict[str, int] = {}
    for row in rows:
        key = _clean(row.get("investor")).lower()
        if key:
            repeat_pairs[key] = repeat_pairs.get(key, 0) + 1
    repeats = sum(1 for count in repeat_pairs.values() if count >= 2)
    value_bonus = 0.0 if gross <= 0 else min(18.0, max(0.0, (math.log10(gross) - 5.5) * 4.5))
    net_bias = 0.0 if gross <= 0 else net / gross
    investor_bonus = min(13.0, unique_investors * 3.2)
    repeat_bonus = min(10.0, repeats * 4.0)
    fresh_bonus = period_weight * 12.0
    if latest_days <= 3:
        fresh_bonus += 8.0
    elif latest_days <= 31:
        fresh_bonus += 5.0
    elif latest_days <= 186:
        fresh_bonus += 2.0
    conflict_penalty = 0.0
    if buy_value > 0 and sell_value > 0:
        conflict_penalty = min(10.0, min(buy_value, sell_value) / max(buy_value, sell_value) * 12.0)
    score = 44.0 + value_bonus + investor_bonus + repeat_bonus + fresh_bonus + net_bias * 16.0 - conflict_penalty
    if gross <= 0:
        score = 25.0
    score = round(max(0.0, min(100.0, score)), 1)
    if net > 0 and sell_value == 0:
        label = "Bjellesau-kjop"
    elif net > 0:
        label = "Netto bjellesau-kjop"
    elif net < 0 and buy_value == 0:
        label = "Bjellesau-salg"
    elif net < 0:
        label = "Netto bjellesau-salg"
    else:
        label = "Blandet bjellesauaktivitet"
    notes = []
    if unique_investors >= 2:
        notes.append(f"{unique_investors} investorer")
    if repeats:
        notes.append("gjentatte handler")
    if latest_days <= 31:
        notes.append("ferskt")
    if buy_value and sell_value:
        notes.append("baade kjop og salg")
    return score, label, notes


def aggregate_finansavisen_by_stock(rows: Sequence[Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    source_rows = load_finansavisen_transactions() if rows is None else rows
    for raw in source_rows:
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        key = _clean(row.get("matched_ticker")).upper() or _normalize_company(row.get("stock_name"))
        if not key:
            continue
        buckets.setdefault(key, []).append(row)
    out: list[dict[str, Any]] = []
    for key, items in buckets.items():
        buy_value = sum(max(0.0, float(row.get("transaction_value_nok") or 0.0)) for row in items)
        sell_value = sum(abs(min(0.0, float(row.get("transaction_value_nok") or 0.0))) for row in items)
        gross = buy_value + sell_value
        net = buy_value - sell_value
        investors = sorted({_clean(row.get("investor")) for row in items if _clean(row.get("investor"))})
        periods = sort_periods(
            [period for row in items for period in (row.get("source_periods") or [row.get("source_period")])]
        )
        score, signal, notes = _score_bucket(items)
        sorted_items = sorted(items, key=lambda row: (_period_weight(row), _clean(row.get("estimated_date")), abs(float(row.get("transaction_value_nok") or 0.0))), reverse=True)
        latest = sorted_items[0] if sorted_items else {}
        out.append({
            "stock_key": key,
            "stock_name": _clean(latest.get("stock_name")),
            "matched_ticker": _clean(latest.get("matched_ticker")).upper(),
            "ticker_match_quality": latest.get("ticker_match_quality") or "",
            "score": score,
            "signal": signal,
            "notes": ", ".join(notes),
            "periods": periods,
            "latest_date": max((_clean(row.get("estimated_date")) for row in items), default=""),
            "transaction_count": len(items),
            "buy_count": sum(1 for row in items if row.get("side") == "buy"),
            "sell_count": sum(1 for row in items if row.get("side") == "sell"),
            "unique_investors": len(investors),
            "investors": investors[:12],
            "buy_value_nok": round(buy_value, 2),
            "sell_value_nok": round(sell_value, 2),
            "net_value_nok": round(net, 2),
            "gross_value_nok": round(gross, 2),
            "latest_new_ownership_pct": latest.get("new_ownership_pct"),
            "latest_new_holding": latest.get("new_holding"),
            "transactions": [dict(row) for row in sorted_items[:20]],
        })
    return sorted(out, key=lambda row: (float(row.get("score") or 0.0), abs(float(row.get("net_value_nok") or 0.0))), reverse=True)


def _transaction_evidence(row: Mapping[str, Any]) -> dict[str, Any]:
    side = _clean(row.get("side"))
    title_side = "kjopte" if side == "buy" else "solgte" if side == "sell" else "handlet"
    value = format_nok(row.get("transaction_value_nok"))
    detail_parts = [
        f"{row.get('investor')} {title_side} {row.get('stock_name')}",
        f"verdi {value}" if value != "-" else "",
        f"endring aksjer {int(row.get('change_shares')):,}".replace(",", ".") if row.get("change_shares") is not None else "",
        f"ny eierandel {format_percent(row.get('new_ownership_pct'))}" if row.get("new_ownership_pct") is not None else "",
        f"utført av {row.get('performed_by')}" if row.get("performed_by") else "",
        f"perioder {', '.join(row.get('source_periods') or [row.get('source_period')])}",
    ]
    evidence_type = "Bjellesau-kjop" if side == "buy" else "Bjellesau-salg" if side == "sell" else "Bjellesau-handel"
    return {
        "type": evidence_type,
        "title": f"{row.get('investor')} - {row.get('stock_name')}",
        "source": "Finansavisen Bjellesauer",
        "published": row.get("estimated_date") or row.get("imported_at") or "",
        "url": FINANSAVISEN_LATEST_TRADES_URL,
        "detail": " | ".join(part for part in detail_parts if part),
        "actor": "Bjellesau",
        "actor_roles": ["Bjellesau"],
        "strength": "Sterk" if abs(float(row.get("transaction_value_nok") or 0.0)) >= 10_000_000 else "Normal",
        "trust_level": "Importert",
        "matched_actor": row.get("investor"),
        "ticker": row.get("matched_ticker"),
        "found_by": "Finansavisen import",
    }


def build_finansavisen_overlay_snapshot(rows: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    aggregates = aggregate_finansavisen_by_stock(rows)
    by_ticker: dict[str, dict[str, Any]] = {}
    by_stock_key: dict[str, dict[str, Any]] = {}
    for item in aggregates:
        evidence = [_transaction_evidence(row) for row in item.get("transactions") or []]
        data = {
            "finansavisen_bjellesau_score": item.get("score"),
            "finansavisen_bjellesau_signal": item.get("signal"),
            "finansavisen_bjellesau_periods": item.get("periods") or [],
            "finansavisen_bjellesau_investors": item.get("investors") or [],
            "finansavisen_bjellesau_buy_value_nok": item.get("buy_value_nok"),
            "finansavisen_bjellesau_sell_value_nok": item.get("sell_value_nok"),
            "finansavisen_bjellesau_net_value_nok": item.get("net_value_nok"),
            "finansavisen_bjellesau_transaction_count": item.get("transaction_count"),
            "finansavisen_bjellesau_latest_date": item.get("latest_date"),
            "finansavisen_bjellesau_evidence": evidence[:10],
            "bjellesau_evidence": evidence[:10],
            "source_diagnostics": [{
                "type": "lokal import",
                "title": "Finansavisen Bjellesauer",
                "source": "Finansavisen import",
                "status": "lokalt snapshot",
                "detail": f"{item.get('transaction_count')} handler, perioder {', '.join(item.get('periods') or [])}, score {item.get('score')}.",
                "url": FINANSAVISEN_LATEST_TRADES_URL,
            }],
        }
        ticker = _clean(item.get("matched_ticker")).upper()
        if ticker:
            by_ticker[ticker] = data
        stock_key = _normalize_company(item.get("stock_name"))
        if stock_key:
            by_stock_key[stock_key] = data
    return {
        "updated_at": _now_iso(),
        "by_ticker": by_ticker,
        "by_stock_key": by_stock_key,
        "aggregates": aggregates,
    }


def build_finansavisen_overlay(rows: Sequence[Mapping[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    return build_finansavisen_overlay_snapshot(rows).get("by_ticker", {})


def summarize_finansavisen_transactions(rows: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    source_rows = load_finansavisen_transactions() if rows is None else rows
    rows = [dict(row) for row in source_rows if isinstance(row, Mapping)]
    investors = {_clean(row.get("investor")) for row in rows if _clean(row.get("investor"))}
    stocks = {_clean(row.get("stock_name")) for row in rows if _clean(row.get("stock_name"))}
    tickers = {_clean(row.get("matched_ticker")).upper() for row in rows if _clean(row.get("matched_ticker"))}
    periods = sort_periods([period for row in rows for period in (row.get("source_periods") or [row.get("source_period")])])
    dates = sorted(_clean(row.get("estimated_date")) for row in rows if _clean(row.get("estimated_date")))
    buy_value = sum(max(0.0, float(row.get("transaction_value_nok") or 0.0)) for row in rows)
    sell_value = sum(abs(min(0.0, float(row.get("transaction_value_nok") or 0.0))) for row in rows)
    return {
        "rows": len(rows),
        "investors": len(investors),
        "stocks": len(stocks),
        "matched_tickers": len(tickers),
        "periods": periods,
        "first_date": dates[0] if dates else "",
        "last_date": dates[-1] if dates else "",
        "buy_count": sum(1 for row in rows if row.get("side") == "buy"),
        "sell_count": sum(1 for row in rows if row.get("side") == "sell"),
        "buy_value_nok": round(buy_value, 2),
        "sell_value_nok": round(sell_value, 2),
        "net_value_nok": round(buy_value - sell_value, 2),
    }


def _settings_payload(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    clean_rows = merge_finansavisen_transactions([], rows)
    snapshot = build_finansavisen_overlay_snapshot(clean_rows)
    return {
        "updated_at": _now_iso(),
        "transactions": clean_rows,
        "summary": summarize_finansavisen_transactions(clean_rows),
        "overlay": snapshot,
    }


@lru_cache(maxsize=1)
def _load_payload_cached() -> dict[str, Any]:
    try:
        from settings_store import load_settings

        settings = load_settings() or {}
        raw = settings.get(FINANSAVISEN_SETTINGS_KEY)
        if isinstance(raw, Mapping):
            return dict(raw)
    except Exception:
        pass
    return {"transactions": [], "summary": summarize_finansavisen_transactions([]), "overlay": build_finansavisen_overlay_snapshot([])}


def reset_finansavisen_cache() -> None:
    _load_payload_cached.cache_clear()


def load_finansavisen_payload() -> dict[str, Any]:
    payload = dict(_load_payload_cached())
    payload.setdefault("transactions", [])
    payload.setdefault("summary", summarize_finansavisen_transactions(payload.get("transactions") or []))
    payload.setdefault("overlay", build_finansavisen_overlay_snapshot(payload.get("transactions") or []))
    return payload


def load_finansavisen_transactions() -> list[dict[str, Any]]:
    payload = load_finansavisen_payload()
    return [dict(row) for row in payload.get("transactions") or [] if isinstance(row, Mapping)]


def save_finansavisen_transactions(rows: Sequence[Mapping[str, Any]]) -> int:
    from settings_store import load_settings, save_settings

    payload = _settings_payload(rows)
    settings = load_settings() or {}
    settings[FINANSAVISEN_SETTINGS_KEY] = payload
    save_settings(settings)
    reset_finansavisen_cache()
    return len(payload.get("transactions") or [])


def finansavisen_status() -> dict[str, Any]:
    payload = load_finansavisen_payload()
    summary = dict(payload.get("summary") or {})
    summary["updated_at"] = payload.get("updated_at") or ""
    overlay = payload.get("overlay") if isinstance(payload.get("overlay"), Mapping) else {}
    summary["overlay_tickers"] = len((overlay.get("by_ticker") if isinstance(overlay, Mapping) else {}) or {})
    return summary


def _overlay_for_row(row: Mapping[str, Any], snapshot: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    snapshot = snapshot or (load_finansavisen_payload().get("overlay") if isinstance(load_finansavisen_payload().get("overlay"), Mapping) else {})
    ticker = _clean(row.get("ticker")).upper()
    by_ticker = snapshot.get("by_ticker") if isinstance(snapshot, Mapping) else {}
    if ticker and isinstance(by_ticker, Mapping) and ticker in by_ticker:
        return dict(by_ticker[ticker])
    stock_keys = [
        _normalize_company(row.get("name")),
        _normalize_company(row.get("company")),
        _normalize_company(row.get("ticker")),
        _normalize_company(_ticker_root(row.get("ticker"))),
    ]
    by_stock = snapshot.get("by_stock_key") if isinstance(snapshot, Mapping) else {}
    if isinstance(by_stock, Mapping):
        for key in stock_keys:
            if key and key in by_stock:
                return dict(by_stock[key])
    return None


def apply_finansavisen_bjellesau_overlay(
    row: Mapping[str, Any],
    snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    out = dict(row)
    data = _overlay_for_row(out, snapshot)
    if not data:
        return out
    existing_bj = [dict(item) for item in out.get("bjellesau_evidence") or [] if isinstance(item, Mapping)]
    existing_diag = [dict(item) for item in out.get("source_diagnostics") or [] if isinstance(item, Mapping)]
    evidence = [dict(item) for item in data.get("finansavisen_bjellesau_evidence") or [] if isinstance(item, Mapping)]
    diagnostics = [dict(item) for item in data.get("source_diagnostics") or [] if isinstance(item, Mapping)]
    out.update({key: value for key, value in data.items() if key not in {"bjellesau_evidence", "source_diagnostics"}})
    out["bjellesau_evidence"] = (existing_bj + evidence)[:12]
    out["finansavisen_bjellesau_evidence"] = evidence[:12]
    out["source_diagnostics"] = (existing_diag + diagnostics)[:20]
    score = _parse_number(data.get("finansavisen_bjellesau_score"))
    if score is not None:
        unit_score = max(0.0, min(1.0, float(score) / 100.0))
        out["bjellesau_score"] = max(_unit(out.get("bjellesau_score"), 0.0), unit_score)
        out["smart_money_score"] = max(_unit(out.get("smart_money_score"), 0.0), unit_score)
        out["owner_signal"] = max(_unit(out.get("owner_signal"), 0.0), unit_score)
    return out


def _unit(value: Any, default: float = 0.0) -> float:
    number = _parse_number(value)
    if number is None:
        return default
    if number > 10:
        number /= 100.0
    elif number > 1:
        number /= 10.0
    return max(0.0, min(1.0, float(number)))


def actor_rows_from_finansavisen_transactions(
    rows: Sequence[Mapping[str, Any]] | None = None,
    *,
    existing_rows: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    try:
        from actor_registry import actor_roles, normalize_actor_row
    except Exception:  # pragma: no cover
        return []

    merged: dict[str, dict[str, Any]] = {}
    for raw in existing_rows or []:
        if not isinstance(raw, Mapping):
            continue
        row = normalize_actor_row(raw)
        key = _clean(row.get("name") or row.get("aliases")).lower()
        if key:
            merged[key] = row

    by_investor: dict[str, list[dict[str, Any]]] = {}
    source_rows = load_finansavisen_transactions() if rows is None else rows
    for raw in source_rows:
        if not isinstance(raw, Mapping):
            continue
        investor = _clean(raw.get("investor"))
        if investor:
            by_investor.setdefault(investor.lower(), []).append(dict(raw))

    for _key, txs in by_investor.items():
        name = _clean(txs[0].get("investor"))
        current_key = name.lower()
        existing = merged.get(current_key, {})
        aliases = [name]
        for tx in txs:
            for alias in (tx.get("performed_by"), tx.get("investor")):
                text = _clean(alias)
                if text and text.lower() not in {item.lower() for item in aliases}:
                    aliases.append(text)
        tickers = []
        for tx in txs:
            ticker = _clean(tx.get("matched_ticker")).upper()
            if ticker and ticker not in tickers:
                tickers.append(ticker)
        gross = sum(abs(float(tx.get("transaction_value_nok") or 0.0)) for tx in txs)
        roles = list(actor_roles(existing)) if existing else []
        if "Bjellesau" not in roles:
            roles.append("Bjellesau")
        old_aliases = [part.strip() for part in str(existing.get("aliases") or "").replace(",", ";").split(";") if part.strip()]
        for alias in old_aliases:
            if alias.lower() not in {item.lower() for item in aliases}:
                aliases.append(alias)
        old_tickers = [part.strip().upper() for part in str(existing.get("relevant_tickers") or "").replace(",", ";").split(";") if part.strip()]
        for ticker in old_tickers:
            if ticker not in tickers:
                tickers.append(ticker)
        strength = "Sterk" if gross >= 100_000_000 or len(txs) >= 5 else existing.get("strength") or "Normal"
        note = (
            f"Importert fra Finansavisen Bjellesauer: {len(txs)} handler, "
            f"brutto {format_nok(gross)}, siste {max((_clean(tx.get('estimated_date')) for tx in txs), default='-')}."
        )
        if existing.get("notes") and "Finansavisen Bjellesauer" not in str(existing.get("notes")):
            note = str(existing.get("notes")) + " " + note
        merged[current_key] = normalize_actor_row({
            **existing,
            "active": True if existing.get("active", True) else existing.get("active"),
            "name": name,
            "aliases": "; ".join(aliases),
            "market": existing.get("market") or "Norge",
            "actor_roles": "; ".join(roles),
            "strength": strength,
            "trust_level": "Importert" if not existing else existing.get("trust_level") or "Importert",
            "relevant_tickers": "; ".join(tickers),
            "notes": note,
            "links": existing.get("links") or FINANSAVISEN_SOURCE_URL,
        })
    return list(merged.values())


def sync_finansavisen_actors_to_registry(rows: Sequence[Mapping[str, Any]] | None = None) -> int:
    from actor_registry import load_actor_registry, save_actor_registry

    existing = load_actor_registry()
    merged = actor_rows_from_finansavisen_transactions(rows, existing_rows=existing)
    return save_actor_registry(merged)


def finansavisen_transactions_to_csv(rows: Sequence[Mapping[str, Any]] | None = None) -> bytes:
    source_rows = load_finansavisen_transactions() if rows is None else rows
    rows = [dict(row) for row in source_rows if isinstance(row, Mapping)]
    fields = [
        "transaction_id",
        "source_periods",
        "investor",
        "stock_name",
        "matched_ticker",
        "ticker_match_quality",
        "side",
        "estimated_date",
        "transaction_value_nok",
        "change_shares",
        "relative_change_pct",
        "new_ownership_pct",
        "new_holding",
        "performed_by",
        "source_file",
        "source_url",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        copy = dict(row)
        copy["source_periods"] = "; ".join(copy.get("source_periods") or [])
        writer.writerow(copy)
    return buffer.getvalue().encode("utf-8-sig")


def finansavisen_transactions_to_json(rows: Sequence[Mapping[str, Any]] | None = None) -> bytes:
    source_rows = load_finansavisen_transactions() if rows is None else rows
    rows = [dict(row) for row in source_rows if isinstance(row, Mapping)]
    return json.dumps(rows, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def _score_explanation(item: Mapping[str, Any]) -> str:
    parts = []
    if item.get("unique_investors", 0) >= 2:
        parts.append(f"{item.get('unique_investors')} investorer")
    if item.get("transaction_count", 0) >= 2:
        parts.append(f"{item.get('transaction_count')} handler")
    if abs(float(item.get("net_value_nok") or 0.0)) >= 10_000_000:
        parts.append("stor nettoverdi")
    if item.get("latest_date"):
        parts.append(f"siste {item.get('latest_date')}")
    if item.get("matched_ticker"):
        parts.append("radar-klar ticker")
    else:
        parts.append("mangler ticker-match")
    return ", ".join(parts)


def finansavisen_aggregates_to_display_rows(rows: Sequence[Mapping[str, Any]] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    aggregates = aggregate_finansavisen_by_stock(rows)
    selected = aggregates[:limit] if limit else aggregates
    return [
        {
            "Score": item.get("score"),
            "Signal": item.get("signal"),
            "Ticker": item.get("matched_ticker") or "",
            "Ticker-match": item.get("ticker_match_quality") or "",
            "Aksje": item.get("stock_name") or "",
            "Perioder": ", ".join(item.get("periods") or []),
            "Siste dato": item.get("latest_date") or "",
            "Investorer": item.get("unique_investors"),
            "Handler": item.get("transaction_count"),
            "Kjop": item.get("buy_count"),
            "Salg": item.get("sell_count"),
            "Kjopsverdi": format_nok(item.get("buy_value_nok")),
            "Salgsverdi": format_nok(item.get("sell_value_nok")),
            "Netto": format_nok(item.get("net_value_nok")),
            "Navn": ", ".join(item.get("investors") or []),
            "Scoreforklaring": _score_explanation(item),
            "Notat": item.get("notes") or "",
        }
        for item in selected
    ]


def _stock_key_from_transaction(row: Mapping[str, Any]) -> str:
    return _clean(row.get("matched_ticker")).upper() or _normalize_company(row.get("stock_name"))


def _format_integer(value: Any) -> str:
    number = _parse_number(value)
    if number is None:
        return "-"
    return f"{int(round(number)):,}".replace(",", ".")


def _side_label(row: Mapping[str, Any]) -> str:
    side = _clean(row.get("side")).lower()
    if side == "buy":
        return "Kjop"
    if side == "sell":
        return "Salg"
    return "Ukjent"


def _period_text(row: Mapping[str, Any]) -> str:
    return ", ".join(sort_periods(row.get("source_periods") or [row.get("source_period")]))


def finansavisen_stock_detail_options(
    rows: Sequence[Mapping[str, Any]] | None = None,
    *,
    limit: int = 80,
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for item in aggregate_finansavisen_by_stock(rows)[:limit]:
        key = _clean(item.get("stock_key"))
        if not key:
            continue
        ticker = _clean(item.get("matched_ticker")).upper()
        name = _clean(item.get("stock_name")) or key
        label_main = ticker or name
        options.append(
            {
                "key": key,
                "label": f"{label_main} | score {item.get('score')} | netto {format_nok(item.get('net_value_nok'))}",
                "ticker": ticker,
                "stock_name": name,
                "score": item.get("score"),
                "net_value_nok": item.get("net_value_nok"),
            }
        )
    return options


def _transactions_for_stock(
    rows: Sequence[Mapping[str, Any]] | None,
    stock_key: str,
) -> list[dict[str, Any]]:
    source_rows = load_finansavisen_transactions() if rows is None else rows
    key = _clean(stock_key)
    selected = [
        dict(row)
        for row in source_rows
        if isinstance(row, Mapping) and _stock_key_from_transaction(row) == key
    ]
    return sorted(
        selected,
        key=lambda row: (
            _clean(row.get("estimated_date")),
            _period_weight(row),
            abs(float(row.get("transaction_value_nok") or 0.0)),
            _clean(row.get("investor")),
        ),
        reverse=True,
    )


def finansavisen_stock_transaction_rows(
    rows: Sequence[Mapping[str, Any]] | None,
    stock_key: str,
    *,
    limit: int = 250,
) -> list[dict[str, Any]]:
    return [
        {
            "Dato": row.get("estimated_date") or "",
            "Investor": row.get("investor") or "",
            "Side": _side_label(row),
            "Endring aksjer": _format_integer(row.get("change_shares")),
            "Verdi": format_nok(row.get("transaction_value_nok")),
            "Rel endring": format_percent(row.get("relative_change_pct")),
            "Ny eierandel": format_percent(row.get("new_ownership_pct")),
            "Ny beholdning": _format_integer(row.get("new_holding")),
            "Utfort av": row.get("performed_by") or "",
            "Perioder": _period_text(row),
        }
        for row in _transactions_for_stock(rows, stock_key)[:limit]
    ]


def finansavisen_stock_date_rows(
    rows: Sequence[Mapping[str, Any]] | None,
    stock_key: str,
    *,
    limit: int = 120,
) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in _transactions_for_stock(rows, stock_key):
        buckets.setdefault(_clean(row.get("estimated_date")) or "Ukjent dato", []).append(row)
    out: list[dict[str, Any]] = []
    for day, items in buckets.items():
        buy_value = sum(max(0.0, float(row.get("transaction_value_nok") or 0.0)) for row in items)
        sell_value = sum(abs(min(0.0, float(row.get("transaction_value_nok") or 0.0))) for row in items)
        share_net = sum(float(row.get("change_shares") or 0.0) for row in items)
        largest = max(items, key=lambda row: abs(float(row.get("transaction_value_nok") or 0.0)))
        buyers = sorted({_clean(row.get("investor")) for row in items if row.get("side") == "buy" and _clean(row.get("investor"))})
        sellers = sorted({_clean(row.get("investor")) for row in items if row.get("side") == "sell" and _clean(row.get("investor"))})
        periods = sort_periods([period for row in items for period in (row.get("source_periods") or [row.get("source_period")])])
        out.append(
            {
                "Dato": day,
                "Handler": len(items),
                "Kjop": sum(1 for row in items if row.get("side") == "buy"),
                "Salg": sum(1 for row in items if row.get("side") == "sell"),
                "Kjopsverdi": format_nok(buy_value),
                "Salgsverdi": format_nok(sell_value),
                "Netto": format_nok(buy_value - sell_value),
                "Netto aksjer": _format_integer(share_net),
                "Kjopere": ", ".join(buyers[:8]),
                "Selgere": ", ".join(sellers[:8]),
                "Storste handel": f"{largest.get('investor') or '-'} {_side_label(largest)} {format_nok(largest.get('transaction_value_nok'))}",
                "Perioder": ", ".join(periods),
            }
        )
    return sorted(out, key=lambda row: _clean(row.get("Dato")), reverse=True)[:limit]


def finansavisen_stock_person_rows(
    rows: Sequence[Mapping[str, Any]] | None,
    stock_key: str,
    *,
    limit: int = 120,
) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in _transactions_for_stock(rows, stock_key):
        investor = _clean(row.get("investor")) or "Ukjent investor"
        buckets.setdefault(investor, []).append(row)
    out: list[dict[str, Any]] = []
    for investor, items in buckets.items():
        buy_value = sum(max(0.0, float(row.get("transaction_value_nok") or 0.0)) for row in items)
        sell_value = sum(abs(min(0.0, float(row.get("transaction_value_nok") or 0.0))) for row in items)
        share_net = sum(float(row.get("change_shares") or 0.0) for row in items)
        dates = sorted(_clean(row.get("estimated_date")) for row in items if _clean(row.get("estimated_date")))
        largest = max(items, key=lambda row: abs(float(row.get("transaction_value_nok") or 0.0)))
        performed_by = sorted({_clean(row.get("performed_by")) for row in items if _clean(row.get("performed_by"))})
        periods = sort_periods([period for row in items for period in (row.get("source_periods") or [row.get("source_period")])])
        out.append(
            {
                "Investor": investor,
                "Forste dato": dates[0] if dates else "",
                "Siste dato": dates[-1] if dates else "",
                "Handler": len(items),
                "Kjop": sum(1 for row in items if row.get("side") == "buy"),
                "Salg": sum(1 for row in items if row.get("side") == "sell"),
                "Kjopsverdi": format_nok(buy_value),
                "Salgsverdi": format_nok(sell_value),
                "Netto": format_nok(buy_value - sell_value),
                "Netto aksjer": _format_integer(share_net),
                "Storste handel": f"{largest.get('estimated_date') or '-'} {_side_label(largest)} {format_nok(largest.get('transaction_value_nok'))}",
                "Utfort av": ", ".join(performed_by[:6]),
                "Perioder": ", ".join(periods),
            }
        )
    return sorted(out, key=lambda row: (_parse_number(str(row.get("Netto")).replace(" NOK", "")) or 0.0, row.get("Siste dato") or ""), reverse=True)[:limit]


def build_finansavisen_stock_detail_views(
    rows: Sequence[Mapping[str, Any]] | None,
    stock_key: str,
) -> dict[str, list[dict[str, Any]]]:
    stock_rows = [
        row
        for row in (load_finansavisen_transactions() if rows is None else rows)
        if isinstance(row, Mapping) and _stock_key_from_transaction(row) == _clean(stock_key)
    ]
    summary = finansavisen_aggregates_to_display_rows(stock_rows, limit=1)
    return {
        "Sammendrag": summary[:1],
        "Gruppert per dato": finansavisen_stock_date_rows(rows, stock_key),
        "Samlet per person": finansavisen_stock_person_rows(rows, stock_key),
        "Transaksjoner": finansavisen_stock_transaction_rows(rows, stock_key),
    }


def build_finansavisen_priority_views(rows: Sequence[Mapping[str, Any]] | None = None, limit: int = 75) -> dict[str, list[dict[str, Any]]]:
    source_rows = load_finansavisen_transactions() if rows is None else rows
    rows = [dict(row) for row in source_rows if isinstance(row, Mapping)]
    aggregates = aggregate_finansavisen_by_stock(rows)

    def top_tx(predicate, key):
        return sorted([row for row in rows if predicate(row)], key=key, reverse=True)[:limit]

    def display_tx(tx_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "Dato": row.get("estimated_date") or "",
                "Perioder": ", ".join(row.get("source_periods") or [row.get("source_period")]),
                "Investor": row.get("investor") or "",
                "Aksje": row.get("stock_name") or "",
                "Ticker": row.get("matched_ticker") or "",
                "Side": "Kjop" if row.get("side") == "buy" else "Salg" if row.get("side") == "sell" else "-",
                "Verdi": format_nok(row.get("transaction_value_nok")),
                "Endring aksjer": f"{int(row.get('change_shares')):,}".replace(",", ".") if row.get("change_shares") is not None else "-",
                "Rel endring": format_percent(row.get("relative_change_pct")),
                "Ny eierandel": format_percent(row.get("new_ownership_pct")),
                "Utført av": row.get("performed_by") or "",
            }
            for row in tx_rows
        ]

    frequent = [item for item in aggregates if item.get("transaction_count", 0) >= 2 or item.get("unique_investors", 0) >= 2]
    score_rows = finansavisen_aggregates_to_display_rows(rows, limit=limit)
    return {
        "Score per aksje": score_rows,
        "Ferskeste handler": display_tx(sorted(rows, key=lambda row: (_clean(row.get("estimated_date")), _period_weight(row)), reverse=True)[:limit]),
        "Storste kjop": display_tx(top_tx(lambda row: row.get("side") == "buy", lambda row: abs(float(row.get("transaction_value_nok") or 0.0)))),
        "Storste salg": display_tx(top_tx(lambda row: row.get("side") == "sell", lambda row: abs(float(row.get("transaction_value_nok") or 0.0)))),
        "Akkumulering per aksje": finansavisen_aggregates_to_display_rows([tx for item in aggregates if float(item.get("net_value_nok") or 0.0) > 0 for tx in item.get("transactions") or []], limit=limit),
        "Distribusjon per aksje": finansavisen_aggregates_to_display_rows([tx for item in aggregates if float(item.get("net_value_nok") or 0.0) < 0 for tx in item.get("transactions") or []], limit=limit),
        "Gjentatte signaler": [
            row for row in finansavisen_aggregates_to_display_rows([tx for item in frequent for tx in item.get("transactions") or []], limit=limit)
        ],
        "Flere bjellesauer samme aksje": [
            row
            for row in finansavisen_aggregates_to_display_rows(
                [tx for item in aggregates if int(item.get("unique_investors") or 0) >= 2 for tx in item.get("transactions") or []],
                limit=limit,
            )
        ],
        "Ticker-match": [row for row in score_rows if row.get("Ticker")],
        "Mangler ticker-match": [row for row in score_rows if not row.get("Ticker")],
        "Raadata": display_tx(rows[:limit]),
    }


def build_finansavisen_report(rows: Sequence[Mapping[str, Any]] | None = None) -> str:
    source_rows = load_finansavisen_transactions() if rows is None else rows
    rows = [dict(row) for row in source_rows if isinstance(row, Mapping)]
    summary = summarize_finansavisen_transactions(rows)
    top = finansavisen_aggregates_to_display_rows(rows, limit=25)
    lines = [
        "Finansavisen Bjellesauer - lokal importrapport",
        f"Oppdatert: {_now_iso()}",
        "",
        f"Handler: {summary['rows']} | investorer: {summary['investors']} | aksjer: {summary['stocks']} | ticker-match: {summary['matched_tickers']}",
        f"Perioder: {', '.join(summary.get('periods') or []) or '-'} | datoer: {summary.get('first_date') or '-'} til {summary.get('last_date') or '-'}",
        f"Kjop: {summary['buy_count']} / {format_nok(summary['buy_value_nok'])} | Salg: {summary['sell_count']} / {format_nok(summary['sell_value_nok'])} | Netto: {format_nok(summary['net_value_nok'])}",
        "",
        "Topp scorede aksjer:",
    ]
    for row in top:
        lines.append(
            f"- {row.get('Score')} | {row.get('Signal')} | {row.get('Ticker') or row.get('Aksje')} | "
            f"netto {row.get('Netto')} | investorer {row.get('Investorer')} | {row.get('Navn')}"
        )
    lines.extend(["", "Detalj per aksje (topp 5):"])
    for option in finansavisen_stock_detail_options(rows, limit=5):
        details = build_finansavisen_stock_detail_views(rows, option["key"])
        summary_row = (details.get("Sammendrag") or [{}])[0]
        lines.append(
            f"- {option.get('ticker') or option.get('stock_name')} | {summary_row.get('Signal', '-')} | "
            f"netto {summary_row.get('Netto', '-')} | handler {summary_row.get('Handler', '-')}"
        )
        for day_row in (details.get("Gruppert per dato") or [])[:3]:
            lines.append(
                f"  Dato {day_row.get('Dato')}: kjop {day_row.get('Kjop')} / salg {day_row.get('Salg')} | "
                f"netto {day_row.get('Netto')} | storste {day_row.get('Storste handel')}"
            )
        for person_row in (details.get("Samlet per person") or [])[:4]:
            lines.append(
                f"  Person {person_row.get('Investor')}: handler {person_row.get('Handler')} | "
                f"netto {person_row.get('Netto')} | {person_row.get('Forste dato')} til {person_row.get('Siste dato')}"
            )
    lines.extend([
        "",
        "Metode:",
        "Score vekter ferskhet, transaksjonsverdi, netto kjop/salg, antall kjente investorer og gjentatte handler.",
        "Data brukes som lokalt evidenslag i Alpha Radar/Early Warning; ingen nettverkskall kjores ved importvisning eller menyvalg.",
    ])
    return "\n".join(lines)


def _html_table(records: Sequence[Mapping[str, Any]], *, limit: int = 25) -> str:
    rows = [dict(row) for row in records[:limit] if isinstance(row, Mapping)]
    if not rows:
        return "<p class='muted'>Ingen rader.</p>"
    columns = list(rows[0].keys())
    head = "".join(f"<th>{html.escape(str(col))}</th>" for col in columns)
    body = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(str(row.get(col) or '-'))}</td>" for col in columns)
        body.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _finansavisen_detail_html_sections(rows: Sequence[Mapping[str, Any]], *, limit_stocks: int = 5) -> str:
    sections: list[str] = []
    for option in finansavisen_stock_detail_options(rows, limit=limit_stocks):
        details = build_finansavisen_stock_detail_views(rows, option["key"])
        title = option.get("ticker") or option.get("stock_name") or option["key"]
        sections.append(
            f"""
  <h2>Detalj per aksje: {html.escape(str(title))}</h2>
  <h3>Sammendrag</h3>
  {_html_table(details.get("Sammendrag") or [], limit=1)}
  <h3>Gruppert per dato</h3>
  {_html_table(details.get("Gruppert per dato") or [], limit=15)}
  <h3>Samlet per person i perioden</h3>
  {_html_table(details.get("Samlet per person") or [], limit=15)}
  <h3>Transaksjonslinjer</h3>
  {_html_table(details.get("Transaksjoner") or [], limit=30)}
"""
        )
    return "\n".join(sections)


def build_finansavisen_report_html(rows: Sequence[Mapping[str, Any]] | None = None) -> bytes:
    source_rows = load_finansavisen_transactions() if rows is None else rows
    rows = [dict(row) for row in source_rows if isinstance(row, Mapping)]
    summary = summarize_finansavisen_transactions(rows)
    views = build_finansavisen_priority_views(rows, limit=30)
    score_rows = views.get("Score per aksje", [])
    buy_rows = views.get("Storste kjop", [])
    sell_rows = views.get("Storste salg", [])
    frequent_rows = views.get("Flere bjellesauer samme aksje", [])
    match_rows = views.get("Ticker-match", [])
    detail_sections = _finansavisen_detail_html_sections(rows, limit_stocks=5)
    title = "Finansavisen Bjellesauer - rapport"
    document = f"""<!doctype html>
<html lang="no">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 28px; color: #111827; }}
    button {{ border: 1px solid #0284c7; background: #0ea5e9; color: white; border-radius: 8px; padding: 9px 14px; font-weight: 700; }}
    h1 {{ margin-bottom: 4px; }}
    h2 {{ border-top: 1px solid #d1d5db; padding-top: 14px; margin-top: 18px; }}
    h3 {{ margin: 10px 0 4px 0; font-size: 15px; }}
    .meta, .muted {{ color: #4b5563; font-size: 13px; }}
    .cards {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin: 14px 0; }}
    .card {{ border: 1px solid #d1d5db; background: #f8fafc; border-radius: 8px; padding: 10px; }}
    .card b {{ display: block; font-size: 18px; color: #064e3b; margin-top: 4px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 8px 0 10px 0; }}
    th, td {{ border: 1px solid #d1d5db; padding: 5px 7px; text-align: left; font-size: 12px; vertical-align: top; }}
    th {{ background: #f3f4f6; }}
    .method {{ background: #f8fafc; border: 1px solid #dbeafe; border-radius: 8px; padding: 10px 12px; }}
    @media print {{ button {{ display: none; }} body {{ margin: 16mm; }} h2 {{ page-break-after: avoid; }} table {{ page-break-inside: auto; }} tr {{ page-break-inside: avoid; }} }}
  </style>
</head>
<body>
  <button onclick="window.print()">Skriv ut / lagre som PDF</button>
  <h1>{html.escape(title)}</h1>
  <p class="meta">Oppdatert: {html.escape(_now_iso())} | Datakilde: lokal XLSX-import fra Finansavisen Bjellesauer</p>
  <div class="cards">
    <div class="card">Handler<b>{summary.get('rows', 0)}</b></div>
    <div class="card">Investorer<b>{summary.get('investors', 0)}</b></div>
    <div class="card">Aksjer<b>{summary.get('stocks', 0)}</b></div>
    <div class="card">Ticker-match<b>{summary.get('matched_tickers', 0)}</b></div>
    <div class="card">Netto<b>{html.escape(format_nok(summary.get('net_value_nok')))}</b></div>
  </div>
  <p class="meta">Perioder: {html.escape(', '.join(summary.get('periods') or []) or '-')} | datoer: {html.escape(str(summary.get('first_date') or '-'))} til {html.escape(str(summary.get('last_date') or '-'))}</p>
  <p class="meta">Kjop: {summary.get('buy_count', 0)} / {html.escape(format_nok(summary.get('buy_value_nok')))} | Salg: {summary.get('sell_count', 0)} / {html.escape(format_nok(summary.get('sell_value_nok')))}</p>
  <h2>Topp signaler per aksje</h2>
  {_html_table(score_rows, limit=25)}
  {detail_sections}
  <h2>Storste bjellesau-kjop</h2>
  {_html_table(buy_rows, limit=25)}
  <h2>Storste bjellesau-salg</h2>
  {_html_table(sell_rows, limit=25)}
  <h2>Flere bjellesauer samme aksje</h2>
  {_html_table(frequent_rows, limit=25)}
  <h2>Ticker-match som radarene kan bruke direkte</h2>
  {_html_table(match_rows, limit=25)}
  <h2>Metode</h2>
  <div class="method">
    <p>Score vekter ferskhet, transaksjonsverdi, netto kjop/salg, antall kjente investorer, gjentatte handler og om aksjen har ticker-match.</p>
    <p>Dette er et lokalt evidenslag for Alpha Radar, Early Warning og Beslutningsgrunnlag. Ingen nettverkskall eller Excel-parse kjores ved vanlige menyvalg.</p>
    <p>Rapporten er ikke investeringsraad. Den viser hva som er funnet i importerte Finansavisen-filer og hva som bor vurderes manuelt videre.</p>
  </div>
</body>
</html>"""
    return document.encode("utf-8")


def _pdf_escape(text: Any) -> str:
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_finansavisen_report_pdf(rows: Sequence[Mapping[str, Any]] | None = None) -> bytes:
    lines = build_finansavisen_report(rows).splitlines()
    safe_lines = ["Finansavisen Bjellesauer", "", *lines[:140]]
    chunks = [safe_lines[idx : idx + 46] for idx in range(0, len(safe_lines), 46)] or [["Finansavisen Bjellesauer"]]
    objects: list[tuple[int, bytes]] = []
    page_refs: list[str] = []
    next_obj = 4
    for page_idx, chunk in enumerate(chunks, start=1):
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
            trimmed = str(line)[:116]
            commands.append(f"50 {y} Td")
            commands.append(f"({_pdf_escape(trimmed)}) Tj")
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


def decision_rows_from_finansavisen(
    rows: Sequence[Mapping[str, Any]] | None = None,
    selected_tickers: Sequence[str] | None = None,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    selected = {str(ticker or "").strip().upper() for ticker in selected_tickers or [] if str(ticker or "").strip()}
    out: list[dict[str, Any]] = []
    for item in aggregate_finansavisen_by_stock(rows):
        ticker = _clean(item.get("matched_ticker")).upper()
        if not ticker:
            continue
        if selected and ticker not in selected:
            continue
        score = float(item.get("score") or 0.0)
        evidence = [_transaction_evidence(row) for row in item.get("transactions") or []]
        out.append({
            "ticker": ticker,
            "name": item.get("stock_name") or ticker,
            "market": "Norge" if ticker.endswith(".OL") else "",
            "decision_source": "Finansavisen Bjellesauer",
            "source_scope": "Lokal Finansavisen-import",
            "source_horizon": ", ".join(item.get("periods") or []),
            "score": score,
            "alpha_score": score,
            "bjellesau_score": score,
            "evidence_score": min(100.0, 45.0 + score / 2.0),
            "insider_score": 0.0,
            "catalyst_score": 0.0,
            "why_now": f"{item.get('signal')} med netto {format_nok(item.get('net_value_nok'))}, {item.get('unique_investors')} investorer og {item.get('transaction_count')} handler.",
            "thesis": _score_explanation(item),
            "signals": [item.get("signal"), "Finansavisen Bjellesauer"],
            "finansavisen_bjellesau_evidence": evidence[:10],
            "bjellesau_evidence": evidence[:10],
            "source_diagnostics": [{
                "type": "lokal import",
                "source": "Finansavisen Bjellesauer",
                "detail": _score_explanation(item),
                "url": FINANSAVISEN_LATEST_TRADES_URL,
            }],
            "queued_at": _now_iso(),
        })
        if len(out) >= limit:
            break
    return out


__all__ = [
    "FINANSAVISEN_SETTINGS_KEY",
    "PERIOD_OPTIONS",
    "aggregate_finansavisen_by_stock",
    "apply_finansavisen_bjellesau_overlay",
    "actor_rows_from_finansavisen_transactions",
    "build_finansavisen_overlay",
    "build_finansavisen_overlay_snapshot",
    "build_finansavisen_priority_views",
    "build_finansavisen_report",
    "build_finansavisen_report_html",
    "build_finansavisen_report_pdf",
    "build_finansavisen_stock_detail_views",
    "decision_rows_from_finansavisen",
    "finansavisen_aggregates_to_display_rows",
    "finansavisen_status",
    "finansavisen_stock_date_rows",
    "finansavisen_stock_detail_options",
    "finansavisen_stock_person_rows",
    "finansavisen_stock_transaction_rows",
    "finansavisen_transactions_to_csv",
    "finansavisen_transactions_to_json",
    "format_nok",
    "format_percent",
    "sort_periods",
    "infer_period_from_filename",
    "load_finansavisen_payload",
    "load_finansavisen_transactions",
    "match_finansavisen_stock_to_ticker",
    "merge_finansavisen_transactions",
    "normalize_finansavisen_transaction",
    "normalize_period",
    "parse_finansavisen_transaction_xlsx",
    "read_xlsx_rows",
    "reset_finansavisen_cache",
    "save_finansavisen_transactions",
    "summarize_finansavisen_transactions",
    "sync_finansavisen_actors_to_registry",
]
