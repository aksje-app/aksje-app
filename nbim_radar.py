from __future__ import annotations

import csv
import io
import json
import math
import re
import unicodedata
from datetime import datetime
from typing import Any, Mapping, Sequence


NBIM_OVERLAY_SETTINGS_KEY = "nbim_radar_overlay_v1863bd"
NBIM_SOURCE_URL = "https://www.nbim.no/en/the-fund/investments/"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _clean(value).lower())


def _decode_csv_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "latin-1"):
        try:
            text = data.decode(encoding)
            if "Region" in text[:200] or "Name" in text[:200] or ";" in text[:200]:
                return text
        except Exception:
            continue
    return data.decode("utf-8", errors="replace")


def _normalize_company(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _clean(value)).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"\b(the|a/s|as|asa|ab|oyj|oy|plc|inc|corp|corporation|ltd|limited|ag|sa|spa|nv|bv|co|company|group|holding|holdings)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _country_suffix(country: Any) -> tuple[str, ...]:
    text = _clean(country).lower()
    if "norway" in text:
        return (".OL",)
    if "sweden" in text:
        return (".ST",)
    if "denmark" in text:
        return (".CO",)
    if "finland" in text:
        return (".HE",)
    if "brazil" in text:
        return (".SA",)
    if "united states" in text or text == "usa":
        return ("",)
    return ()


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
        "region": _clean(_first(row, ("region",))),
        "sector": sector,
        "market_value_nok": market_value_nok,
        "market_value_usd": market_value_usd,
        "ownership_pct": ownership_pct,
        "voting_pct": voting_pct,
        "shares": shares,
        "isin": _clean(_first(row, ("isin", "isin code"))).upper(),
    }


def read_nbim_csv_bytes(data: bytes) -> list[dict[str, Any]]:
    text = _decode_csv_bytes(data)
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except Exception:
        delimiter = ";" if sample.count(";") >= max(sample.count(","), sample.count("\t")) else "\t" if sample.count("\t") > sample.count(",") else ","
        class _Dialect(csv.excel):
            pass
        dialect = _Dialect
        dialect.delimiter = delimiter
    rows: list[dict[str, Any]] = []
    for raw in csv.DictReader(io.StringIO(text), dialect=dialect):
        if not isinstance(raw, Mapping):
            continue
        item = normalize_nbim_holding(raw)
        if item.get("ticker") or item.get("name"):
            rows.append(item)
    return rows


