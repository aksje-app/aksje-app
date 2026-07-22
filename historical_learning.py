"""Historical Learning & Accuracy Analytics v18.7.3.

Stores immutable recommendation snapshots and evaluates forward returns at fixed
horizons. Analytics are descriptive only and never change production weights.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Callable, Mapping, Sequence

from storage_architecture import runtime_data_path
from persistent_config_store import read_persistent_json, write_persistent_json

VERSION = "v18.7.4"
ROOT = runtime_data_path("historical_learning")
SNAPSHOTS_PATH = ROOT / "recommendation_snapshots.json"
HORIZONS = (1, 5, 30, 90)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read() -> list[dict[str, Any]]:
    stored = read_persistent_json("historical_learning/recommendation_snapshots.json", default=None)
    if isinstance(stored, list):
        ROOT.mkdir(parents=True, exist_ok=True)
        SNAPSHOTS_PATH.write_text(json.dumps(stored, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return [dict(x) for x in stored if isinstance(x, Mapping)]
    try:
        data = json.loads(SNAPSHOTS_PATH.read_text(encoding="utf-8"))
        write_persistent_json("historical_learning/recommendation_snapshots.json", data)
        return [dict(x) for x in data if isinstance(x, Mapping)]
    except Exception:
        return []


def _write(rows: Sequence[Mapping[str, Any]]) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    payload = [dict(x) for x in rows]
    SNAPSHOTS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_persistent_json("historical_learning/recommendation_snapshots.json", payload)


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
        return number if number == number else default
    except (TypeError, ValueError):
        return default


def _entry_price(candidate: Mapping[str, Any]) -> float | None:
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    for key in ("current_price", "price", "last_price", "regularMarketPrice", "close"):
        value = _num(candidate.get(key))
        if value and value > 0:
            return value
        value = _num(raw.get(key))
        if value and value > 0:
            return value
    return None


def register_run(run: Mapping[str, Any]) -> int:
    """Create one immutable snapshot per recommended/proposed ticker."""
    if run.get("analysis_aborted"):
        return 0
    source = list(run.get("proposals") or []) or [
        x for x in (run.get("candidates") or []) if x.get("status") == "ANBEFALT FOR VURDERING"
    ]
    existing = _read()
    keys = {(str(x.get("run_id")), str(x.get("ticker"))) for x in existing}
    added = 0
    for candidate in source:
        ticker = str(candidate.get("ticker") or "").upper().strip()
        if not ticker or (str(run.get("run_id")), ticker) in keys:
            continue
        raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
        existing.append({
            "snapshot_id": f"{run.get('run_id')}:{ticker}",
            "run_id": run.get("run_id"), "created_at": run.get("created_at") or _now_iso(),
            "job_name": run.get("job_name"), "report_type": (run.get("report_identity") or {}).get("type"),
            "ticker": ticker, "market": candidate.get("market"), "sector": candidate.get("sector"),
            "rank": candidate.get("rank"), "entry_price": _entry_price(candidate),
            "investment_score": _num(candidate.get("investment_score"), 0.0),
            "ai_score": _num(candidate.get("ai_score") or candidate.get("discovery_score"), 50.0),
            "insider_score": _num(raw.get("insider_score"), 50.0),
            "news_score": _num(raw.get("news_score"), 50.0),
            "technical_score": _num(candidate.get("technical_score"), 50.0),
            "fundamental_score": _num(candidate.get("fundamental_score"), 50.0),
            "discovery_score": _num(candidate.get("discovery_score") or candidate.get("ai_score"), 50.0),
            "research_score": _num(candidate.get("research_score"), 50.0),
            "validation_score": _num(candidate.get("validation_score"), 50.0),
            "portfolio_fit_score": _num(candidate.get("portfolio_fit_score"), 50.0),
            "risk_adjustment_score": 100.0 - (_num(candidate.get("risk_score"), 50.0) or 50.0),
            "model_version": ((raw.get("adaptive_learning") or {}).get("model_version") if isinstance(raw.get("adaptive_learning"), Mapping) else "standard"),
            "effective_weights": raw.get("effective_weights") if isinstance(raw.get("effective_weights"), Mapping) else {},
            "confidence_score": _num(candidate.get("confidence_score"), 0.0),
            "evaluations": {}, "last_evaluated_at": None,
        })
        added += 1
    if added:
        existing.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
        _write(existing[:10000])
    return added


def _business_days_since(created_at: str, now: datetime | None = None) -> int:
    try:
        start = datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).date()
    except Exception:
        return 0
    end = (now or datetime.now(timezone.utc)).date()
    if end <= start:
        return 0
    count = 0
    cursor = start
    from datetime import timedelta
    while cursor < end:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            count += 1
    return count


def update_due_evaluations(price_loader: Callable[[str, int], Mapping[int, float | None]], *, limit: int = 200) -> dict[str, int]:
    """Evaluate due horizons with an injected loader for deterministic testing."""
    rows = _read(); updated = errors = checked = 0
    for row in rows:
        if checked >= limit:
            break
        entry = _num(row.get("entry_price"))
        if not entry or entry <= 0:
            continue
        age = _business_days_since(str(row.get("created_at") or ""))
        due = [h for h in HORIZONS if age >= h and str(h) not in (row.get("evaluations") or {})]
        if not due:
            continue
        checked += 1
        try:
            prices = price_loader(str(row.get("ticker")), max(due))
            evaluations = dict(row.get("evaluations") or {})
            for horizon in due:
                price = _num(prices.get(horizon))
                if price and price > 0:
                    evaluations[str(horizon)] = {
                        "horizon_days": horizon, "price": round(price, 6),
                        "return_pct": round((price / entry - 1.0) * 100.0, 4), "evaluated_at": _now_iso(),
                    }
                    updated += 1
            row["evaluations"] = evaluations
            row["last_evaluated_at"] = _now_iso()
        except Exception:
            errors += 1
    if updated:
        _write(rows)
    return {"checked": checked, "updated": updated, "errors": errors}


def yfinance_price_loader(ticker: str, max_horizon: int) -> Mapping[int, float | None]:
    import yfinance as yf
    period_days = max(14, int(max_horizon * 1.8) + 10)
    frame = yf.download(ticker, period=f"{period_days}d", interval="1d", progress=False, auto_adjust=False, threads=False)
    if frame is None or frame.empty:
        return {}
    close = frame["Close"]
    if hasattr(close, "columns"):
        close = close.iloc[:, 0]
    values = [float(x) for x in close.dropna().tolist()]
    return {h: values[h - 1] if len(values) >= h else None for h in HORIZONS}


def analytics(rows: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    rows = list(rows if rows is not None else _read())
    horizons: dict[str, Any] = {}
    all_returns: list[float] = []
    for h in HORIZONS:
        vals = []
        for row in rows:
            ev = (row.get("evaluations") or {}).get(str(h)) or {}
            value = _num(ev.get("return_pct"))
            if value is not None:
                vals.append(value); all_returns.append(value)
        horizons[str(h)] = {
            "count": len(vals), "hit_rate": round(sum(v > 0 for v in vals) / len(vals) * 100, 2) if vals else 0.0,
            "average_return": round(sum(vals) / len(vals), 3) if vals else 0.0,
            "median_return": round(median(vals), 3) if vals else 0.0,
        }
    by_market: dict[str, list[float]] = {}
    signal_buckets: dict[str, dict[str, list[float]]] = {k: {"high": [], "low": []} for k in ("insider_score", "news_score", "technical_score", "fundamental_score")}
    for row in rows:
        ev = (row.get("evaluations") or {}).get("30") or (row.get("evaluations") or {}).get("5") or {}
        ret = _num(ev.get("return_pct"))
        if ret is None:
            continue
        by_market.setdefault(str(row.get("market") or "Ukjent"), []).append(ret)
        for signal in signal_buckets:
            score = _num(row.get(signal), 50.0) or 50.0
            signal_buckets[signal]["high" if score >= 70 else "low"].append(ret)
    market_stats = [{"market": k, "count": len(v), "average_return": round(sum(v)/len(v), 3), "hit_rate": round(sum(x>0 for x in v)/len(v)*100, 2)} for k,v in by_market.items()]
    signal_stats = []
    for signal, buckets in signal_buckets.items():
        high, low = buckets["high"], buckets["low"]
        signal_stats.append({"signal": signal, "high_count": len(high), "high_average": round(sum(high)/len(high),3) if high else 0.0, "baseline_average": round(sum(low)/len(low),3) if low else 0.0})
    return {
        "snapshot_count": len(rows), "evaluated_snapshots": sum(bool(x.get("evaluations")) for x in rows),
        "horizons": horizons, "markets": sorted(market_stats, key=lambda x: x["average_return"], reverse=True),
        "signals": sorted(signal_stats, key=lambda x: x["high_average"] - x["baseline_average"], reverse=True),
        "best_return": round(max(all_returns), 3) if all_returns else None,
        "worst_return": round(min(all_returns), 3) if all_returns else None,
    }


def report_performance(run_id: str) -> dict[str, Any]:
    rows = [x for x in _read() if x.get("run_id") == run_id]
    returns = []
    for row in rows:
        ev = (row.get("evaluations") or {}).get("30") or (row.get("evaluations") or {}).get("5") or (row.get("evaluations") or {}).get("1") or {}
        value = _num(ev.get("return_pct"))
        if value is not None:
            returns.append((str(row.get("ticker")), value))
    return {"evaluated": len(returns), "average_return": round(sum(v for _,v in returns)/len(returns),3) if returns else None,
            "winners": sum(v>0 for _,v in returns), "losers": sum(v<=0 for _,v in returns),
            "best": max(returns, key=lambda x:x[1]) if returns else None, "worst": min(returns, key=lambda x:x[1]) if returns else None}


def run_horizon_performance(run_id: str, horizons: Sequence[int] = (5, 30, 90)) -> dict[str, Any]:
    """Return comparable per-horizon outcomes for production/Shadow cohorts."""
    rows = [x for x in _read() if str(x.get("run_id")) == str(run_id)]
    result: dict[str, Any] = {}
    for horizon in horizons:
        values = []
        for row in rows:
            value = _num(((row.get("evaluations") or {}).get(str(horizon)) or {}).get("return_pct"))
            if value is not None: values.append(value)
        result[str(horizon)] = {
            "status": "READY" if values else "PENDING", "count": len(values),
            "average_return_pct": round(sum(values) / len(values), 3) if values else None,
            "hit_rate_pct": round(sum(value > 0 for value in values) / len(values) * 100, 2) if values else None,
        }
    return result


def render_accuracy_analytics() -> None:
    import pandas as pd
    import streamlit as st
    st.markdown("### 🎯 Accuracy Analytics")
    st.caption("Historiske resultater er beskrivende statistikk. De endrer ikke modellvekter automatisk.")
    if st.button("Oppdater modne målepunkter", key="hl_refresh_v1873", use_container_width=True):
        with st.spinner("Henter historiske sluttkurser …"):
            result = update_due_evaluations(yfinance_price_loader)
        st.success(f"Oppdatert {result['updated']} målepunkter. Feil: {result['errors']}.")
    data = analytics()
    a,b,c,d = st.columns(4)
    a.metric("Snapshots", data["snapshot_count"]); b.metric("Evaluert", data["evaluated_snapshots"])
    c.metric("Beste utvikling", "-" if data["best_return"] is None else f"{data['best_return']:+.2f}%")
    d.metric("Svakeste utvikling", "-" if data["worst_return"] is None else f"{data['worst_return']:+.2f}%")
    horizon_rows = [{"Måleperiode": f"{h} handelsdager", "Antall": v["count"], "Treffprosent": v["hit_rate"], "Gjennomsnitt %": v["average_return"], "Median %": v["median_return"]} for h,v in data["horizons"].items()]
    st.dataframe(pd.DataFrame(horizon_rows), use_container_width=True, hide_index=True)
    st.markdown("#### Signalanalyse")
    labels = {"insider_score":"Insider", "news_score":"Nyheter", "technical_score":"Teknisk", "fundamental_score":"Fundamental"}
    signal_rows = [{"Signal": labels.get(x["signal"],x["signal"]), "Observasjoner ≥70": x["high_count"], "Gj.snitt høy score %": x["high_average"], "Baseline %": x["baseline_average"], "Meravkastning %": round(x["high_average"]-x["baseline_average"],3)} for x in data["signals"]]
    st.dataframe(pd.DataFrame(signal_rows), use_container_width=True, hide_index=True)
    if data["markets"]:
        st.markdown("#### Resultat per marked")
        st.dataframe(pd.DataFrame(data["markets"]), use_container_width=True, hide_index=True)
    st.divider()
    try:
        from adaptive_ranking import render_adaptive_ranking
        from investment_pipeline import PipelineConfig
        render_adaptive_ranking(PipelineConfig().normalized().weights, _read())
    except Exception as exc:
        st.warning(f"Adaptiv rangering kunne ikke lastes: {exc}")
