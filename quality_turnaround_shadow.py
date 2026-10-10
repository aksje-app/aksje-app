"""Bounded forward experiment; immutable cohorts, equal capital, same prices.

The benchmark is the existing quality-qualified subset of the SAME analyzed
universe. This is not a Super Portfolio backtest or evidence of optimal rules.
Each currency has a separate 100-unit model account; no invented FX conversion.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from copy import deepcopy
from quality_turnaround import date, number, MODEL

KEY = "quality_turnaround/forward_shadow.json"
MAX_COHORTS = 120
HORIZON_DAYS = 30
COST_PCT = 0.10  # per side; explicitly assumed, not actual brokerage


def advance(state, snapshot):
    state = deepcopy(state or {})
    now = date(snapshot.get("generated_at"))
    previous = date(state.get("last_observed_at"))
    if not now or (previous and now <= previous) or snapshot.get("state") != "COMPLETED":
        return state
    rows = {r["ticker"]: r for group in (snapshot.get("groups") or {}).values()
            for r in group if r.get("ticker") and number(r.get("price")) is not None and number(r["price"]) > 0
            and date(r.get("observed_at")) and date(r["observed_at"]) <= now}
    pricing_rows = dict(rows)
    for ticker, row in (snapshot.get("turnaround_shadow_prices") or {}).items():
        observed = date(row.get("observed_at"))
        trade = date(row.get("latest_trade_date"))
        if observed and observed <= now and trade and 0 <= (now - trade).days <= 7 and number(row.get("price")) and row["price"] > 0:
            pricing_rows.setdefault(ticker, row)
    cohorts = state.setdefault("cohorts", [])
    for cohort in cohorts:
        if cohort.get("closed_at"):
            continue
        for arm in ("watch", "baseline"):
            basket = cohort[arm]
            if not basket["positions"]:
                basket["net_value"] = 100.0  # a cash baseline has no trading cost
                continue
            missing = []
            for ticker, pos in basket["positions"].items():
                row = pricing_rows.get(ticker)
                if not row or row.get("currency") != cohort["currency"]:
                    missing.append(ticker)
                    continue
                pos["last_price"] = row["price"]
                pos["priced_at"] = now.isoformat()
                if arm == "watch" and row.get("quality_evidence_ready") and not pos.get("quality_confirmed_at"):
                    pos["quality_confirmed_at"] = now.isoformat()
                    pos["lead_days"] = (now - date(cohort["opened_at"])).days
            basket["missing_prices"] = missing
            if missing:
                continue  # no stale-price success, no replacement with hindsight
            gross = sum(pos["units"] * pos["last_price"] for pos in basket["positions"].values())
            net = gross * (1 - COST_PCT / 100)
            basket["net_value"] = net
            basket["peak_value"] = max(basket.get("peak_value", 100), net)
            basket["max_drawdown_pct"] = max(basket.get("max_drawdown_pct", 0), (1 - net / basket["peak_value"]) * 100)
            basket["return_pct"] = net - 100
        if now - date(cohort["opened_at"]) >= timedelta(days=HORIZON_DAYS):
            if all(not cohort[arm].get("missing_prices") for arm in ("watch", "baseline")):
                cohort["closed_at"] = now.isoformat()
                cohort["holding_calendar_days"] = (now - date(cohort["opened_at"])).days
                cohort["exit_delay_days"] = cohort["holding_calendar_days"] - HORIZON_DAYS
                cohort["excess_return_pp"] = cohort["watch"]["net_value"] - cohort["baseline"]["net_value"]
                cohort["false_positive_count"] = sum(pos["last_price"] * (1 - COST_PCT / 100) < pos["entry_price"] / (1 - COST_PCT / 100)
                                                       for pos in cohort["watch"]["positions"].values())
            else:
                cohort["status"] = "WAITING_FOR_COMPLETE_EXIT_PRICES"
    # At most one active experiment per exact currency and universe. Daily
    # repeated cron calls do not open overlapping duplicate cohorts.
    for currency in sorted({str(r.get("currency") or "") for r in rows.values()} - {""}):
        universe = sorted(t for t, r in rows.items() if r.get("currency") == currency)
        if any(not c.get("closed_at") and c["currency"] == currency and c["universe"] == universe for c in cohorts):
            continue
        watch = [rows[t] for t in universe if (rows[t].get("turnaround") or {}).get("financial_improvement")
                 and date(rows[t]["turnaround"].get("observed_at"))
                 and date(rows[t]["turnaround"]["observed_at"]) <= now]
        if not watch:
            continue
        if len(cohorts) >= MAX_COHORTS:
            state["capacity_status"] = "FULL_EXPORT_AND_REVIEW_REQUIRED"
            break
        baseline = [rows[t] for t in universe if rows[t].get("quality_evidence_ready")]
        def basket(selected):
            return {"positions": {r["ticker"]: {"entry_price": r["price"], "last_price": r["price"],
                     "units": 100 * (1 - COST_PCT / 100) / len(selected) / r["price"],
                     "priced_at": now.isoformat(), "entry_evidence": {
                         "quality_qualified": bool(r.get("quality_evidence_ready")),
                         "turnaround": {key: (r.get("turnaround") or {}).get(key) for key in (
                             "status", "model", "observed_at", "period_end", "comparison_period_end",
                             "primary_filing_status", "operating_margin_delta_pp", "metrics")}}} for r in selected},
                    "net_value": 100.0 if not selected else 100 * (1 - COST_PCT / 100) ** 2,
                    "peak_value": 100.0, "max_drawdown_pct": 0.0 if not selected else 100 * (1 - (1 - COST_PCT / 100) ** 2), "missing_prices": []}
        cohorts.append({"opened_at": now.isoformat(), "currency": currency, "universe": universe,
                        "watch": basket(watch), "baseline": basket(baseline), "model": MODEL,
                        "run_key": snapshot.get("run_key"), "status": "OBSERVING"})
    state.update(schema="turnaround_forward_shadow@1.0", last_observed_at=now.isoformat(),
                 horizon_calendar_days=HORIZON_DAYS, cost_pct_per_side=COST_PCT,
                 capital_units_per_arm=100, shadow_only=True, production_effect=False,
                 limitations=["Forward observations only; no historical filings reconstructed",
                              "Overlapping cohorts are not independent statistical samples",
                              "Sampled prices only; intraday drawdown and FX not measured",
                              "Quality-screen baseline; not the actual Super Portfolio strategy"])
    return state


def record(snapshot):
    from services.storage_service import get_storage_service
    storage = get_storage_service()
    return storage.mutate_json(KEY, lambda old: advance(old, snapshot), default={})


def tracked_prices(prescreen):
    """Reuse this cycle's quotes for names that dropped out of the finalists."""
    from services.storage_service import get_storage_service
    state = get_storage_service().read_json(KEY, {}) or {}
    tickers = {ticker for c in state.get("cohorts", [])[:MAX_COHORTS] if not c.get("closed_at")
               for arm in ("watch", "baseline") for ticker in c[arm]["positions"]}
    observed = datetime.now(timezone.utc).isoformat()
    return {r["ticker"]: {"price": number(r.get("last_price")), "currency": r.get("currency"),
                           "observed_at": observed, "latest_trade_date": r.get("latest_trade_date")}
            for r in prescreen.get("rows", []) if r.get("ticker") in tickers}


def summary(state):
    closed = [c for c in (state or {}).get("cohorts", []) if c.get("closed_at")]
    currencies = {}
    for currency in sorted({c["currency"] for c in closed}):
        subset = [c for c in closed if c["currency"] == currency]
        currencies[currency] = {"completed": len(subset),
                                "mean_excess_return_pp": sum(c["excess_return_pp"] for c in subset) / len(subset),
                                "false_positive_count": sum(c["false_positive_count"] for c in subset),
                                "worst_sampled_drawdown_pct": max(c["watch"].get("max_drawdown_pct", 0) for c in subset)}
    return {"status": "OBSERVING" if not closed else "FORWARD_RESULTS_AVAILABLE",
            "completed_cohorts": len(closed), "total_cohorts": len((state or {}).get("cohorts", [])),
            "by_currency": currencies, "latest_cohorts": (state or {}).get("cohorts", [])[-6:],
            "limitations": (state or {}).get("limitations", []),
            "capacity_status": (state or {}).get("capacity_status", "OK"),
            "production_effect": False, "shadow_only": True}
