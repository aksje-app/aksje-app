"""Killable, single-ticker financial data worker."""
from __future__ import annotations

import json
import sys

from quality_valuation import _safe_ticker
from quality_valuation_data import live_financial_snapshot, live_proxy_snapshot


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--proxy":
        if sys.argv[2] not in {"BZ=F", "HG=F", "GC=F"}:
            raise SystemExit(2)
        try:
            print(json.dumps(live_proxy_snapshot(sys.argv[2]), ensure_ascii=False, allow_nan=False))
        except Exception:
            raise SystemExit(1)
        raise SystemExit(0)
    symbol = _safe_ticker(sys.argv[1] if len(sys.argv) == 2 else "")
    if not symbol:
        raise SystemExit(2)
    try:
        print(json.dumps(live_financial_snapshot(symbol), ensure_ascii=False, allow_nan=False))
    except Exception:
        # Never print a provider exception: upstream may include private URLs.
        raise SystemExit(1)