def nbim_file_diagnostics(rows: Sequence[Mapping[str, Any]], overlay: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    overlay = overlay or {}
    countries: dict[str, int] = {}
    sectors: dict[str, int] = {}
    for row in rows or []:
        country = _clean(row.get("country")) or "Ukjent"
        sector = _clean(row.get("sector")) or "Ukjent"
        countries[country] = countries.get(country, 0) + 1
        sectors[sector] = sectors.get(sector, 0) + 1
    return {
        "rows": len(rows or []),
        "matched_tickers": len(overlay),
        "unmatched_rows": max(0, len(rows or []) - len(overlay)),
        "countries": dict(sorted(countries.items(), key=lambda item: item[1], reverse=True)[:12]),
        "sectors": dict(sorted(sectors.items(), key=lambda item: item[1], reverse=True)[:12]),
    }


def _holding_key(row: Mapping[str, Any]) -> str:
    ticker = _clean(row.get("ticker")).upper()
    if ticker:
        return f"ticker:{ticker}"
    isin = _clean(row.get("isin")).upper()
    if isin:
        return f"isin:{isin}"
    return "name:" + _normalize_key(row.get("name"))


def _comparison_value(row: Mapping[str, Any]) -> tuple[str, float | None]:
    for key in ("shares", "ownership_pct", "market_value_nok", "market_value_usd"):
        value = parse_number(row.get(key))
        if value is not None:
            return key, value
    return "missing", None


def _pct_delta(previous: Any, current: Any, *, sold_out: bool = False) -> float | None:
    prev_value = parse_number(previous)
    cur_value = parse_number(current)
    if sold_out and prev_value not in {None, 0}:
        return -100.0
    if prev_value in {None, 0} or cur_value is None:
        return None
    return round(((cur_value - float(prev_value)) / abs(float(prev_value))) * 100.0, 2)


def _with_metric_deltas(
    row: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any] | None,
    *,
    sold_out: bool = False,
) -> dict[str, Any]:
    out = dict(row)
    for key in ("shares", "ownership_pct", "voting_pct", "market_value_nok", "market_value_usd"):
        prev_value = parse_number((previous or {}).get(key))
        cur_value = None if sold_out else parse_number((current or {}).get(key))
        out[f"previous_{key}"] = prev_value
        out[f"current_{key}"] = cur_value
        out[f"{key}_change_pct"] = _pct_delta(prev_value, cur_value, sold_out=sold_out)
    return out


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
        changes.append(_with_metric_deltas({
            **cur,
            "change_type": change_type,
            "change_metric": metric,
            "change_pct": None if delta_pct is None else round(delta_pct, 2),
            "previous_value": prev_value,
            "current_value": cur_value,
            "detected_at": now,
        }, prev, cur))
    for key, prev in prev_map.items():
        if key in cur_map:
            continue
        metric, prev_value = _comparison_value(prev)
        changes.append(_with_metric_deltas({
            **prev,
            "change_type": "Solgt ut",
            "change_metric": metric,
            "change_pct": -100.0,
            "previous_value": prev_value,
            "current_value": None,
            "detected_at": now,
        }, prev, None, sold_out=True))
    priority = {"Ny": 0, "Okt": 1, "Redusert": 2, "Solgt ut": 3, "Uendret": 4}
    return sorted(changes, key=lambda item: (priority.get(str(item.get("change_type")), 9), -abs(float(item.get("change_pct") or 0.0))))


def build_ticker_alias_index(ticker_aliases: Mapping[str, Sequence[str]] | None = None) -> list[dict[str, Any]]:
    if ticker_aliases is None:
        try:
            from stocks import get_ticker_name_aliases

            ticker_aliases = get_ticker_name_aliases()
        except Exception:
            ticker_aliases = {}
    index: list[dict[str, Any]] = []
    for ticker, aliases in (ticker_aliases or {}).items():
        ticker_text = _clean(ticker).upper()
        suffixes = _country_suffix({
            ".OL": "Norway",
            ".ST": "Sweden",
            ".CO": "Denmark",
            ".HE": "Finland",
            ".SA": "Brazil",
        }.get("." + ticker_text.rsplit(".", 1)[-1] if "." in ticker_text else "", "United States"))
        all_aliases = list(aliases or [])
        root = ticker_text.split(".", 1)[0].replace("-", " ")
        all_aliases.append(root)
        for alias in all_aliases:
            normalized = _normalize_company(alias)
            if len(normalized) < 3 and not any(ch.isdigit() for ch in normalized):
                continue
            index.append({
                "ticker": ticker_text,
                "alias": alias,
                "normalized": normalized,
                "suffixes": suffixes,
            })
    return index


def build_ticker_alias_lookup(ticker_aliases: Mapping[str, Sequence[str]] | None = None) -> dict[str, Any]:
    entries = build_ticker_alias_index(ticker_aliases)
    exact: dict[str, list[dict[str, Any]]] = {}
    token: dict[str, list[dict[str, Any]]] = {}
    first_token: dict[str, list[dict[str, Any]]] = {}
    for item in entries:
        alias = _clean(item.get("normalized"))
        if not alias:
            continue
        exact.setdefault(alias, []).append(dict(item))
        tokens = alias.split()
        if len(tokens) == 1:
            token.setdefault(alias, []).append(dict(item))
        else:
            first_token.setdefault(tokens[0], []).append(dict(item))
    return {
        "entries": entries,
        "exact": exact,
        "token": token,
        "first_token": first_token,
    }


