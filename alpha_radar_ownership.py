from __future__ import annotations

from typing import Any, Mapping, Sequence


INSIDER_ROLE_HINTS = (
    "ceo",
    "cfo",
    "coo",
    "cto",
    "chair",
    "director",
    "board",
    "officer",
    "primary insider",
    "primarinnsider",
    "styre",
    "leder",
    "management",
)

BJELLESAU_HINTS = (
    "bjellesau",
    "smart money",
    "fond",
    "fund",
    "asset management",
    "capital",
    "investor",
    "owner",
    "aksjonaer",
    "flagging",
    "watchlist",
)


def _clean(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _unit(value: Any) -> float | None:
    number = _float(value, None)
    if number is None:
        return None
    if number > 10:
        number = number / 100.0
    elif number > 1:
        number = number / 10.0
    return max(0.0, min(1.0, number))


def classify_ownership_item(item: Mapping[str, Any], watchlist_names: Sequence[str] | None = None) -> str:
    explicit = str(
        item.get("ownership_type")
        or item.get("signal_type")
        or item.get("actor_type")
        or item.get("type_group")
        or ""
    ).strip().lower()
    if explicit in {"insider", "innsider", "primarinnsider", "primary insider"}:
        return "Insider"
    if explicit in {"bjellesau", "smart_money", "smart money", "owner", "major_owner"}:
        return "Bjellesau"

    role = _clean(item.get("relation") or item.get("role") or item.get("officerTitle")).lower()
    source = _clean(item.get("source")).lower()
    name = _clean(item.get("name") or item.get("person") or item.get("insider") or item.get("owner")).lower()
    combined = f"{name} {role} {source}"

    watch = [str(x or "").strip().lower() for x in watchlist_names or [] if str(x or "").strip()]
    if watch and any(name_part and name_part in combined for name_part in watch):
        return "Bjellesau"
    if any(hint in combined for hint in INSIDER_ROLE_HINTS):
        return "Insider"
    if any(hint in combined for hint in BJELLESAU_HINTS):
        return "Bjellesau"
    return "Insider"


def normalize_ownership_item(
    item: Mapping[str, Any],
    *,
    watchlist_names: Sequence[str] | None = None,
    fallback_type: str = "Insider",
) -> dict[str, Any]:
    kind = classify_ownership_item(item, watchlist_names=watchlist_names)
    if kind not in {"Insider", "Bjellesau"}:
        kind = fallback_type if fallback_type in {"Insider", "Bjellesau"} else "Insider"
    action = _clean(item.get("type") or item.get("transaction_type") or item.get("side") or item.get("action"), "transaksjon")
    shares = _clean(item.get("shares") or item.get("volume") or item.get("quantity"))
    value = _clean(item.get("value") or item.get("amount") or item.get("value_nok"))
    role = _clean(item.get("relation") or item.get("role") or item.get("officerTitle"))
    detail_parts = [
        part
        for part in (
            f"Rolle: {role}" if role else "",
            f"Handling: {action}" if action else "",
            f"Aksjer: {shares}" if shares else "",
            f"Verdi: {value}" if value else "",
        )
        if part
    ]
    return {
        "type": kind,
        "title": _clean(item.get("name") or item.get("person") or item.get("insider") or item.get("owner"), "Ukjent aktor"),
        "source": _clean(item.get("source"), "Insiderdata" if kind == "Insider" else "Bjellesau-data"),
        "published": _clean(item.get("date") or item.get("published") or item.get("transaction_date")),
        "url": _clean(item.get("url") or item.get("link") or item.get("source_url")),
        "detail": " | ".join(detail_parts) or ("Primarinnsider/ledelse/styre." if kind == "Insider" else "Kjent investor/eier/watchlist-aktor."),
        "actor": kind,
        "role": role,
        "action": action,
        "value": value,
    }


def split_ownership_evidence(row: Mapping[str, Any], *, limit: int = 6) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    txs = row.get("latest_transactions") if isinstance(row.get("latest_transactions"), list) else []
    watchlist = [str(x) for x in row.get("bjellesau_match") or [] if str(x or "").strip()] if isinstance(row.get("bjellesau_match"), list) else []
    insider: list[dict[str, Any]] = []
    bjellesau: list[dict[str, Any]] = []
    for tx in txs[:limit]:
        if not isinstance(tx, Mapping):
            continue
        item = normalize_ownership_item(tx, watchlist_names=watchlist)
        if item["type"] == "Bjellesau":
            bjellesau.append(item)
        else:
            insider.append(item)

    explicit_bjellesau = row.get("bjellesau_evidence") if isinstance(row.get("bjellesau_evidence"), list) else []
    for raw in explicit_bjellesau[:limit]:
        if isinstance(raw, Mapping):
            forced = dict(raw)
            forced.setdefault("ownership_type", "Bjellesau")
            bjellesau.append(normalize_ownership_item(forced, fallback_type="Bjellesau"))

    for name in watchlist:
        if not any(str(item.get("title") or "").lower() == str(name).lower() for item in bjellesau):
            bjellesau.append({
                "type": "Bjellesau",
                "title": name,
                "source": "Lokal bjellesau-watchlist",
                "published": "",
                "url": "",
                "detail": "Navn fra siste eier-/insiderdata matcher lokal bjellesau-watchlist.",
                "actor": "Bjellesau",
                "role": "watchlist",
                "action": "match",
                "value": "",
            })

    def dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str, str, str]] = set()
        clean: list[dict[str, Any]] = []
        for item in items:
            marker = (
                str(item.get("type") or "").lower(),
                str(item.get("title") or "").lower(),
                str(item.get("source") or "").lower(),
                str(item.get("published") or "").lower(),
            )
            if marker in seen:
                continue
            seen.add(marker)
            clean.append(item)
        return clean

    insider = dedupe(insider)
    bjellesau = dedupe(bjellesau)
    combined: list[dict[str, Any]] = []
    for idx in range(max(len(insider), len(bjellesau))):
        if idx < len(insider):
            combined.append(insider[idx])
        if idx < len(bjellesau):
            combined.append(bjellesau[idx])
    combined = combined[: max(1, int(limit or 6))]
    return combined, insider[:limit], bjellesau[:limit]


