"""Canonical issuer identity shared by ranking and portfolio risk gates."""
from __future__ import annotations

import re
from typing import Any, Mapping


ALIASES = {
    "GOOG": "ALPHABET", "GOOGL": "ALPHABET",
    "BRK-A": "BERKSHIRE_HATHAWAY", "BRK-B": "BERKSHIRE_HATHAWAY",
    "BRK.A": "BERKSHIRE_HATHAWAY", "BRK.B": "BERKSHIRE_HATHAWAY",
    "FOX": "FOX_CORP", "FOXA": "FOX_CORP",
    "NWS": "NEWS_CORP", "NWSA": "NEWS_CORP",
    "HEI": "HEICO", "HEI-A": "HEICO",
    "INVE-A.ST": "INVESTOR_AB", "INVE-B.ST": "INVESTOR_AB",
}


def issuer_identity(candidate: Mapping[str, Any] | str) -> str:
    row = {"ticker": candidate} if isinstance(candidate, str) else candidate
    ticker = str(row.get("ticker") or row.get("symbol") or "").upper().strip()
    if ticker in ALIASES:
        return ALIASES[ticker]
    nordic_class = re.fullmatch(r"(.+)-[ABC]\.(ST|OL|CO|HE)", ticker)
    if nordic_class:
        return f"{nordic_class.group(1)}.{nordic_class.group(2)}"
    raw = row.get("raw") if isinstance(row.get("raw"), Mapping) else {}
    name = str(row.get("longName") or row.get("shortName") or row.get("name") or raw.get("longName") or raw.get("shortName") or "").upper()
    if name and name != ticker:
        for suffix in (" CLASS A", " CLASS B", " CLASS C", " A-SHARE", " B-SHARE", " ADR", " PLC", " INC.", " INC", " CORP.", " CORP", " LTD.", " LTD"):
            name = name.replace(suffix, "")
        compact = "".join(ch for ch in name if ch.isalnum())
        if compact:
            return compact
    return ticker
