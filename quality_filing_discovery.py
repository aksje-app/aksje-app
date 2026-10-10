"""One bounded official Oslo announcement lookup, never one lookup per finalist.

Announcements document discovery/availability, not extraction of verified
financial values. Yahoo quarterly numbers retain their unverified source label.
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
import re
from quality_turnaround import date

KEY = "quality_turnaround/official_announcements.json"


def classify(messages, now):
    events = []
    for message in messages[:1000]:
        if not isinstance(message, dict) or message.get("correctedByMessageId"):
            continue
        published = date(message.get("publishedTime"))
        identity = str(message.get("id") or "")
        if not identity.isdigit() or not published or not 0 <= (now - published).days <= 120:
            continue
        title = str(message.get("title") or "")[:400]
        text = title.casefold()
        financial = bool(re.search(r"\b(q[1-4]|quarter|quarterly|halvår|half.year|kvartal|annual report|årsrapport)\b", text))
        contract = bool(re.search(r"\b(contract|kontrakt|order award|ordre)\b", text))
        if not (financial or contract):
            continue
        events.append({"id": identity, "kind": "FINANCIAL_REPORT" if financial else "CONTRACT_ANNOUNCEMENT",
                       "issuer_symbol": str(message.get("issuerSign") or "").upper(),
                       "title": title, "occurred_at": published.isoformat(), "observed_at": now.isoformat(),
                       "source_url": f"https://newsweb.oslobors.no/message/{identity}",
                       "numeric_extraction": "NOT_PERFORMED"})
    return sorted(events, key=lambda row: row["occurred_at"], reverse=True)[:240]


def refresh(*, storage=None, now=None, request_json=None):
    from services.storage_service import get_storage_service
    from market_event_discovery import NEWS_API, _request_json
    storage = storage or get_storage_service()
    now = now or datetime.now(timezone.utc)
    old = storage.read_json(KEY, {}) or {}
    checked = date(old.get("checked_at"))
    if checked and 0 <= (now - checked).total_seconds() < 3600:
        return old
    try:
        query = urlencode({"fromDate": (now - timedelta(days=120)).date().isoformat(), "toDate": now.date().isoformat()})
        payload = (request_json or _request_json)(NEWS_API + "list?" + query, post=True)
        messages = payload["messages"]
        if not isinstance(messages, list):
            raise ValueError("Invalid official list")
        state = {"checked_at": now.isoformat(), "status": "AVAILABLE", "coverage": "OSLO_OFFICIAL_ONLY",
                 "coverage_complete": False, "coverage_reason": "BOUNDED_METADATA_RESPONSE_NOT_EXHAUSTIVE",
                 "list_limit_reached": len(messages) >= 1000, "events": classify(messages, now)}
    except Exception as exc:
        state = {**old, "checked_at": now.isoformat(), "status": "UNAVAILABLE", "error": type(exc).__name__}
    storage.write_json(KEY, state)
    return state


def cached_context(ticker, identity=None):
    """Read-only: UI and provider loops must never start heavy discovery."""
    from services.storage_service import get_storage_service
    from market_event_discovery import KEY as EVENT_KEY, candidate_events
    storage = get_storage_service()
    now = datetime.now(timezone.utc)
    official = storage.read_json(KEY, {}) or {}
    state = storage.read_json(EVENT_KEY, {}) or {}
    events = candidate_events([{**(identity or {}), "ticker": ticker}], state, now).get(ticker, [])
    announcements = [e for e in official.get("events", []) if ticker.endswith(".OL")
                     and e.get("issuer_symbol") == ticker.removesuffix(".OL")
                     and date(e.get("observed_at")) and date(e["observed_at"]) <= now][:10]
    return {"official_market_events": events + announcements,
            "official_announcement_coverage": {"status": official.get("status", "NOT_AVAILABLE"),
                                                "checked_at": official.get("checked_at"),
                                                "scope": "OSLO_OFFICIAL_ONLY",
                                                "numeric_extraction": "NOT_PERFORMED"},
            "official_event_coverage": state.get("sources") or {"status": "NOT_AVAILABLE"}}


def discovery_tickers(universe=(), now=None):
    from services.storage_service import get_storage_service
    from market_event_discovery import KEY as EVENT_KEY, candidate_events
    now = now or datetime.now(timezone.utc)
    storage = get_storage_service()
    rows = list((storage.read_json(KEY, {}) or {}).get("events", []))
    event_state = storage.read_json(EVENT_KEY, {}) or {}
    rows += list(event_state.get("events", []))
    tickers = {str(e["issuer_symbol"]).removesuffix(".OL") + ".OL" for e in rows
            if e.get("issuer_symbol") and date(e.get("observed_at")) and date(e["observed_at"]) <= now
            and date(e.get("occurred_at")) and 0 <= (now - date(e["occurred_at"])).days <= 14}
    # Short-register records may have ISIN/name but no symbol. Resolve only
    # unique official identity matches across the entire analyzed universe.
    tickers.update(candidate_events(universe, event_state, now))
    return tickers