def ownership_signal_scores(row: Mapping[str, Any]) -> dict[str, Any]:
    _combined, insider_items, bjellesau_items = split_ownership_evidence(row, limit=8)
    insider_values = [
        row.get("insider_signal_score"),
        row.get("insider_quality_score"),
        row.get("historical_insider_quality_score"),
        row.get("insider_score"),
    ]
    bjellesau_values = [
        row.get("bjellesau_signal_score"),
        row.get("bjellesau_score"),
        row.get("smart_money_score"),
        row.get("owner_signal"),
    ]
    insider_scores = [_unit(value) for value in insider_values if value is not None]
    bjellesau_scores = [_unit(value) for value in bjellesau_values if value is not None]
    insider_score = max([x for x in insider_scores if x is not None], default=None)
    bjellesau_score = max([x for x in bjellesau_scores if x is not None], default=None)

    if insider_score is None and insider_items:
        insider_score = 0.58 + min(len(insider_items), 4) * 0.055
    if bjellesau_score is None and bjellesau_items:
        bjellesau_score = 0.56 + min(len(bjellesau_items), 4) * 0.06

    scores = [x for x in (insider_score, bjellesau_score) if x is not None]
    combined = max(scores) if scores else None
    if insider_score is not None and bjellesau_score is not None:
        quality = "kombinert"
    elif insider_score is not None:
        quality = "insider"
    elif bjellesau_score is not None:
        quality = "bjellesau"
    else:
        quality = "mangler"
    return {
        "combined_score": None if combined is None else max(0.0, min(1.0, float(combined))),
        "insider_score": None if insider_score is None else max(0.0, min(1.0, float(insider_score))),
        "bjellesau_score": None if bjellesau_score is None else max(0.0, min(1.0, float(bjellesau_score))),
        "quality": quality,
        "insider_count": len(insider_items),
        "bjellesau_count": len(bjellesau_items),
    }


def ownership_summary(row: Mapping[str, Any]) -> str:
    scores = ownership_signal_scores(row)
    parts: list[str] = []
    if scores["insider_count"]:
        parts.append(f"{scores['insider_count']} insider")
    if scores["bjellesau_count"]:
        parts.append(f"{scores['bjellesau_count']} bjellesau")
    return ", ".join(parts) if parts else "ingen konkrete insider-/bjellesauspor"