def match_nbim_holding_to_ticker(row: Mapping[str, Any], alias_index: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None) -> dict[str, Any]:
    explicit = _clean(row.get("ticker")).upper()
    if explicit:
        return {"ticker": explicit, "quality": "ticker", "alias": explicit}
    name = _normalize_company(row.get("name"))
    if not name:
        return {"ticker": "", "quality": "mangler", "alias": ""}
    suffixes = _country_suffix(row.get("country"))
    candidates = []
    generic_single_aliases = {"investor", "capital", "holding", "holdings", "group", "bank", "energy", "de"}
    name_tokens = name.split()
    if isinstance(alias_index, Mapping) and "entries" in alias_index:
        candidate_items: list[Mapping[str, Any]] = []
        seen_items: set[tuple[str, str]] = set()
        for item in alias_index.get("exact", {}).get(name, []):
            key = (_clean(item.get("ticker")), _clean(item.get("normalized")))
            if key not in seen_items:
                seen_items.add(key)
                candidate_items.append(item)
        for token_value in name_tokens:
            for item in alias_index.get("token", {}).get(token_value, []):
                key = (_clean(item.get("ticker")), _clean(item.get("normalized")))
                if key not in seen_items:
                    seen_items.add(key)
                    candidate_items.append(item)
            for item in alias_index.get("first_token", {}).get(token_value, []):
                key = (_clean(item.get("ticker")), _clean(item.get("normalized")))
                if key not in seen_items:
                    seen_items.add(key)
                    candidate_items.append(item)
    else:
        candidate_items = list(alias_index or build_ticker_alias_index())
    for item in candidate_items:
        ticker = _clean(item.get("ticker")).upper()
        if suffixes and ticker.endswith(tuple(suffixes)) is False:
            continue
        alias = _clean(item.get("normalized"))
        if not alias:
            continue
        alias_tokens = alias.split()
        score = 0
        if name == alias:
            score = 100
        elif len(alias_tokens) >= 2 and len(alias) >= 5 and (name.startswith(alias + " ") or f" {alias} " in f" {name} "):
            score = 88
        elif len(alias_tokens) == 1 and len(alias) >= 3 and alias not in generic_single_aliases and alias in name_tokens:
            score = 84
        elif len(name.split()) >= 2 and len(name) >= 6 and name in alias:
            score = 82
        if score:
            if suffixes:
                score += 5
            candidates.append((score, ticker, item.get("alias")))
    if not candidates:
        return {"ticker": "", "quality": "ingen match", "alias": ""}
    candidates.sort(reverse=True)
    score, ticker, alias = candidates[0]
    quality = "navn eksakt" if score >= 100 else "navn sterk" if score >= 88 else "navn mulig"
    return {"ticker": ticker, "quality": quality, "alias": alias, "score": score}


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


def _format_decimal(value: float, decimals: int = 2) -> str:
    text = f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if "," in text:
        text = text.rstrip("0").rstrip(",")
    return text


def format_nbim_amount(value: Any, currency: str = "NOK") -> str:
    number = parse_number(value)
    if number is None:
        return "-"
    return f"{int(round(number)):,}".replace(",", ".") + f" {currency}"


def format_nbim_percent(value: Any) -> str:
    number = parse_number(value)
    if number is None:
        return "-"
    return f"{_format_decimal(number, 2)} %"


def format_nbim_shares(value: Any) -> str:
    number = parse_number(value)
    if number is None:
        return "-"
    return f"{int(round(number)):,}".replace(",", ".") + " aksjer"


def nbim_metric_label(metric: Any) -> str:
    labels = {
        "shares": "aksjer",
        "ownership_pct": "eierandel",
        "voting_pct": "stemmeandel",
        "market_value_nok": "markedsverdi NOK",
        "market_value_usd": "markedsverdi USD",
    }
    return labels.get(_clean(metric), _clean(metric) or "-")


def format_nbim_metric_value(metric: Any, value: Any) -> str:
    metric_key = _clean(metric)
    if metric_key == "ownership_pct" or metric_key == "voting_pct":
        return format_nbim_percent(value)
    if metric_key == "shares":
        return format_nbim_shares(value)
    if metric_key == "market_value_nok":
        return format_nbim_amount(value, "NOK")
    if metric_key == "market_value_usd":
        return format_nbim_amount(value, "USD")
    number = parse_number(value)
    if number is None:
        return "-"
    return _format_decimal(number, 2)


