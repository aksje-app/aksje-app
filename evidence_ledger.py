from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence


EVIDENCE_COLLECTION_KEYS = (
    "evidence_items",
    "insider_evidence",
    "bjellesau_evidence",
    "news_evidence",
    "financial_insider_evidence",
    "nordic_actor_evidence",
    "nordic_insider_evidence",
    "nbim_evidence",
    "finansavisen_bjellesau_evidence",
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _hash_marker(parts: Sequence[Any]) -> str:
    text = "|".join(_clean(part).lower() for part in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def normalize_evidence_item(
    item: Mapping[str, Any] | None,
    *,
    ticker: str | None = None,
    found_by: str = "",
    default_type: str = "Kilde",
) -> dict[str, Any]:
    raw = dict(item or {})
    evidence_type = _clean(raw.get("type") or raw.get("kind") or default_type)
    title = _clean(raw.get("title") or raw.get("headline") or raw.get("name") or evidence_type)
    source = _clean(raw.get("source") or raw.get("publisher") or raw.get("site") or "Ukjent kilde")
    url = _clean(raw.get("url") or raw.get("link") or raw.get("source_url"))
    date = _clean(raw.get("published") or raw.get("date") or raw.get("published_at") or raw.get("transaction_date"))
    detail = _clean(raw.get("detail") or raw.get("description") or raw.get("summary") or raw.get("excerpt"))
    actor = _clean(raw.get("actor") or raw.get("actor_type") or raw.get("person") or raw.get("matched_actor"))
    strength = _clean(raw.get("strength") or raw.get("confidence") or raw.get("quality"))
    actor_roles = raw.get("actor_roles") or raw.get("matched_roles") or raw.get("roles")
    if isinstance(actor_roles, Sequence) and not isinstance(actor_roles, (str, bytes, bytearray)):
        actor_roles_text = "; ".join(str(item) for item in actor_roles if str(item or "").strip())
    else:
        actor_roles_text = _clean(actor_roles or raw.get("actor_type"))
    normalized = {
        "ticker": _clean(raw.get("ticker") or ticker).upper(),
        "type": evidence_type,
        "date": date,
        "source": source,
        "url": url,
        "actor": actor,
        "actor_roles": actor_roles_text,
        "strength": strength,
        "trust_level": _clean(raw.get("trust_level") or raw.get("tillit")),
        "title": title,
        "excerpt": detail[:500],
        "found_by": _clean(raw.get("found_by") or found_by),
    }
    normalized["marker"] = _hash_marker((normalized["ticker"], evidence_type, title, source, url, date, actor))
    return normalized


def merge_evidence_ledger(
    existing: Sequence[Mapping[str, Any]] | None,
    additions: Sequence[Mapping[str, Any]] | None,
    *,
    ticker: str | None = None,
    found_by: str = "",
    limit: int = 40,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in list(existing or []) + list(additions or []):
        if not isinstance(raw, Mapping):
            continue
        item = normalize_evidence_item(raw, ticker=ticker, found_by=found_by)
        marker = item.get("marker") or _hash_marker(item.values())
        if marker in seen:
            continue
        seen.add(marker)
        rows.append(item)
        if len(rows) >= limit:
            break
    return rows


def build_evidence_ledger(row: Mapping[str, Any], *, found_by: str = "Radar") -> list[dict[str, Any]]:
    ticker = _clean(row.get("ticker")).upper()
    additions: list[dict[str, Any]] = []
    for key in EVIDENCE_COLLECTION_KEYS:
        value = row.get(key)
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            continue
        for item in value:
            if isinstance(item, Mapping):
                additions.append(dict(item))
    articles = row.get("articles")
    if isinstance(articles, Sequence) and not isinstance(articles, (str, bytes, bytearray)):
        for article in articles:
            if not isinstance(article, Mapping):
                continue
            additions.append({
                "type": "Nyhet",
                "title": article.get("title") or article.get("headline"),
                "source": article.get("source") or article.get("publisher") or article.get("site"),
                "published": article.get("published") or article.get("publishedAt") or article.get("date"),
                "url": article.get("url") or article.get("link"),
                "detail": article.get("description") or article.get("summary") or article.get("content"),
                "found_by": "News/financial source",
            })
    return merge_evidence_ledger(row.get("evidence_ledger") if isinstance(row.get("evidence_ledger"), list) else [], additions, ticker=ticker, found_by=found_by)


def evidence_ledger_summary(row: Mapping[str, Any]) -> str:
    ledger = row.get("evidence_ledger") if isinstance(row.get("evidence_ledger"), list) else build_evidence_ledger(row)
    if not ledger:
        return "Ingen evidence ledger lagret."
    counts: dict[str, int] = {}
    for item in ledger:
        kind = _clean(item.get("type")) or "Kilde"
        counts[kind] = counts.get(kind, 0) + 1
    return ", ".join(f"{key}: {value}" for key, value in sorted(counts.items())) + f" | totalt {len(ledger)}"


def evidence_ledger_to_text(row: Mapping[str, Any], *, limit: int = 10) -> str:
    ledger = row.get("evidence_ledger") if isinstance(row.get("evidence_ledger"), list) else build_evidence_ledger(row)
    lines: list[str] = []
    for item in ledger[:limit]:
        parts = [
            _clean(item.get("type")),
            _clean(item.get("title")),
            _clean(item.get("source")),
            _clean(item.get("date")),
            _clean(item.get("actor")),
            _clean(item.get("actor_roles")),
            _clean(item.get("strength")),
            _clean(item.get("trust_level")),
            _clean(item.get("url")),
        ]
        line = " | ".join(part for part in parts if part)
        if line:
            lines.append(line)
    return "\n".join(lines) if lines else "Ingen evidence ledger lagret."


__all__ = [
    "EVIDENCE_COLLECTION_KEYS",
    "build_evidence_ledger",
    "evidence_ledger_summary",
    "evidence_ledger_to_text",
    "merge_evidence_ledger",
    "normalize_evidence_item",
]
