"""Bounded, auditable historical S&P 500 breadth backfill (explicit job only).

Historical index membership is read by effective date; prices are adjusted Yahoo
daily closes. Missing/delisted securities count against coverage, never replaced.
The job emits a JSON proposal, not writes to production or trade signals.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from urllib.request import Request, urlopen

from market_health_historical_breadth import parse_membership_csv, historical_breadth

MEMBERSHIP_URL = (
    "https://raw.githubusercontent.com/chinobing/"
    "historical_sp500_constituents/main/sp_500_historical_components.csv"
)


def monthly_snapshots(rows, *, start, end):
    """Last known membership on each month's last available archived date."""
    latest = {}
    for day, tickers in rows:
        if start <= day <= end:
            latest[(day.year, day.month)] = (day, tickers)
    return [latest[key] for key in sorted(latest)]


def download_adjusted_prices(tickers, *, years=3, batch_size=40):
    import yfinance as yf
    prices = {}
    for offset in range(0, len(tickers), batch_size):
        batch = tickers[offset:offset + batch_size]
        frame = yf.download(
            batch, period=f"{years}y", interval="1d",
            auto_adjust=True, progress=False, threads=4, group_by="column",
        )
        if frame is None or frame.empty:
            continue
        close = frame["Close"] if "Close" in frame else None
        if close is None:
            continue
        for ticker in batch:
            try:
                series = close[ticker].dropna() if hasattr(close, "columns") else close.dropna()
            except (KeyError, TypeError, AttributeError):
                continue
            if series is None or len(series) < 200:
                continue
            values = {}
            for at, value in series.items():
                try:
                    number = float(value)
                    if number > 0:
                        values[at.date()] = number
                except (ValueError, TypeError, AttributeError):
                    pass
            if values:
                prices[ticker] = values
    return prices


def prepare_backfill(*, membership_csv, prices, start, end):
    rows = parse_membership_csv(membership_csv)
    snapshots = monthly_snapshots(rows, start=start, end=end)
    observations = historical_breadth(snapshots, prices)
    return {
        "mode": "READ_ONLY",
        "historical_membership_source": MEMBERSHIP_URL,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "candidate_months": len(snapshots),
        "accepted_months": len(observations),
        "rejected_months": len(snapshots) - len(observations),
        "minimum_coverage": 0.8,
        "observations": observations,
        "validated_composite": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate a reviewed breadth-backfill JSON proposal.")
    parser.add_argument("--months", type=int, default=18)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not 1 <= args.months <= 24:
        parser.error("--months must be between 1 and 24")
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=31 * args.months)
    request = Request(MEMBERSHIP_URL, headers={"User-Agent": "MarketHealthHistory/1.0"})
    with urlopen(request, timeout=30) as response:
        members_csv = response.read(12_000_000).decode("utf-8-sig")
    snapshots = monthly_snapshots(parse_membership_csv(members_csv), start=start, end=today)
    tickers = sorted(set().union(*(members for _, members in snapshots))) if snapshots else []
    prices = download_adjusted_prices(tickers, years=3) if tickers else {}
    proposal = prepare_backfill(membership_csv=members_csv, prices=prices, start=start, end=today)
    with open(args.output, "w", encoding="utf-8") as output:
        json.dump(proposal, output, ensure_ascii=False, indent=2)
    print(json.dumps({key: value for key, value in proposal.items() if key != "observations"}))
    if not proposal["accepted_months"]:
        raise SystemExit("No month passed the point-in-time 80% coverage gate; no data approved")


if __name__ == "__main__":
    main()