def _market_value_nok(row: Mapping[str, Any]) -> float:
    return parse_number(row.get("market_value_nok")) or 0.0


def _market_value_usd(row: Mapping[str, Any]) -> float:
    return parse_number(row.get("market_value_usd")) or 0.0


def _size_bonus(value_nok: float) -> float:
    if value_nok <= 0:
        return 0.0
    return max(0.0, min(30.0, (math.log10(value_nok) - 6.0) * 5.0))


def score_nbim_priority(change: Mapping[str, Any], match: Mapping[str, Any] | None = None) -> float:
    change_type = _clean(change.get("change_type"))
    base = {
        "Ny": 42.0,
        "Okt": 38.0,
        "Redusert": 26.0,
        "Solgt ut": 34.0,
        "Uendret": 8.0,
    }.get(change_type, 10.0)
    size = _size_bonus(_market_value_nok(change))
    delta = min(16.0, abs(parse_number(change.get("change_pct")) or 0.0) / 4.0)
    ownership = max(parse_number(change.get("ownership_pct")) or 0.0, parse_number(change.get("voting_pct")) or 0.0)
    owner_bonus = min(16.0, ownership * 3.0)
    match_bonus = 8.0 if _clean((match or {}).get("ticker")) else 0.0
    if change_type == "Redusert" and _market_value_nok(change) > 0:
        base += 6.0
    if change_type == "Solgt ut":
        owner_bonus = min(owner_bonus, 8.0)
    return round(max(0.0, min(100.0, base + size + delta + owner_bonus + match_bonus)), 1)


def _change_delta(row: Mapping[str, Any], key: str) -> float | None:
    return parse_number(row.get(f"{key}_change_pct"))


def _previous_market_value_nok(row: Mapping[str, Any]) -> float:
    return parse_number(row.get("previous_market_value_nok")) or _market_value_nok(row)


def nbim_signal_tags(change: Mapping[str, Any]) -> list[str]:
    tags: list[str] = []
    change_type = _clean(change.get("change_type"))
    market_value = _market_value_nok(change)
    previous_value = _previous_market_value_nok(change)
    ownership = parse_number(change.get("ownership_pct")) or 0.0
    voting = parse_number(change.get("voting_pct")) or 0.0
    ownership_delta = _change_delta(change, "ownership_pct")
    market_value_delta = _change_delta(change, "market_value_nok")
    voting_gap = abs(voting - ownership) if voting or ownership else 0.0

    if change_type == "Ny":
        tags.append("Nytt kjop")
    elif change_type == "Okt":
        tags.append("Okt eierandel")
    elif change_type == "Redusert":
        tags.append("Redusert")
    elif change_type == "Solgt ut":
        tags.append("Solgt ut")

    if market_value >= 10_000_000_000:
        tags.append("Stor beholdning")
    elif market_value >= 1_000_000_000:
        tags.append("Milliardposisjon")
    if change_type == "Ny" and market_value >= 1_000_000_000:
        tags.append("Stort nytt kjop")
    if ownership_delta is not None and ownership_delta > 0 and market_value_delta is not None and market_value_delta < 0:
        tags.append("Akkumulering i svakhet")
    if change_type == "Redusert" and market_value >= 1_000_000_000:
        tags.append("Redusert med restverdi")
    if change_type == "Solgt ut" and previous_value >= 1_000_000_000:
        tags.append("Stor exit")
    if ownership >= 5.0 or voting >= 5.0:
        tags.append("Hoy eier/stemmeandel")
    elif ownership >= 3.0 or voting >= 3.0:
        tags.append("Betydelig eierandel")
    if voting_gap >= 0.5:
        tags.append("Stemmeavvik")
    if _clean(change.get("matched_ticker")):
        tags.append("Ticker-match")
    if change.get("radar_overlap"):
        tags.append("Radar-overlap")
    return list(dict.fromkeys(tags))


