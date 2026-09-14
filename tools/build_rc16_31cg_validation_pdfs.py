#!/usr/bin/env python3
"""Build deterministic RC16.31cg PDFs for visual release validation."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from market_intelligence import build_pdf
from tests.test_v1921_decision_report import _run


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf"


def _series(offset: float, slope: float) -> list[dict]:
    start = date(2026, 6, 15)
    points = []
    for index in range(60):
        price = offset + slope * index + ((index % 7) - 3) * 0.18
        points.append({
            "date": (start + timedelta(days=index)).isoformat(),
            "close": round(price, 2),
            "volume": 900_000 + (index % 9) * 85_000,
        })
    return points


def _receipt(ticker: str, rank: int, *, early: bool = False) -> dict:
    points = _series(95 + rank * 6, 0.22 + rank * 0.015)
    last = points[-1]["close"]
    return {
        "ticker": ticker,
        "name": ticker.split(".")[0],
        "exchange_name": "Oslo Børs",
        "country": "Norge",
        "market": "Norge",
        "last_price": last,
        "return_1d_pct": 0.4 + rank * 0.08,
        "return_3d_pct": 1.5 + rank * 0.17,
        "return_5d_pct": 2.4 + rank * 0.21,
        "volume_ratio_20": 1.05 + rank * 0.06,
        "volume_bar_complete": True,
        "volume_time_adjusted": False,
        "volume_comparison_basis": "fullført dagsvolum mot 20 fullførte dager",
        "market_rs_5d_percentile": 72 + rank,
        "sector_rs_5d_percentile": 64 + rank,
        "market_rs_20d_percentile": 70 + rank,
        "sector_rs_20d_percentile": 62 + rank,
        "market_rs_universe_count_5d": 286,
        "sector_rs_universe_count_5d": 31,
        "prior_20d_high": round(last * 0.97, 2),
        "prior_60d_high": round(last * 1.03, 2),
        "low_20d": round(last * 0.91, 2),
        "price_trend_60d": points,
        "pullback_retest": {"label": "RETEST HOLDER" if rank % 2 else "PULLBACK/RETEST"},
        "fresh_monitor_components": {
            "Freshness": 100,
            "Confirmation": 70 + rank,
            "Velocity": 76 + rank,
            "Risk": 25,
        },
        "fresh_signal": {
            "score": 88 + rank,
            "label": "STERKT TIDLIG STYRKESIGNAL" if early else "NYTT BREAKOUTSIGNAL",
            "trend_age_sessions": rank % 5,
        },
    }


def main() -> None:
    run = _run("2026-09-11T08:05:54+00:00")
    fresh = [_receipt(ticker, i) for i, ticker in enumerate(
        ["DNO.OL", "WWI.OL", "ROGS.OL", "EQNR.OL", "AKRBP.OL", "VAR.OL", "NSKOG.OL", "OTE.OL"], 1
    )]
    early = [_receipt(ticker, i, early=True) for i, ticker in enumerate(
        ["NHY.OL", "FRO.OL", "GJF.OL"], 1
    )]
    run["trend_discovery"] = {
        "coverage": {"full_stage1_universe": 294},
        "fresh_trend_watchlist": fresh,
        "early_signal_watchlist": early,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "RC16.31cg_VALIDATION_MAIN.pdf").write_bytes(build_pdf(run, include_technical=False))
    (OUT / "RC16.31cg_VALIDATION_TECHNICAL.pdf").write_bytes(build_pdf(run, include_technical=True))


if __name__ == "__main__":
    main()