def score_nbim_conviction(change: Mapping[str, Any]) -> float:
    score = float(change.get("nbim_priority_score") or 0.0)
    weights = {
        "Nytt kjop": 4.0,
        "Okt eierandel": 4.0,
        "Stort nytt kjop": 8.0,
        "Akkumulering i svakhet": 10.0,
        "Redusert med restverdi": 5.0,
        "Stor exit": 8.0,
        "Hoy eier/stemmeandel": 8.0,
        "Betydelig eierandel": 4.0,
        "Stemmeavvik": 3.0,
        "Ticker-match": 4.0,
        "Radar-overlap": 12.0,
    }
    for tag in change.get("nbim_signals") or nbim_signal_tags(change):
        score += weights.get(str(tag), 0.0)
    return round(max(0.0, min(100.0, score)), 1)


def _priority_reason(change: Mapping[str, Any], match: Mapping[str, Any] | None = None) -> str:
    parts = []
    change_type = _clean(change.get("change_type")) or "Holding"
    parts.append(change_type)
    value = _market_value_nok(change)
    if value:
        parts.append(format_nbim_amount(value, "NOK"))
    ownership = parse_number(change.get("ownership_pct"))
    if ownership is not None:
        parts.append("eierandel " + format_nbim_percent(ownership))
    voting = parse_number(change.get("voting_pct"))
    if voting is not None and voting != ownership:
        parts.append("stemmeandel " + format_nbim_percent(voting))
    change_pct = parse_number(change.get("change_pct"))
    if change_pct is not None:
        parts.append("endring " + format_nbim_percent(change_pct))
    ticker = _clean((match or {}).get("ticker"))
    if ticker:
        parts.append("ticker-match " + ticker)
    return "; ".join(parts)


def annotate_nbim_changes(
    changes: Sequence[Mapping[str, Any]],
    ticker_aliases: Mapping[str, Sequence[str]] | None = None,
    radar_tickers: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    alias_index = build_ticker_alias_lookup(ticker_aliases)
    radar_lookup = {str(ticker or "").strip().upper() for ticker in (radar_tickers or []) if str(ticker or "").strip()}
    annotated: list[dict[str, Any]] = []
    for row in changes:
        item = dict(row)
        match = match_nbim_holding_to_ticker(item, alias_index)
        item["matched_ticker"] = _clean(match.get("ticker")).upper()
        item["ticker_match_quality"] = match.get("quality") or ""
        item["ticker_match_alias"] = match.get("alias") or ""
        item["ticker_match_score"] = match.get("score")
        item["nbim_priority_score"] = score_nbim_priority(item, match)
        item["radar_overlap"] = bool(item["matched_ticker"] and item["matched_ticker"] in radar_lookup)
        item["nbim_signals"] = nbim_signal_tags(item)
        item["nbim_conviction_score"] = score_nbim_conviction(item)
        item["nbim_priority_reason"] = _priority_reason(item, match)
        if item["nbim_signals"]:
            item["nbim_priority_reason"] += "; signaler: " + ", ".join(item["nbim_signals"][:6])
        annotated.append(item)
    ticker_change_types: dict[str, set[str]] = {}
    for item in annotated:
        ticker = _clean(item.get("matched_ticker")).upper()
        if not ticker:
            continue
        ticker_change_types.setdefault(ticker, set()).add(_clean(item.get("change_type")))
    for item in annotated:
        ticker = _clean(item.get("matched_ticker")).upper()
        types = ticker_change_types.get(ticker) or set()
        if ticker and "Solgt ut" in types and any(change_type != "Solgt ut" for change_type in types):
            signals = list(item.get("nbim_signals") or [])
            if "Mulig navnebytte/dobbeltmatch" not in signals:
                signals.append("Mulig navnebytte/dobbeltmatch")
            item["nbim_signals"] = signals
            item["nbim_priority_reason"] += "; merk: samme ticker har baade aktiv og solgt-ut rad"
    return annotated


def build_nbim_priority_views(changes: Sequence[Mapping[str, Any]], limit: int = 50) -> dict[str, list[dict[str, Any]]]:
    annotated = annotate_nbim_changes(changes) if changes and "nbim_priority_score" not in changes[0] else [dict(row) for row in changes]

    def top(rows: Sequence[Mapping[str, Any]], key) -> list[dict[str, Any]]:
        return [dict(row) for row in sorted(rows, key=key, reverse=True)[:limit]]

    active = [row for row in annotated if row.get("change_type") != "Solgt ut"]
    reduced = [row for row in annotated if row.get("change_type") == "Redusert"]
    unmatched = [row for row in annotated if not row.get("matched_ticker")]
    views = {
        "Topp signaler": top(annotated, lambda row: float(row.get("nbim_conviction_score") or row.get("nbim_priority_score") or 0.0)),
        "Overbevisning": top(annotated, lambda row: float(row.get("nbim_conviction_score") or 0.0)),
        "Storste beholdninger": top(active, lambda row: _market_value_nok(row)),
        "Storste nye kjop": top([row for row in annotated if row.get("change_type") == "Ny"], lambda row: _market_value_nok(row)),
        "Storste okninger": top([row for row in annotated if row.get("change_type") == "Okt"], lambda row: (float(row.get("nbim_conviction_score") or 0.0), _market_value_nok(row))),
        "Akkumulering svakhet": top([row for row in annotated if "Akkumulering i svakhet" in (row.get("nbim_signals") or [])], lambda row: float(row.get("nbim_conviction_score") or 0.0)),
        "Redusert med restverdi": top([row for row in reduced if _market_value_nok(row) > 0], lambda row: _market_value_nok(row)),
        "Solgt ut": top([row for row in annotated if row.get("change_type") == "Solgt ut"], lambda row: _market_value_nok(row)),
        "Hoy eierandel": top([row for row in annotated if "Hoy eier/stemmeandel" in (row.get("nbim_signals") or []) or "Betydelig eierandel" in (row.get("nbim_signals") or [])], lambda row: float(row.get("nbim_conviction_score") or 0.0)),
        "Stemmerett-avvik": top([row for row in annotated if "Stemmeavvik" in (row.get("nbim_signals") or [])], lambda row: float(row.get("nbim_conviction_score") or 0.0)),
        "Unmatched verdi": top(unmatched, lambda row: _market_value_nok(row)),
        "Radar-overlap": top([row for row in annotated if row.get("radar_overlap")], lambda row: float(row.get("nbim_conviction_score") or 0.0)),
        "Ticker-match": top([row for row in annotated if row.get("matched_ticker")], lambda row: float(row.get("nbim_conviction_score") or 0.0)),
        "NBIM-watchlist": build_nbim_watchlist(annotated, limit=limit),
        "Radata": [dict(row) for row in annotated[:limit]],
    }
    return views


def build_nbim_watchlist(changes: Sequence[Mapping[str, Any]], limit: int = 50) -> list[dict[str, Any]]:
    annotated = annotate_nbim_changes(changes) if changes and "nbim_signals" not in changes[0] else [dict(row) for row in changes]
    watch_tags = {
        "Stort nytt kjop",
        "Akkumulering i svakhet",
        "Redusert med restverdi",
        "Stor exit",
        "Hoy eier/stemmeandel",
        "Radar-overlap",
    }
    selected = []
    for row in annotated:
        signals = set(str(tag) for tag in row.get("nbim_signals") or [])
        if signals & watch_tags or float(row.get("nbim_conviction_score") or 0.0) >= 78.0:
            item = dict(row)
            item["watchlist_reason"] = ", ".join([tag for tag in item.get("nbim_signals") or [] if tag in watch_tags]) or item.get("nbim_priority_reason") or "-"
            selected.append(item)
    if not selected:
        selected = sorted(annotated, key=lambda row: float(row.get("nbim_conviction_score") or 0.0), reverse=True)[:limit]
    seen: set[str] = set()
    unique = []
    for row in sorted(selected, key=lambda item: float(item.get("nbim_conviction_score") or 0.0), reverse=True):
        key = _clean(row.get("matched_ticker") or row.get("ticker") or row.get("isin") or row.get("name")).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(dict(row))
        if len(unique) >= limit:
            break
    return unique


def nbim_changes_to_display_rows(changes: Sequence[Mapping[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    rows = list(changes)[:limit] if limit else list(changes)
    display: list[dict[str, Any]] = []
    for row in rows:
        metric = row.get("change_metric")
        display.append({
            "Score": row.get("nbim_conviction_score") or row.get("nbim_priority_score"),
            "Prioritet": row.get("nbim_priority_score"),
            "Ticker": row.get("matched_ticker") or row.get("ticker") or "",
            "Ticker-match": row.get("ticker_match_quality") or "",
            "Selskap": row.get("name") or "",
            "Land": row.get("country") or "",
            "Region": row.get("region") or "",
            "Sektor": row.get("sector") or "",
            "Signaler": ", ".join(str(tag) for tag in row.get("nbim_signals") or []),
            "Endring": row.get("change_type") or "",
            "Endring %": format_nbim_percent(row.get("change_pct")),
            "Eierandel endr.": format_nbim_percent(row.get("ownership_pct_change_pct")),
            "Markedsverdi endr.": format_nbim_percent(row.get("market_value_nok_change_pct")),
            "Markedsverdi NOK": format_nbim_amount(row.get("market_value_nok"), "NOK"),
            "Markedsverdi USD": format_nbim_amount(row.get("market_value_usd"), "USD"),
            "Eierandel": format_nbim_percent(row.get("ownership_pct")),
            "Stemmeandel": format_nbim_percent(row.get("voting_pct")),
            "Malt verdi": nbim_metric_label(metric),
            "Forrige verdi": format_nbim_metric_value(metric, row.get("previous_value")),
            "Naa-verdi": format_nbim_metric_value(metric, row.get("current_value")),
            "Forklaring": row.get("nbim_priority_reason") or "",
        })
    return display


def nbim_group_summary(changes: Sequence[Mapping[str, Any]], group_key: str) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for row in changes:
        label = _clean(row.get(group_key)) or "Ukjent"
        bucket = groups.setdefault(label, {
            "Navn": label,
            "Rader": 0,
            "Ny": 0,
            "Okt": 0,
            "Redusert": 0,
            "Solgt ut": 0,
            "Markedsverdi NOK": 0.0,
            "Ny verdi NOK": 0.0,
            "Okt verdi NOK": 0.0,
            "Redusert restverdi NOK": 0.0,
            "Solgt ut tidligere NOK": 0.0,
            "Score": 0.0,
        })
        change_type = _clean(row.get("change_type"))
        bucket["Rader"] += 1
        if change_type in {"Ny", "Okt", "Redusert", "Solgt ut"}:
            bucket[change_type] += 1
        if change_type != "Solgt ut":
            bucket["Markedsverdi NOK"] += _market_value_nok(row)
        if change_type == "Ny":
            bucket["Ny verdi NOK"] += _market_value_nok(row)
        elif change_type == "Okt":
            bucket["Okt verdi NOK"] += _market_value_nok(row)
        elif change_type == "Redusert":
            bucket["Redusert restverdi NOK"] += _market_value_nok(row)
        elif change_type == "Solgt ut":
            bucket["Solgt ut tidligere NOK"] += _previous_market_value_nok(row)
        bucket["Score"] = max(float(bucket["Score"]), float(row.get("nbim_conviction_score") or row.get("nbim_priority_score") or 0.0))
    out = []
    for bucket in groups.values():
        item = dict(bucket)
        net_bias = float(bucket["Ny"]) + float(bucket["Okt"]) - float(bucket["Redusert"]) - float(bucket["Solgt ut"])
        item["Rotasjon"] = "Inn" if net_bias > 0 else "Ut" if net_bias < 0 else "Blandet"
        item["Markedsverdi NOK"] = format_nbim_amount(item["Markedsverdi NOK"], "NOK")
        item["Ny verdi NOK"] = format_nbim_amount(item["Ny verdi NOK"], "NOK")
        item["Okt verdi NOK"] = format_nbim_amount(item["Okt verdi NOK"], "NOK")
        item["Redusert restverdi NOK"] = format_nbim_amount(item["Redusert restverdi NOK"], "NOK")
        item["Solgt ut tidligere NOK"] = format_nbim_amount(item["Solgt ut tidligere NOK"], "NOK")
        item["Score"] = round(float(item["Score"]), 1)
        out.append(item)
    return sorted(out, key=lambda row: (float(row.get("Score") or 0.0), int(row.get("Rader") or 0)), reverse=True)


def build_nbim_overlay(
    changes: Sequence[Mapping[str, Any]],
    ticker_aliases: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, dict[str, Any]]:
    overlay: dict[str, dict[str, Any]] = {}
    alias_index = build_ticker_alias_lookup(ticker_aliases)
    for change in changes:
        if _clean(change.get("matched_ticker")):
            match = {
                "ticker": _clean(change.get("matched_ticker")).upper(),
                "quality": change.get("ticker_match_quality") or "forhandsmatchet",
                "alias": change.get("ticker_match_alias") or change.get("matched_ticker"),
                "score": change.get("ticker_match_score") or 0,
            }
        else:
            match = match_nbim_holding_to_ticker(change, alias_index)
        ticker = _clean(match.get("ticker")).upper()
        if not ticker:
            continue
        score = score_nbim_change(change)
        title = f"NBIM/Oljefondet: {change.get('change_type') or 'Holding'}"
        detail = (
            f"{change.get('name') or ticker}; metric {change.get('change_metric') or '-'}; "
            f"endring {change.get('change_pct') if change.get('change_pct') is not None else 'ukjent'}%; "
            f"eierandel {change.get('ownership_pct') if change.get('ownership_pct') is not None else '-'}%."
        )
        existing = overlay.get(ticker)
        if existing:
            existing_type = _clean(existing.get("nbim_change_type"))
            current_type = _clean(change.get("change_type"))
            if existing_type != "Solgt ut" and current_type == "Solgt ut":
                continue
            if existing_type == "Solgt ut" and current_type != "Solgt ut":
                pass
            elif float(existing.get("nbim_conviction_score") or existing.get("nbim_signal_score") or 0.0) > float(change.get("nbim_conviction_score") or score):
                continue
            elif float(existing.get("nbim_ticker_match_score") or 0.0) > float(match.get("score") or 0.0):
                continue
        overlay[ticker] = {
            "nbim_signal_score": round(score, 1),
            "nbim_priority_score": change.get("nbim_priority_score"),
            "nbim_conviction_score": change.get("nbim_conviction_score"),
            "nbim_signals": list(change.get("nbim_signals") or []),
            "nbim_change_type": change.get("change_type"),
            "nbim_change_pct": change.get("change_pct"),
            "nbim_ownership_change_pct": change.get("ownership_pct_change_pct"),
            "nbim_market_value_change_pct": change.get("market_value_nok_change_pct"),
            "nbim_market_value_nok": change.get("market_value_nok"),
            "nbim_market_value_usd": change.get("market_value_usd"),
            "nbim_ownership_pct": change.get("ownership_pct"),
            "nbim_radar_overlap": bool(change.get("radar_overlap")),
            "nbim_ticker_match_quality": match.get("quality"),
            "nbim_ticker_match_alias": match.get("alias"),
            "nbim_ticker_match_score": match.get("score"),
            "nbim_evidence": [{
                "type": "Oljefond",
                "title": title,
                "source": "NBIM/Oljefondet",
                "published": str(change.get("detected_at") or ""),
                "url": NBIM_SOURCE_URL,
                "detail": detail + f" Ticker-match: {ticker} via {match.get('quality')} ({match.get('alias') or '-'}).",
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
    "annotate_nbim_changes",
    "apply_nbim_overlay",
    "build_nbim_overlay",
    "build_nbim_priority_views",
    "build_nbim_watchlist",
    "build_ticker_alias_index",
    "build_ticker_alias_lookup",
    "compare_nbim_holdings",
    "format_nbim_amount",
    "format_nbim_metric_value",
    "format_nbim_percent",
    "nbim_changes_to_display_rows",
    "load_nbim_overlay",
    "match_nbim_holding_to_ticker",
    "nbim_file_diagnostics",
    "nbim_group_summary",
    "nbim_changes_to_json",
    "nbim_metric_label",
    "normalize_nbim_holding",
    "parse_number",
    "read_nbim_csv_bytes",
    "save_nbim_overlay",
    "score_nbim_change",
    "score_nbim_conviction",
    "score_nbim_priority",
    "nbim_signal_tags",
]
