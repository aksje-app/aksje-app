"""Super Portfolio intelligence v19.22.0 RC16.32f.

Isolated theoretical portfolio layer. Reuses completed Investment Pipeline data,
never submits real orders and never changes the authoritative Autonomy chain.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from io import BytesIO
from math import isfinite, sqrt
from typing import Any, Mapping, Sequence

from durable_runtime import append_event, read_events, read_json, write_json
from storage_architecture import runtime_data_path, runtime_log_path

VERSION = "v19.22.0-rc16.32f"
STATE_KEY = "super_portfolio/state.json"
STATE_PATH = runtime_data_path("super_portfolio", "state.json")
AUDIT_KEY = "super_portfolio/audit.jsonl"
AUDIT_PATH = runtime_log_path("super_portfolio_audit.jsonl")
LATEST_PIPELINE_KEY = "investment_pipeline/latest_run.json"
LATEST_PIPELINE_PATH = runtime_data_path("investment_pipeline", "latest_run.json")
MARKET_PIPELINE_KEY = "super_portfolio/market_pipeline.json"
MARKET_PIPELINE_PATH = runtime_data_path("super_portfolio", "market_pipeline.json")

_RETURN_KEYS = (
    "return_1d", "return_3d", "return_5d", "return_10d", "return_20d",
    "return_60d", "return_1m", "return_3m",
)


def _now_dt() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def _now() -> str:
    return _now_dt().isoformat(timespec="seconds")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _candidate_price(row: Mapping[str, Any]) -> float:
    raw = row.get("raw") if isinstance(row.get("raw"), Mapping) else {}
    for value in (row.get("price"), row.get("last_price"), raw.get("last_price"), raw.get("price")):
        price = _f(value)
        if price > 0:
            return price
    return 0.0


def _score(row: Mapping[str, Any]) -> float:
    for key in ("autonomy_adjusted_investment_score", "investment_score", "score", "final_score"):
        if row.get(key) is not None:
            return max(0.0, min(100.0, _f(row.get(key))))
    return 0.0


def _risk(row: Mapping[str, Any]) -> float:
    for key in ("risk_score", "portfolio_risk_score"):
        if row.get(key) is not None:
            return max(0.0, min(100.0, _f(row.get(key), 50.0)))
    return 50.0


def _quality(row: Mapping[str, Any]) -> float:
    for key in ("data_quality_score", "data_quality"):
        value = row.get(key)
        if isinstance(value, Mapping):
            value = value.get("score")
        if value is not None:
            return max(0.0, min(100.0, _f(value, 50.0)))
    return 50.0


def _volatility(row: Mapping[str, Any], default: float = 30.0) -> float:
    raw = row.get("raw") if isinstance(row.get("raw"), Mapping) else {}
    for value in (row.get("volatility_pct"), row.get("annual_volatility"), row.get("volatility"), raw.get("volatility_pct"), raw.get("annual_volatility"), raw.get("volatility")):
        if value is not None:
            return max(0.0, min(200.0, _f(value, default)))
    return default


def _memory_snapshot() -> dict[str, Any]:
    try:
        from runtime_memory import memory_snapshot
        return dict(memory_snapshot() or {})
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _storage_usage_report() -> dict[str, Any]:
    try:
        from services.storage_service import get_storage_service
        return dict(get_storage_service().storage_usage_report() or {})
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _timestamp_from_row(row: Mapping[str, Any]) -> str:
    raw = row.get("raw") if isinstance(row.get("raw"), Mapping) else {}
    for key in ("price_timestamp", "data_timestamp", "updated_at", "captured_at", "timestamp"):
        value = row.get(key) or raw.get(key)
        if value:
            return str(value)
    return ""


def data_freshness(row: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    observed_raw = _timestamp_from_row(row)
    if not observed_raw:
        return {"status":"DATA GAP","icon":"🔴","score":0.0,"age_hours":None,"observed_at":""}
    try:
        observed = datetime.fromisoformat(observed_raw.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        reference = now or _now_dt()
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        hours=max(0.0,(reference-observed).total_seconds()/3600.0)
        if hours <= 24: status,icon,score="FRESH","🟢",100.0
        elif hours <= 72: status,icon,score="AGING","🟡",80.0
        elif hours <= 168: status,icon,score="STALE","🟠",50.0
        else: status,icon,score="STALE","🔴",20.0
        return {"status":status,"icon":icon,"score":score,"age_hours":round(hours,1),"observed_at":observed.isoformat(timespec="seconds")}
    except Exception:
        return {"status":"DATA GAP","icon":"🔴","score":0.0,"age_hours":None,"observed_at":observed_raw}


def _event_date(row: Mapping[str, Any]) -> str:
    raw = row.get("raw") if isinstance(row.get("raw"), Mapping) else {}
    for key in ("earnings_date","next_earnings_date","report_date","next_report_date","event_date"):
        value=row.get(key) or raw.get(key)
        if value:
            return str(value)
    return ""


def event_risk(row: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    value=_event_date(row)
    if not value:
        return {"status":"NONE","icon":"⚪","date":"","days_until":None}
    try:
        parsed=datetime.fromisoformat(value[:10]).date()
        ref=(now or _now_dt()).date()
        days=(parsed-ref).days
        if days < 0: return {"status":"PAST","icon":"⚪","date":value[:10],"days_until":days}
        if days <= 2: icon="🟠"
        elif days <= 7: icon="🟡"
        else: icon="🟢"
        return {"status":"UPCOMING","icon":icon,"date":value[:10],"days_until":days}
    except Exception:
        return {"status":"UNKNOWN","icon":"🟡","date":value,"days_until":None}


def decision_confidence(*, data_quality: float, freshness_score: float, regime_fit: float = 70.0, score_spread: float = 10.0, correlation_available: bool = True) -> dict[str, Any]:
    agreement=max(0.0,min(100.0,100.0-_f(score_spread)*2.0))
    corr=100.0 if correlation_available else 55.0
    score=max(0.0,min(100.0,0.30*_f(data_quality)+0.25*_f(freshness_score)+0.20*_f(regime_fit)+0.15*agreement+0.10*corr))
    if score>=80: icon,label="🟢","HIGH"
    elif score>=65: icon,label="🟡","MEDIUM"
    elif score>=50: icon,label="🟠","LOW"
    else: icon,label="🔴","VERY LOW"
    return {"score":round(score,1),"icon":icon,"label":label,"components":{"data_quality":round(_f(data_quality),1),"freshness":round(_f(freshness_score),1),"regime_fit":round(_f(regime_fit),1),"agreement":round(agreement,1),"correlation":corr}}


def turnover_cost_summary(changes: Sequence[Mapping[str, Any]], *, portfolio_value: float, gross_return_pct: float = 0.0, cost_bps: float = 10.0) -> dict[str, Any]:
    turnover=sum(abs(_f(c.get("to_pct"))-_f(c.get("from_pct"))) for c in changes)
    traded_value=max(0.0,_f(portfolio_value))*turnover/100.0
    cost=traded_value*max(0.0,_f(cost_bps))/10000.0
    cost_pct=(cost/max(1.0,_f(portfolio_value)))*100.0
    return {"turnover_pct":round(turnover,2),"traded_value":round(traded_value,2),"estimated_cost":round(cost,2),"cost_bps":round(_f(cost_bps),2),"cost_pct":round(cost_pct,4),"gross_return_pct":round(_f(gross_return_pct),4),"net_return_pct":round(_f(gross_return_pct)-cost_pct,4)}


def _position_currency(row: Mapping[str, Any]) -> str:
    raw=row.get("raw_candidate") if isinstance(row.get("raw_candidate"),Mapping) else row.get("raw") if isinstance(row.get("raw"),Mapping) else {}
    value=row.get("currency") or raw.get("currency")
    if value: return str(value).upper()
    market=str(row.get("market") or "").upper()
    return {"USA":"USD","US":"USD","NORWAY":"NOK","NORGE":"NOK","SWEDEN":"SEK","SVERIGE":"SEK","DENMARK":"DKK","DANMARK":"DKK","FINLAND":"EUR","BRAZIL":"BRL","BRASIL":"BRL"}.get(market,"")


def stress_radar(positions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows=list(positions)
    scenarios=[
        ("usa_-10","🇺🇸 USA −10%",-10.0,lambda p:"USA" in str(p.get("market") or "").upper() or str(p.get("market") or "").upper()=="US"),
        ("nordics_-10","🌍 Norden −10%",-10.0,lambda p:any(x in str(p.get("market") or "").upper() for x in ("NORWAY","NORGE","SWEDEN","SVERIGE","DENMARK","DANMARK","FINLAND"))),
        ("shipping_-30","🚢 Shipping −30%",-30.0,lambda p:any(x in str(p.get("sector") or "").upper() for x in ("SHIPPING","MARITIME","TRANSPORT"))),
        ("energy_-20","🛢️ Energi/offshore −20%",-20.0,lambda p:any(x in str(p.get("sector") or "").upper() for x in ("ENERGY","OFFSHORE","OIL","GAS"))),
        ("tech_-15","💻 Teknologi −15%",-15.0,lambda p:"TECH" in str(p.get("sector") or "").upper()),
        ("usd_-10","💵 USD/NOK −10%",-10.0,lambda p:_position_currency(p)=="USD"),
    ]
    out=[]
    for key,label,shock,predicate in scenarios:
        exposure=sum(_f(p.get("target_weight_pct")) for p in rows if predicate(p))
        impact=exposure*shock/100.0
        severity=abs(impact)
        icon="🔴" if severity>=12 else "🟠" if severity>=7 else "🟡" if severity>=3 else "🟢"
        out.append({"key":key,"label":label,"shock_pct":shock,"exposure_pct":round(exposure,1),"estimated_portfolio_impact_pct":round(impact,2),"icon":icon})
    return out


def benchmark_summary(state: Mapping[str, Any], *, portfolio_return_pct: float) -> dict[str, Any]:
    bench=state.get("benchmark") if isinstance(state.get("benchmark"),Mapping) else {}
    result={}
    for key in ("index","aurora"):
        row=dict(bench.get(key) or {}) if isinstance(bench.get(key),Mapping) else {}
        if row and row.get("return_pct") is not None:
            row["alpha_pct"]=round(_f(portfolio_return_pct)-_f(row.get("return_pct")),2)
        result[key]=row
    return result


def set_manual_aurora_benchmark(return_pct: float, *, label: str = "Aurora") -> dict[str, Any]:
    state=load_state(); bench=dict(state.get("benchmark") or {})
    bench["aurora"]={"label":str(label or "Aurora"),"return_pct":round(_f(return_pct),4),"status":"MANUAL","updated_at":_now()}
    state["benchmark"]=bench; save_state(state)
    return bench["aurora"]


def refresh_index_benchmark(state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    data=dict(state or load_state()); cfg=dict(data.get("config") or {})
    ticker=str(cfg.get("benchmark_ticker") or "^STOXX"); label=str(cfg.get("benchmark_label") or ticker)
    positions=list((data.get("positions") or {}).values())
    dates=[str(p.get("entry_date") or "")[:10] for p in positions if p.get("entry_date")]
    start=min(dates) if dates else str(data.get("created_at") or "")[:10]
    row={"ticker":ticker,"label":label,"return_pct":None,"status":"UNAVAILABLE","updated_at":_now()}
    try:
        import yfinance as yf
        hist=yf.download(ticker,start=start,progress=False,auto_adjust=False,threads=False)
        close=hist["Close"] if "Close" in hist else None
        if close is not None and len(close)>=2:
            first=float(close.iloc[0].iloc[0] if hasattr(close.iloc[0],"iloc") else close.iloc[0])
            last=float(close.iloc[-1].iloc[0] if hasattr(close.iloc[-1],"iloc") else close.iloc[-1])
            if first>0:
                row.update({"return_pct":round((last/first-1.0)*100.0,4),"status":"AVAILABLE","start_date":start,"last_price":round(last,6)})
    except Exception as exc:
        row["error"]=f"{type(exc).__name__}: {exc}"[:240]
    bench=dict(data.get("benchmark") or {}); bench["index"]=row; data["benchmark"]=bench; save_state(data)
    return row


def resource_health() -> dict[str, Any]:
    mem=_memory_snapshot(); db=_storage_usage_report()
    mem_pct=_f(mem.get("cgroup_memory_used_pct")); db_pct=_f(db.get("capacity_pct"))
    pressure=max(mem_pct,db_pct)
    if pressure>=92: status,icon="CRITICAL","🔴"
    elif pressure>=80: status,icon="WARNING","🟠"
    elif pressure>=70: status,icon="WATCH","🟡"
    else: status,icon="OK","🟢"
    return {"status":status,"icon":icon,"memory_used_pct":round(mem_pct,1),"rss_mb":_f(mem.get("process_rss_mb")),"cgroup_mb":_f(mem.get("cgroup_memory_current_mb")),"memory_limit_mb":_f(mem.get("cgroup_memory_limit_mb")),"db_used_pct":round(db_pct,1),"db_bytes":int(_f(db.get("database_bytes"))),"db_capacity_bytes":int(_f(db.get("capacity_bytes"))),"memory":mem,"database":db,"updated_at":_now()}


@dataclass(frozen=True)
class SuperPortfolioConfig:
    target_positions: int = 10
    challenger_count: int = 5
    start_cash: float = 1_000_000.0
    minimum_score: float = 60.0
    maximum_risk: float = 75.0
    warning_drawdown_pct: float = 7.0
    near_stop_drawdown_pct: float = 10.0
    hard_stop_drawdown_pct: float = 15.0
    min_rebalance_pp: float = 1.0
    max_position_pct: float = 15.0
    concentration_soft_pct: float = 40.0
    sector_penalty_per_existing: float = 1.5
    correlation_soft_limit: float = 0.60
    correlation_penalty_scale: float = 8.0
    rebalance_weekday: int = 4  # Friday
    manual_exit_cooldown_days: int = 10
    auto_pushover: bool = True
    history_limit: int = 180
    transaction_cost_bps: float = 10.0
    base_currency: str = "NOK"
    benchmark_ticker: str = "^STOXX"
    benchmark_label: str = "STOXX Europe 600"
    market_scopes: tuple[str, ...] = ("Norge", "Sverige", "Danmark", "Finland", "USA")
    # RC16.32f: broad-first funnel. Stage 1 must see the full available
    # investable universe before any shortlist is formed.
    market_universe_limit_per_market: int = 500
    # Deprecated RC16.32e constructor compatibility only; broad discovery no longer uses this cap.
    market_scan_limit_per_market: int | None = None
    market_coarse_shortlist_per_market: int = 100
    market_deep_analysis_per_market: int = 50
    market_candidates_per_market: int = 15
    market_refresh_hours: float = 12.0


def default_state(config: SuperPortfolioConfig | None = None) -> dict[str, Any]:
    cfg = config or SuperPortfolioConfig()
    return {
        "version": VERSION,
        "created_at": _now(),
        "updated_at": _now(),
        "status": "SHADOW",
        "initial_cash": cfg.start_cash,
        "cash": cfg.start_cash,
        "positions": {},
        "challengers": [],
        "history": [],
        "config": asdict(cfg),
        "source_run_id": "",
        "last_scheduled_source_run_id": "",
        "last_rebalance_date": "",
        "last_changes": [],
        "manual_exit_cooldown": {},
        "manual_exit_shadow": [],
        "benchmark": {},
        "stress_radar": [],
        "turnover_costs": {},
        "decision_confidence": {},
        "resource_health": {},
    }


def load_state() -> dict[str, Any]:
    value = read_json(STATE_KEY, STATE_PATH, {})
    return dict(value) if isinstance(value, Mapping) and value else default_state()


def save_state(state: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(state)
    value["version"] = VERSION
    value["updated_at"] = _now()
    write_json(STATE_KEY, STATE_PATH, value)
    return value


def load_latest_pipeline() -> dict[str, Any]:
    value = read_json(LATEST_PIPELINE_KEY, LATEST_PIPELINE_PATH, {})
    return dict(value) if isinstance(value, Mapping) else {}


def load_latest_super_portfolio_market_pipeline() -> dict[str, Any]:
    value = read_json(MARKET_PIPELINE_KEY, MARKET_PIPELINE_PATH, {})
    return dict(value) if isinstance(value, Mapping) else {}


def _market_pipeline_is_fresh(payload: Mapping[str, Any], cfg: "SuperPortfolioConfig", now: datetime) -> bool:
    created = str(payload.get("created_at") or "")
    if not created or not payload.get("candidates"):
        return False
    try:
        observed = datetime.fromisoformat(created.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        ref = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        return (ref - observed).total_seconds() < max(1.0, float(cfg.market_refresh_hours)) * 3600.0
    except Exception:
        return False


def _coarse_market_snapshot(tickers: Sequence[str], market: str) -> dict[str, dict[str, float]]:
    """Return low-cost market metrics for the complete discovery universe.

    The coarse pass intentionally uses batched close-price history only.  It is
    much cheaper than full candidate enrichment and lets every symbol compete
    before the expensive deep-analysis shortlist is formed.
    """
    clean = [str(t or "").strip().upper() for t in tickers if str(t or "").strip()]
    if not clean:
        return {}
    try:
        from learning_observation_engine import yfinance_series_loader
        start = (_now_dt().date() - timedelta(days=230)).isoformat()
        series_map = yfinance_series_loader(clean, start)
    except Exception:
        return {}

    out: dict[str, dict[str, float]] = {}
    for ticker in clean:
        rows = list(series_map.get(ticker) or [])
        closes = [_f(row.get("close")) for row in rows]
        closes = [value for value in closes if value > 0]
        if len(closes) < 22:
            continue

        def ret(days: int) -> float:
            if len(closes) <= days or closes[-(days + 1)] <= 0:
                return 0.0
            return (closes[-1] / closes[-(days + 1)] - 1.0) * 100.0

        daily: list[float] = []
        for left, right in zip(closes[:-1], closes[1:]):
            if left > 0:
                daily.append(right / left - 1.0)
        if daily:
            mean = sum(daily) / len(daily)
            variance = sum((value - mean) ** 2 for value in daily) / max(1, len(daily) - 1)
            volatility = sqrt(max(0.0, variance)) * sqrt(252.0) * 100.0
        else:
            volatility = 0.0
        out[ticker] = {
            "last_price": closes[-1],
            "return_20d": ret(20),
            "return_60d": ret(60),
            "volatility_pct": volatility,
        }
    return out


def _coarse_rank_market_rows(rows: Sequence[Mapping[str, Any]], market: str, limit: int) -> list[dict[str, Any]]:
    """Rank the whole available universe using cheap, auditable signals.

    Existing Smart-Universe/fundamental hints are reused when present, while
    batched price momentum guarantees bare fallback symbols are not excluded
    merely because they were late in a static ticker list.
    """
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows:
        row = dict(raw or {})
        ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        row["ticker"] = ticker
        unique.append(row)
    snapshot = _coarse_market_snapshot([row["ticker"] for row in unique], market)

    ranked: list[tuple[float, dict[str, Any]]] = []
    for row in unique:
        ticker = row["ticker"]
        snap = dict(snapshot.get(ticker) or {})
        r20 = _f(snap.get("return_20d"))
        r60 = _f(snap.get("return_60d"))
        vol = max(0.0, _f(snap.get("volatility_pct"), 35.0))
        technical = max(0.0, min(100.0, 50.0 + 1.00 * r20 + 0.35 * r60 - 0.12 * vol))

        existing = 50.0
        for key in ("smart_score", "investment_score", "ai_score", "discovery_score", "score"):
            if row.get(key) is not None:
                existing = max(0.0, min(100.0, _f(row.get(key), 50.0)))
                if key == "ai_score" and existing <= 10.0:
                    existing *= 10.0
                break
        fundamental = max(0.0, min(100.0, _f(row.get("fundamental_score"), existing)))
        quality = max(0.0, min(100.0, _f(row.get("data_quality_score", row.get("data_quality")), 50.0)))
        risk = max(0.0, min(100.0, _f(row.get("risk_score"), 50.0)))
        coarse = 0.55 * technical + 0.20 * existing + 0.10 * fundamental + 0.08 * quality + 0.07 * (100.0 - risk)

        enriched = dict(row)
        enriched.update({key: value for key, value in snap.items() if value is not None})
        enriched["coarse_score"] = round(coarse, 4)
        enriched["coarse_score_components"] = {
            "technical": round(technical, 2), "existing": round(existing, 2),
            "fundamental": round(fundamental, 2), "quality": round(quality, 2),
            "risk": round(risk, 2),
        }
        ranked.append((coarse, enriched))

    ranked.sort(key=lambda item: (item[0], str(item[1].get("ticker") or "")), reverse=True)
    return [row for _, row in ranked[: max(1, int(limit))]]


def _compact_market_candidate(assessment: Any, source_row: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(getattr(assessment, "raw", {}) or {})
    source = dict(source_row or {})
    keep = {
        "last_price", "price", "price_timestamp", "data_timestamp", "updated_at", "captured_at", "timestamp",
        "volatility_pct", "annual_volatility", "volatility", "currency", "earnings_date", "next_earnings_date",
        "report_date", "next_report_date", "event_date", "return_1d", "return_3d", "return_5d", "return_10d",
        "return_20d", "return_60d", "return_1m", "return_3m",
    }
    compact_raw = {key: raw.get(key, source.get(key)) for key in keep if raw.get(key, source.get(key)) is not None}
    return {
        "ticker": str(getattr(assessment, "ticker", source.get("ticker") or "")).upper(),
        "market": str(getattr(assessment, "market", source.get("market") or "")),
        "sector": str(getattr(assessment, "sector", source.get("sector") or source.get("industry") or "Ukjent")),
        "investment_score": _f(getattr(assessment, "investment_score", 0.0)),
        "risk_score": _f(getattr(assessment, "risk_score", 50.0), 50.0),
        "data_quality_score": _f(getattr(assessment, "data_quality", 50.0), 50.0),
        "price": _f(compact_raw.get("last_price"), _f(compact_raw.get("price"))),
        "raw": compact_raw,
        "source": "Super Portfolio independent market universe",
    }


def build_super_portfolio_market_pipeline(
    cfg: "SuperPortfolioConfig" | None = None, *, now: datetime | None = None, force_refresh: bool = False
) -> dict[str, Any]:
    """Build a bounded Norden+USA candidate feed independent of production Norway-only policy.

    This deliberately does not mutate Investment Pipeline's canonical latest_run.json.
    It uses the same local market enrichment and scoring primitives with expensive
    evidence modules disabled, then stores only a compact candidate payload.
    """
    config = cfg or SuperPortfolioConfig()
    now_dt = now or _now_dt()
    from investment_pipeline import PipelineConfig, _load_candidate_rows_from_app, _prepare_candidate_rows, score_candidate

    candidates: list[dict[str, Any]] = []
    market_stats: list[dict[str, Any]] = []
    for market in tuple(config.market_scopes):
        universe_limit = max(1, min(500, int(config.market_universe_limit_per_market)))
        coarse_limit = max(1, min(universe_limit, int(config.market_coarse_shortlist_per_market)))
        deep_limit = max(1, min(coarse_limit, int(config.market_deep_analysis_per_market)))
        pcfg = PipelineConfig(
            market_scope=str(market),
            scan_limit=universe_limit,
            deep_analysis_count=deep_limit,
            proposal_count=0,
            evidence_analysis_count=1,
            use_research=False, use_backtest=False, use_portfolio_fit=True,
            use_learning_advisor=True, use_insider_intelligence=False, use_news_intelligence=False,
            mission_id="SUPER_PORTFOLIO_BROAD_DISCOVERY",
            configuration_version=VERSION,
            full_universe_scan=True,
        ).normalized()
        raw_rows, source_label = _load_candidate_rows_from_app(pcfg)
        coarse_rows = _coarse_rank_market_rows(raw_rows, str(market), coarse_limit)
        deep_rows = coarse_rows[:deep_limit]
        prepared = _prepare_candidate_rows(deep_rows, pcfg, force_refresh=force_refresh)
        scored: list[tuple[float, dict[str, Any]]] = []
        errors = 0
        for row in prepared:
            try:
                assessment = score_candidate(row, pcfg)
                compact = _compact_market_candidate(assessment, row)
                if compact["ticker"] and compact["price"] > 0:
                    scored.append((_f(compact["investment_score"]), compact))
            except Exception:
                errors += 1
        scored.sort(key=lambda item: item[0], reverse=True)
        selected = [row for _, row in scored[: max(1, int(config.market_candidates_per_market))]]
        candidates.extend(selected)
        market_stats.append({
            "market": market,
            "universe_loaded": len(raw_rows),
            "coarse_shortlisted": len(coarse_rows),
            "deep_analyzed": len(prepared),
            "selected": len(selected),
            "errors": errors,
            "source": source_label,
        })

    candidates.sort(key=lambda row: (_f(row.get("investment_score")), -_f(row.get("risk_score"))), reverse=True)
    payload = {
        "version": VERSION,
        "run_id": f"SPM-{now_dt.strftime('%Y%m%d-%H%M%S')}",
        "created_at": now_dt.isoformat(timespec="seconds"),
        "market_scope": "Norden + USA",
        "markets": list(config.market_scopes),
        "production_norway_only_ignored": True,
        "candidates": candidates,
        "summary": {
            "candidates": len(candidates),
            "markets": market_stats,
            "selection_funnel": "FULL_AVAILABLE_UNIVERSE -> COARSE_SHORTLIST -> DEEP_ANALYSIS -> GLOBAL_TOP",
            "country_quotas": False,
        },
    }
    write_json(MARKET_PIPELINE_KEY, MARKET_PIPELINE_PATH, payload)
    return payload


def get_or_build_super_portfolio_market_pipeline(
    cfg: "SuperPortfolioConfig" | None = None, *, now: datetime | None = None, force_refresh: bool = False
) -> dict[str, Any]:
    config = cfg or SuperPortfolioConfig()
    now_dt = now or _now_dt()
    cached = load_latest_super_portfolio_market_pipeline()
    if not force_refresh and _market_pipeline_is_fresh(cached, config, now_dt):
        return cached
    return build_super_portfolio_market_pipeline(config, now=now_dt, force_refresh=force_refresh)


def _normalized_candidate(source: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(source or {})
    ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
    score, risk, quality = _score(row), _risk(row), _quality(row)
    price = _candidate_price(row)
    portfolio_score = 0.72 * score + 0.18 * quality + 0.10 * (100.0 - risk)
    return {
        "ticker": ticker,
        "market": str(row.get("market") or row.get("country") or ""),
        "sector": str(row.get("sector") or row.get("industry") or "Ukjent"),
        "price": price,
        "investment_score": score,
        "risk_score": risk,
        "quality_score": quality,
        "portfolio_score": round(portfolio_score, 4),
        "volatility_pct": _volatility(row),
        "currency": _position_currency(row),
        "data_freshness": data_freshness(row),
        "event_risk": event_risk(row),
        "raw_candidate": row,
    }


def rank_candidates(candidates: Sequence[Mapping[str, Any]], config: SuperPortfolioConfig | None = None) -> list[dict[str, Any]]:
    cfg = config or SuperPortfolioConfig()
    rows: list[dict[str, Any]] = []
    for source in candidates:
        row = _normalized_candidate(source)
        if not row["ticker"]:
            continue
        if row["investment_score"] < cfg.minimum_score or row["risk_score"] > cfg.maximum_risk or row["price"] <= 0:
            continue
        rows.append(row)
    rows.sort(key=lambda item: (-item["portfolio_score"], item["risk_score"], item["ticker"]))
    return rows


def _return_profile(row: Mapping[str, Any]) -> dict[str, float]:
    raw = row.get("raw_candidate") if isinstance(row.get("raw_candidate"), Mapping) else row
    nested = raw.get("raw") if isinstance(raw.get("raw"), Mapping) else {}
    out: dict[str, float] = {}
    for key in _RETURN_KEYS:
        value = raw.get(key) if raw.get(key) is not None else nested.get(key)
        if value is not None:
            out[key] = _f(value)
    return out


def _pearson_pair(a: Mapping[str, float], b: Mapping[str, float]) -> float | None:
    keys = [key for key in _RETURN_KEYS if key in a and key in b]
    if len(keys) < 3:
        return None
    x = [a[key] for key in keys]
    y = [b[key] for key in keys]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    num = sum((vx - mx) * (vy - my) for vx, vy in zip(x, y))
    denx = sqrt(sum((vx - mx) ** 2 for vx in x))
    deny = sqrt(sum((vy - my) ** 2 for vy in y))
    if denx <= 1e-12 or deny <= 1e-12:
        return None
    return max(-1.0, min(1.0, num / (denx * deny)))


def attach_return_profile_correlations(ranked: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Attach a low-cost correlation proxy from already-fetched multi-horizon returns.

    This does not claim to be a full daily-return correlation matrix. It is a
    resource-light return-profile correlation used only as a soft portfolio penalty.
    """
    rows = [dict(row) for row in ranked]
    profiles = {str(row.get("ticker") or ""): _return_profile(row) for row in rows}
    for row in rows:
        ticker = str(row.get("ticker") or "")
        raw = dict(row.get("raw_candidate") or {})
        existing = dict(raw.get("portfolio_correlations") or {}) if isinstance(raw.get("portfolio_correlations"), Mapping) else {}
        computed = 0
        for other, profile in profiles.items():
            if other == ticker or other in existing:
                continue
            corr = _pearson_pair(profiles.get(ticker, {}), profile)
            if corr is not None:
                existing[other] = round(corr, 4)
                computed += 1
        raw["portfolio_correlations"] = existing
        row["raw_candidate"] = raw
        row["correlation_source"] = "MULTI_HORIZON_RETURN_PROFILE" if computed else ("PIPELINE" if existing else "UNAVAILABLE")
        row["correlation_observations"] = computed
    return rows


def apply_concentration_penalties(ranked: Sequence[Mapping[str, Any]], config: SuperPortfolioConfig | None = None) -> list[dict[str, Any]]:
    """Apply soft sector/correlation penalties without imposing hard quotas."""
    cfg = config or SuperPortfolioConfig()
    out: list[dict[str, Any]] = []
    sector_counts: dict[str, int] = {}
    selected_tickers: list[str] = []
    for source in ranked:
        row = dict(source)
        sector = str(row.get("sector") or "Ukjent")
        same_count = sector_counts.get(sector, 0)
        projected_pct = 100.0 * (same_count + 1) / max(1, cfg.target_positions)
        sector_penalty = 0.0 if same_count == 0 else cfg.sector_penalty_per_existing * same_count
        sector_penalty += max(0.0, projected_pct - cfg.concentration_soft_pct) * 0.08
        raw = row.get("raw_candidate") if isinstance(row.get("raw_candidate"), Mapping) else {}
        corr_map = raw.get("portfolio_correlations") if isinstance(raw.get("portfolio_correlations"), Mapping) else {}
        max_corr = 0.0
        for ticker in selected_tickers:
            max_corr = max(max_corr, abs(_f(corr_map.get(ticker), 0.0)))
        correlation_penalty = max(0.0, max_corr - cfg.correlation_soft_limit) * cfg.correlation_penalty_scale
        row["sector_penalty"] = round(sector_penalty, 4)
        row["correlation_penalty"] = round(correlation_penalty, 4)
        row["max_portfolio_correlation"] = round(max_corr, 4)
        row["portfolio_score_adjusted"] = round(max(0.0, _f(row.get("portfolio_score")) - sector_penalty - correlation_penalty), 4)
        out.append(row)
        sector_counts[sector] = same_count + 1
        selected_tickers.append(str(row.get("ticker") or ""))
    out.sort(key=lambda item: (-_f(item.get("portfolio_score_adjusted")), _f(item.get("risk_score"), 100.0), str(item.get("ticker") or "")))
    return out


def ranking_velocity(ticker: str, current_rank: int, history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ranks: list[int] = []
    key = str(ticker or "").upper()
    for snapshot in history:
        for row in snapshot.get("ranking") or []:
            if str(row.get("ticker") or "").upper() == key:
                try:
                    ranks.append(int(row.get("rank")))
                except (TypeError, ValueError):
                    pass
                break
    if not ranks:
        return {"rank_change": 0, "rank_velocity": 0.0, "rank_arrow": "→"}
    rank_change = ranks[0] - int(current_rank)
    velocity = rank_change / max(1, len(ranks))
    if rank_change >= 10: arrow = "↑↑↑"
    elif rank_change >= 4: arrow = "↑↑"
    elif rank_change > 0: arrow = "↑"
    elif rank_change <= -10: arrow = "↓↓↓"
    elif rank_change <= -4: arrow = "↓↓"
    elif rank_change < 0: arrow = "↓"
    else: arrow = "→"
    return {"rank_change": rank_change, "rank_velocity": round(velocity, 2), "rank_arrow": arrow}


def dynamic_stop_levels(position: Mapping[str, Any], config: SuperPortfolioConfig | None = None) -> dict[str, float]:
    cfg = config or SuperPortfolioConfig()
    vol = _volatility(position)
    entry = _f(position.get("entry_price"))
    peak = _f(position.get("peak_price"))
    peak_gain = ((peak / entry) - 1.0) * 100.0 if entry > 0 and peak > 0 else 0.0
    hard = cfg.hard_stop_drawdown_pct
    if vol >= 45:
        hard = max(hard, 18.0)
    elif vol <= 18:
        hard = min(hard, 12.0)
    if peak_gain >= 60:
        hard = min(hard, 8.0)
    elif peak_gain >= 40:
        hard = min(hard, 10.0)
    elif peak_gain >= 25:
        hard = min(hard, 12.0)
    warning = min(cfg.warning_drawdown_pct, max(4.0, hard * 0.50))
    near = min(cfg.near_stop_drawdown_pct, max(warning + 1.0, hard * 0.75))
    return {
        "warning_drawdown_pct": round(warning, 2),
        "near_stop_drawdown_pct": round(near, 2),
        "hard_stop_drawdown_pct": round(hard, 2),
        "volatility_pct": round(vol, 2),
        "peak_gain_pct": round(peak_gain, 2),
    }


def _stop_status(position: Mapping[str, Any], config: SuperPortfolioConfig) -> dict[str, Any]:
    current = _f(position.get("last_price"))
    peak = max(_f(position.get("peak_price")), current)
    entry = _f(position.get("entry_price"))
    drawdown = ((current / peak) - 1.0) * 100.0 if peak > 0 and current > 0 else 0.0
    pnl = ((current / entry) - 1.0) * 100.0 if entry > 0 and current > 0 else 0.0
    dd_abs = abs(min(0.0, drawdown))
    levels = dynamic_stop_levels({**dict(position), "peak_price": peak}, config)
    hard, near, warning = levels["hard_stop_drawdown_pct"], levels["near_stop_drawdown_pct"], levels["warning_drawdown_pct"]
    if dd_abs >= hard: label, icon = "STOP TRIGGERED", "🔴"
    elif dd_abs >= near: label, icon = "NEAR STOP", "🟠"
    elif dd_abs >= warning: label, icon = "WATCH", "🟡"
    else: label, icon = "SAFE", "🟢"
    distance = max(0.0, hard - dd_abs)
    stop_price = peak * (1.0 - hard / 100.0) if peak > 0 else 0.0
    return {
        "stop_status": label, "stop_icon": icon,
        "drawdown_from_peak_pct": round(drawdown, 2), "pnl_pct": round(pnl, 2),
        "distance_to_hard_stop_pct": round(distance, 2), "hard_stop_price": round(stop_price, 4),
        **levels,
    }


def stop_pressure(position: Mapping[str, Any], history: Sequence[Mapping[str, Any]], config: SuperPortfolioConfig | None = None) -> dict[str, Any]:
    cfg = config or SuperPortfolioConfig()
    ticker = str(position.get("ticker") or "").upper()
    current_distance = _f(position.get("distance_to_hard_stop_pct"), cfg.hard_stop_drawdown_pct)
    previous_distance = None
    for snapshot in reversed(list(history)):
        for row in snapshot.get("positions") or []:
            if str(row.get("ticker") or "").upper() == ticker:
                previous_distance = _f(row.get("distance_to_hard_stop_pct"), current_distance)
                break
        if previous_distance is not None:
            break
    change = 0.0 if previous_distance is None else current_distance - previous_distance
    if change < -1.5: arrow = "↓↓"
    elif change < -0.25: arrow = "↓"
    elif change > 1.5: arrow = "↑↑"
    elif change > 0.25: arrow = "↑"
    else: arrow = "→"
    if current_distance <= 1.5: pressure, icon = "CRITICAL", "🔴"
    elif current_distance <= 4.0 and change < 0: pressure, icon = "HIGH", "🟠"
    elif current_distance <= 7.0 or change <= -2.0: pressure, icon = "ELEVATED", "🟡"
    else: pressure, icon = "LOW", "🟢"
    return {"pressure": pressure, "pressure_icon": icon, "direction_arrow": arrow, "distance_change_pct": round(change, 2), "previous_distance_to_stop_pct": None if previous_distance is None else round(previous_distance, 2)}


def portfolio_health(positions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(positions)
    if not rows:
        return {"score": 0.0, "icon": "🔴", "label": "EMPTY", "components": {}}
    quality = sum(_f(p.get("portfolio_score_adjusted"), _f(p.get("portfolio_score"), 50.0)) for p in rows) / len(rows)
    risk = 100.0 - sum(_f(p.get("risk_score"), 50.0) for p in rows) / len(rows)
    sectors: dict[str, int] = {}
    for p in rows:
        sector = str(p.get("sector") or "Ukjent")
        sectors[sector] = sectors.get(sector, 0) + 1
    max_share = max(sectors.values()) / len(rows)
    diversification = max(0.0, min(100.0, 120.0 - max_share * 100.0))
    stop_map = {"SAFE": 100.0, "WATCH": 70.0, "NEAR STOP": 35.0, "STOP TRIGGERED": 0.0}
    stop_safety = sum(stop_map.get(str(p.get("stop_status") or "SAFE"), 60.0) for p in rows) / len(rows)
    correlation = 100.0 - min(100.0, sum(_f(p.get("max_portfolio_correlation"), 0.0) for p in rows) / len(rows) * 100.0)
    score = max(0.0, min(100.0, 0.32 * quality + 0.20 * risk + 0.20 * diversification + 0.15 * stop_safety + 0.13 * correlation))
    if score >= 80: icon, label = "🟢", "STRONG"
    elif score >= 65: icon, label = "🟡", "OK"
    elif score >= 50: icon, label = "🟠", "WEAK"
    else: icon, label = "🔴", "RISK"
    return {"score": round(score, 1), "icon": icon, "label": label, "components": {"quality": round(quality,1), "risk": round(risk,1), "diversification": round(diversification,1), "stop_safety": round(stop_safety,1), "correlation": round(correlation,1)}}


def ai_would_do_today(positions: Mapping[str, Mapping[str, Any]], target: Mapping[str, float], min_rebalance_pp: float = 1.0) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    current = {str(k): dict(v) for k, v in positions.items()}
    for ticker, target_weight in target.items():
        old = current.get(str(ticker), {})
        old_weight = _f(old.get("target_weight_pct"))
        delta = _f(target_weight) - old_weight
        if not old: action = "BUY"
        elif abs(delta) < min_rebalance_pp: continue
        else: action = "ADD" if delta > 0 else "REDUCE"
        actions.append({"action": action, "ticker": str(ticker), "from_pct": round(old_weight,2), "to_pct": round(_f(target_weight),2), "delta_pct": round(delta,2), "advisory_only": True})
    for ticker, old in current.items():
        if ticker not in target:
            old_weight = _f(old.get("target_weight_pct"))
            actions.append({"action": "SELL", "ticker": ticker, "from_pct": round(old_weight,2), "to_pct": 0.0, "delta_pct": round(-old_weight,2), "advisory_only": True})
    action_order = {"SELL": 0, "REDUCE": 1, "BUY": 2, "ADD": 3}
    actions.sort(key=lambda row: (action_order.get(row["action"], 9), -abs(_f(row.get("delta_pct"))), row["ticker"]))
    return actions


def target_weights(ranked: Sequence[Mapping[str, Any]], config: SuperPortfolioConfig | None = None) -> dict[str, float]:
    cfg = config or SuperPortfolioConfig()
    selected = list(ranked)[: cfg.target_positions]
    if not selected:
        return {}
    raw: dict[str, float] = {}
    for row in selected:
        risk_factor = max(0.25, 1.0 - _f(row.get("risk_score"), 50.0) / 140.0)
        raw[str(row["ticker"])] = max(0.01, _f(row.get("portfolio_score_adjusted"), _f(row.get("portfolio_score"))) * risk_factor)
    total = sum(raw.values()) or 1.0
    weights = {ticker: 100.0 * value / total for ticker, value in raw.items()}
    for _ in range(5):
        over = {k: v for k, v in weights.items() if v > cfg.max_position_pct}
        if not over: break
        excess = sum(v - cfg.max_position_pct for v in over.values())
        for k in over: weights[k] = cfg.max_position_pct
        under = [k for k, v in weights.items() if v < cfg.max_position_pct - 1e-9]
        base = sum(weights[k] for k in under)
        if not under or base <= 0: break
        for k in under: weights[k] += excess * weights[k] / base
    norm = sum(weights.values()) or 1.0
    return {k: round(v * 100.0 / norm, 2) for k, v in weights.items()}


def _cooldown_active(state: Mapping[str, Any], ticker: str, now: datetime) -> bool:
    value = (state.get("manual_exit_cooldown") or {}).get(ticker)
    if not value:
        return False
    try:
        until = datetime.fromisoformat(str(value))
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return until > now
    except Exception:
        return False


def _position_from_row(row: Mapping[str, Any], weight: float, old: Mapping[str, Any], now_iso: str, cfg: SuperPortfolioConfig, history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    entry_price = _f(old.get("entry_price")) or _f(row.get("price"))
    entry_date = str(old.get("entry_date") or now_iso)
    peak = max(_f(old.get("peak_price")), _f(row.get("price")))
    pos = {
        "ticker": row.get("ticker"), "market": row.get("market"), "sector": row.get("sector"),
        "entry_date": entry_date, "entry_price": entry_price, "last_price": _f(row.get("price")), "peak_price": peak,
        "target_weight_pct": round(_f(weight), 2), "investment_score": row.get("investment_score"), "portfolio_score": row.get("portfolio_score"),
        "portfolio_score_adjusted": row.get("portfolio_score_adjusted", row.get("portfolio_score")),
        "sector_penalty": row.get("sector_penalty", 0.0), "correlation_penalty": row.get("correlation_penalty", 0.0),
        "max_portfolio_correlation": row.get("max_portfolio_correlation", 0.0), "correlation_source": row.get("correlation_source", "UNAVAILABLE"),
        "rank": row.get("rank"), "rank_change": row.get("rank_change", 0), "rank_velocity": row.get("rank_velocity", 0.0), "rank_arrow": row.get("rank_arrow", "→"),
        "risk_score": row.get("risk_score"), "quality_score": row.get("quality_score"), "volatility_pct": row.get("volatility_pct"),
        "currency": row.get("currency"), "data_freshness": dict(row.get("data_freshness") or {}), "event_risk": dict(row.get("event_risk") or {}),
        "why_here": list(row.get("why_here") or []),
    }
    pos.update(_stop_status(pos, cfg))
    pressure = stop_pressure(pos, history, cfg)
    pos.update({"stop_pressure": pressure["pressure"], "stop_pressure_icon": pressure["pressure_icon"], "stop_direction_arrow": pressure["direction_arrow"], "stop_distance_change_pct": pressure["distance_change_pct"]})
    return pos


def _explanation_for(row: Mapping[str, Any]) -> list[str]:
    reasons = [f"AI-score {_f(row.get('portfolio_score_adjusted'), _f(row.get('portfolio_score'))):.1f}"]
    if _f(row.get("sector_penalty")) > 0:
        reasons.append(f"sektorstraff -{_f(row.get('sector_penalty')):.1f}")
    if _f(row.get("correlation_penalty")) > 0:
        reasons.append(f"korrelasjonsstraff -{_f(row.get('correlation_penalty')):.1f}")
    reasons.append(f"risiko {_f(row.get('risk_score')):.0f}/100")
    if row.get("rank"):
        reasons.append(f"rank #{row.get('rank')} {row.get('rank_arrow','→')}")
    return reasons


def _rebalance_due(state: Mapping[str, Any], now: datetime, cfg: SuperPortfolioConfig, policy: str) -> bool:
    if not state.get("positions"):
        return True
    if str(policy).upper() == "FORCE":
        return True
    if str(policy).upper() == "ANALYZE_ONLY":
        return False
    if now.weekday() != int(cfg.rebalance_weekday):
        return False
    return str(state.get("last_rebalance_date") or "") != now.date().isoformat()


def _stop_alerts(previous: Mapping[str, Mapping[str, Any]], current: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    severity = {"SAFE": 0, "WATCH": 1, "NEAR STOP": 2, "STOP TRIGGERED": 3}
    alerts: list[dict[str, Any]] = []
    for ticker, row in current.items():
        old = previous.get(ticker) or {}
        old_status = str(old.get("stop_status") or "SAFE")
        new_status = str(row.get("stop_status") or "SAFE")
        if severity.get(new_status, 0) > severity.get(old_status, 0):
            alerts.append({"ticker": ticker, "from": old_status, "to": new_status, "distance_pct": row.get("distance_to_hard_stop_pct"), "direction": row.get("stop_direction_arrow"), "pressure": row.get("stop_pressure")})
    return alerts


def evaluate(*, pipeline: Mapping[str, Any] | None = None, persist: bool = True, now: datetime | None = None, rebalance_policy: str = "FORCE") -> dict[str, Any]:
    pipeline = dict(pipeline or get_or_build_super_portfolio_market_pipeline())
    state = load_state()
    now_dt = now or _now_dt()
    now_iso = now_dt.isoformat(timespec="seconds")
    config_data = state.get("config") if isinstance(state.get("config"), Mapping) else {}
    allowed = set(SuperPortfolioConfig.__dataclass_fields__)
    cfg = SuperPortfolioConfig(**{k: v for k, v in config_data.items() if k in allowed})
    candidates = list(pipeline.get("candidates") or pipeline.get("proposals") or [])
    base_ranked = attach_return_profile_correlations(rank_candidates(candidates, cfg))
    ranked_all = apply_concentration_penalties(base_ranked, cfg)
    history = list(state.get("history") or [])
    for index, row in enumerate(ranked_all, start=1):
        row["rank"] = index
        row.update(ranking_velocity(str(row.get("ticker") or ""), index, history))
        row["why_here"] = _explanation_for(row)
    manual_shadow = [dict(row) for row in ranked_all if _cooldown_active(state, str(row.get("ticker") or ""), now_dt)]
    ranked = [row for row in ranked_all if not _cooldown_active(state, str(row.get("ticker") or ""), now_dt)]
    weights = target_weights(ranked, cfg)
    by_ticker = {str(row["ticker"]): row for row in ranked}
    previous = {str(k): dict(v) for k, v in (state.get("positions") or {}).items()}
    advisory = ai_would_do_today(previous, weights, cfg.min_rebalance_pp)
    rebalance_due = _rebalance_due(state, now_dt, cfg, rebalance_policy)
    positions: dict[str, dict[str, Any]] = {}
    changes: list[dict[str, Any]] = []

    if rebalance_due:
        for ticker, weight in weights.items():
            row = by_ticker[ticker]
            old = previous.get(ticker) or {}
            pos = _position_from_row(row, weight, old, now_iso, cfg, history)
            positions[ticker] = pos
            old_weight = _f(old.get("target_weight_pct"))
            if not old:
                changes.append({"action": "BUY", "ticker": ticker, "from_pct": 0.0, "to_pct": weight, "reason_code": "INITIAL_OR_REBALANCE", "reason": "Ny Top-kandidat ved rebalansering"})
            elif abs(weight - old_weight) >= cfg.min_rebalance_pp:
                changes.append({"action": "ADD" if weight > old_weight else "REDUCE", "ticker": ticker, "from_pct": old_weight, "to_pct": weight, "reason_code": "WEEKLY_REBALANCE", "reason": "Målvekt endret etter ny rangering"})
        for ticker, old in previous.items():
            if ticker not in positions:
                changes.append({"action": "SELL", "ticker": ticker, "from_pct": _f(old.get("target_weight_pct")), "to_pct": 0.0, "reason_code": "WEEKLY_REBALANCE", "reason": "Ikke lenger i valgt Top-portefølje"})
        state["last_rebalance_date"] = now_dt.date().isoformat()
    else:
        # Daily analysis updates price/score/stop intelligence but preserves target weights.
        for ticker, old in previous.items():
            row = by_ticker.get(ticker)
            if row:
                pos = _position_from_row(row, _f(old.get("target_weight_pct")), old, now_iso, cfg, history)
            else:
                pos = dict(old)
                pos.update(_stop_status(pos, cfg))
                pressure = stop_pressure(pos, history, cfg)
                pos.update({"stop_pressure": pressure["pressure"], "stop_pressure_icon": pressure["pressure_icon"], "stop_direction_arrow": pressure["direction_arrow"], "stop_distance_change_pct": pressure["distance_change_pct"]})
            if str(pos.get("stop_status")) == "STOP TRIGGERED":
                changes.append({"action": "SELL", "ticker": ticker, "from_pct": _f(old.get("target_weight_pct")), "to_pct": 0.0, "reason_code": "HARD_STOP", "reason": "Dynamisk hard stop utløst"})
                continue
            positions[ticker] = pos

    challengers = ranked[cfg.target_positions: cfg.target_positions + cfg.challenger_count]
    health = portfolio_health(list(positions.values()))
    position_rows = list(positions.values())
    weighted_return = 0.0
    total_weight = sum(_f(p.get("target_weight_pct")) for p in position_rows)
    if total_weight > 0:
        weighted_return = sum(_f(p.get("pnl_pct")) * _f(p.get("target_weight_pct")) for p in position_rows) / total_weight
    turnover = turnover_cost_summary(changes, portfolio_value=_f(state.get("initial_cash"), cfg.start_cash), gross_return_pct=weighted_return, cost_bps=cfg.transaction_cost_bps)
    stress = stress_radar(position_rows)
    freshness_scores = [_f((p.get("data_freshness") or {}).get("score")) for p in position_rows]
    avg_freshness = sum(freshness_scores) / len(freshness_scores) if freshness_scores else 0.0
    avg_quality = sum(_f(p.get("quality_score"), 50.0) for p in position_rows) / len(position_rows) if position_rows else 0.0
    selected_scores = [_f(p.get("portfolio_score_adjusted"), _f(p.get("portfolio_score"))) for p in position_rows]
    spread = (max(selected_scores) - min(selected_scores)) if len(selected_scores) > 1 else 0.0
    regime_fit = _f(pipeline.get("regime_fit_score"), 70.0)
    confidence = decision_confidence(data_quality=avg_quality, freshness_score=avg_freshness, regime_fit=regime_fit, score_spread=spread, correlation_available=all(str(p.get("correlation_source") or "UNAVAILABLE") != "UNAVAILABLE" for p in position_rows) if position_rows else False)
    stop_alerts = _stop_alerts(previous, positions)
    ranking_snapshot = [{"ticker": row.get("ticker"), "rank": row.get("rank"), "score": row.get("portfolio_score_adjusted"), "rank_arrow": row.get("rank_arrow")} for row in ranked_all[: max(cfg.target_positions + cfg.challenger_count, 30)]]
    snapshot = {
        "at": now_iso,
        "source_run_id": str(pipeline.get("run_id") or pipeline.get("report_id") or ""),
        "positions": [{k: v for k, v in p.items() if k != "raw_candidate"} for p in positions.values()],
        "ranking": ranking_snapshot,
        "portfolio_health": health,
        "ai_would_do_today": advisory,
        "changes": changes,
        "stop_alerts": stop_alerts,
        "rebalance_due": rebalance_due,
    }
    state.update({
        "positions": positions,
        "challengers": [{k: v for k, v in row.items() if k != "raw_candidate"} for row in challengers],
        "source_run_id": snapshot["source_run_id"],
        "portfolio_health": health,
        "ai_would_do_today": advisory,
        "last_changes": changes,
        "last_stop_alerts": stop_alerts,
        "manual_exit_shadow": [{"ticker": r.get("ticker"), "rank": r.get("rank"), "score": r.get("portfolio_score_adjusted"), "price": r.get("price"), "rank_arrow": r.get("rank_arrow")} for r in manual_shadow[:20]],
        "stress_radar": stress,
        "turnover_costs": turnover,
        "decision_confidence": confidence,
    })
    history.append(snapshot)
    state["history"] = history[-max(10, int(cfg.history_limit)):]
    if persist:
        save_state(state)
        append_event(AUDIT_KEY, AUDIT_PATH, {"timestamp": now_iso, "event": "EVALUATE", "changes": changes, "stop_alerts": stop_alerts, "portfolio_health": health, "source_run_id": snapshot["source_run_id"], "rebalance_due": rebalance_due})
    return {"state": state, "ranked": ranked, "changes": changes, "snapshot": snapshot, "portfolio_health": health, "ai_would_do_today": advisory, "stop_alerts": stop_alerts, "rebalance_due": rebalance_due, "stress_radar": stress, "turnover_costs": turnover, "decision_confidence": confidence}


def manual_exit(ticker: str, note: str = "") -> dict[str, Any]:
    state = load_state(); positions = dict(state.get("positions") or {})
    key = str(ticker or "").strip().upper()
    row = positions.pop(key, None)
    if not row:
        return {"ok": False, "reason": "Position not found"}
    cfg_data = state.get("config") if isinstance(state.get("config"), Mapping) else {}
    cooldown_days = int(cfg_data.get("manual_exit_cooldown_days") or SuperPortfolioConfig().manual_exit_cooldown_days)
    until = _now_dt() + timedelta(days=max(1, cooldown_days))
    event = {"timestamp": _now(), "event": "MANUAL_EXIT", "ticker": key, "price": row.get("last_price"), "pnl_pct": row.get("pnl_pct"), "note": str(note or ""), "cooldown_until": until.isoformat(timespec="seconds")}
    state["positions"] = positions
    state.setdefault("manual_exits", []).append(event)
    state.setdefault("manual_exit_cooldown", {})[key] = event["cooldown_until"]
    save_state(state); append_event(AUDIT_KEY, AUDIT_PATH, event)
    return {"ok": True, **event}


def dashboard_summary(state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    data = dict(state or load_state())
    positions = list((data.get("positions") or {}).values())
    weighted = 0.0
    total_weight = sum(_f(p.get("target_weight_pct")) for p in positions)
    if total_weight > 0:
        weighted = sum(_f(p.get("pnl_pct")) * _f(p.get("target_weight_pct")) for p in positions) / total_weight
    fastest = max(positions, key=lambda p: _f(p.get("rank_velocity")), default={})
    nearest = min(positions, key=lambda p: _f(p.get("distance_to_hard_stop_pct"), 999.0), default={})
    challengers = list(data.get("challengers") or [])
    challenger = max(challengers, key=lambda p: _f(p.get("portfolio_score_adjusted"), _f(p.get("portfolio_score"))), default={})
    changes = list(data.get("last_changes") or [])
    advisory = list(data.get("ai_would_do_today") or [])
    return {
        "portfolio_return_pct": round(weighted, 2),
        "positions": len(positions),
        "health": dict(data.get("portfolio_health") or {}),
        "fastest_mover": dict(fastest or {}),
        "nearest_stop": dict(nearest or {}),
        "challenger": dict(challenger or {}),
        "last_change": dict(changes[-1]) if changes else {},
        "advisory": dict(advisory[0]) if advisory else {},
        "updated_at": data.get("updated_at"),
    }


def master_checklist() -> list[dict[str, str]]:
    """Release gate: every promised Super Portfolio capability is explicitly tracked."""
    return [
        {"key":"start_portfolio", "status":"DONE", "label":"Synlig startportefølje og inngangsdata"},
        {"key":"position_development", "status":"DONE", "label":"Utvikling per aksje siden inngang"},
        {"key":"change_history", "status":"DONE", "label":"Historikk for BUY/SELL/ADD/REDUCE"},
        {"key":"dynamic_weights", "status":"DONE", "label":"Dynamiske risikovektede målvekter"},
        {"key":"weekly_rebalance", "status":"DONE", "label":"Daglig analyse, ordinær rebalansering ukentlig"},
        {"key":"immediate_risk_exit", "status":"DONE", "label":"Dynamisk hard stop kan utløse umiddelbar Shadow-exit"},
        {"key":"dynamic_stop_loss", "status":"DONE", "label":"Volatilitets- og gevinsttilpasset trailing stop"},
        {"key":"stop_pressure", "status":"DONE", "label":"SAFE/WATCH/NEAR STOP/STOP + retning/piler"},
        {"key":"manual_exit", "status":"DONE", "label":"Manuell exit med cooldown og fortsatt Shadow-observasjon"},
        {"key":"challengers", "status":"DONE", "label":"Challenger-liste"},
        {"key":"ranking_velocity", "status":"DONE", "label":"Ranking Velocity / raske klatrere"},
        {"key":"sector_penalty", "status":"DONE", "label":"Myk sektor-/konsentrasjonsstraff"},
        {"key":"correlation_penalty", "status":"DONE", "label":"Ressurslett multi-horisont korrelasjonsstraff uten nettverkskall"},
        {"key":"portfolio_health", "status":"DONE", "label":"Portfolio Health"},
        {"key":"ai_would_do_today", "status":"DONE", "label":"AI WOULD DO TODAY – rådgivende"},
        {"key":"why_here", "status":"DONE", "label":"Hvorfor aksjen er med / scoreforklaring"},
        {"key":"what_changed", "status":"DONE", "label":"Endringer lagres med reason/reason_code"},
        {"key":"scheduler_auto_evaluation", "status":"DONE", "label":"Automatisk Shadow-vurdering på ny Super Portfolio market-feed"},
        {"key":"independent_multimarket_universe", "status":"DONE", "label":"Eget Super Portfolio-univers: Norge, Sverige, Danmark, Finland og USA"},
        {"key":"production_norway_isolation", "status":"DONE", "label":"PRODUCTION_NORWAY_ONLY påvirker ikke Super Portfolio og hovedkjeden forblir isolert"},
        {"key":"broad_universe_first_pass", "status":"DONE", "label":"Bred første-pass ser hele tilgjengelige univers før shortlist"},
        {"key":"coarse_to_deep_funnel", "status":"DONE", "label":"Ressurslett grovscore -> shortlist -> dyp analyse -> global Top-10 uten landkvoter"},
        {"key":"automatic_pushover", "status":"DONE", "label":"Automatisk Pushover ved reelle Shadow-endringer og stop-varsler"},
        {"key":"shareable_pdf", "status":"DONE", "label":"Publiserbar PDF med offentlig lenke"},
        {"key":"downloadable_pdf", "status":"DONE", "label":"PDF kan lastes ned direkte"},
        {"key":"front_page_window", "status":"DONE", "label":"Kompakt Super Portfolio-vindu på forsiden med direkteknapp"},
        {"key":"two_banner_contract", "status":"DONE", "label":"Ingen tredje banner – eksisterende to bannere beholdes"},
        {"key":"master_release_gate", "status":"DONE", "label":"Master-checkliste vises i modulen og følger release"},
        {"key":"external_benchmark", "status":"DONE", "label":"Automatisk indeksbenchmark + valgfri manuell Aurora-benchmark"},
        {"key":"stress_radar", "status":"DONE", "label":"Scenario-basert Stress Radar for marked, sektor og valuta"},
        {"key":"resource_panel", "status":"DONE", "label":"Eget resource-panel for memory/cgroup og DB-kapasitet"},
        {"key":"data_freshness", "status":"DONE", "label":"Data Freshness / datakvalitet med FRESH/AGING/STALE/DATA GAP"},
        {"key":"turnover_costs", "status":"DONE", "label":"Turnover, estimert kurtasje/slippage og nettoavkastning"},
        {"key":"event_risk", "status":"DONE", "label":"Event Risk for kommende resultat-/rapportdato når data finnes"},
        {"key":"decision_confidence", "status":"DONE", "label":"Decision Confidence basert på kvalitet, ferskhet, regime og signalenighet"},
    ]


def build_pdf(state: Mapping[str, Any] | None = None) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    data = dict(state or load_state())
    out = BytesIO(); doc = SimpleDocTemplate(out, pagesize=A4, rightMargin=12*mm, leftMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm)
    styles = getSampleStyleSheet(); story = [Paragraph("AI Super Portfolio", styles["Title"]), Paragraph(f"{VERSION} · Shadow mode · {data.get('updated_at','-')}", styles["Normal"]), Spacer(1, 8)]
    health = data.get("portfolio_health") if isinstance(data.get("portfolio_health"), Mapping) else {}
    if health:
        story.append(Paragraph(f"Portfolio Health: {health.get('icon','')} {_f(health.get('score')):.1f}/100 · {health.get('label','-')}", styles["Heading2"]))
        components = health.get("components") if isinstance(health.get("components"), Mapping) else {}
        story.append(Paragraph(" · ".join(f"{k}: {_f(v):.1f}" for k, v in components.items()), styles["Normal"])); story.append(Spacer(1, 6))
    rows = [["Aksje", "Vekt", "Fra inn", "AI", "Rank", "Stop", "Press"]]
    for p in (data.get("positions") or {}).values():
        rows.append([p.get("ticker"), f"{_f(p.get('target_weight_pct')):.2f}%", f"{_f(p.get('pnl_pct')):+.2f}%", f"{_f(p.get('portfolio_score_adjusted'), _f(p.get('portfolio_score'))):.1f}", f"#{p.get('rank','-')} {p.get('rank_arrow','→')}", f"{p.get('stop_icon','')} {p.get('stop_status','')}", f"{p.get('stop_pressure_icon','')} {p.get('stop_pressure','-')} {p.get('stop_direction_arrow','→')}"])
    table = Table(rows, repeatRows=1, colWidths=[24*mm, 21*mm, 23*mm, 20*mm, 25*mm, 36*mm, 42*mm])
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("GRID",(0,0),(-1,-1),0.25,colors.grey),("FONTSIZE",(0,0),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story.append(table); story.append(Spacer(1, 10))
    summary = dashboard_summary(data)
    bench = benchmark_summary(data, portfolio_return_pct=_f(summary.get("portfolio_return_pct")))
    story.append(Paragraph("Benchmark", styles["Heading2"]))
    for key in ("index", "aurora"):
        row = bench.get(key) or {}
        if row:
            story.append(Paragraph(f"{row.get('label', key)}: {_f(row.get('return_pct')):+.2f}% · alpha {_f(row.get('alpha_pct')):+.2f} pp · {row.get('status','-')}", styles["Normal"]))
    if not any(bench.get(k) for k in ("index","aurora")):
        story.append(Paragraph("Ingen ekstern benchmark lagret.", styles["Normal"]))
    story.append(Spacer(1, 6)); story.append(Paragraph("Decision Confidence", styles["Heading2"]))
    conf = data.get("decision_confidence") if isinstance(data.get("decision_confidence"), Mapping) else {}
    story.append(Paragraph(f"{conf.get('icon','')} {_f(conf.get('score')):.1f}/100 · {conf.get('label','-')}", styles["Normal"]))
    story.append(Spacer(1, 6)); story.append(Paragraph("Turnover & costs", styles["Heading2"]))
    tc = data.get("turnover_costs") if isinstance(data.get("turnover_costs"), Mapping) else {}
    story.append(Paragraph(f"Turnover {_f(tc.get('turnover_pct')):.2f}% · estimated cost {_f(tc.get('estimated_cost')):.2f} · net return {_f(tc.get('net_return_pct')):+.2f}%", styles["Normal"]))
    story.append(Spacer(1, 6)); story.append(Paragraph("Stress Radar", styles["Heading2"]))
    stress = data.get("stress_radar") or []
    if stress:
        for row in stress[:8]:
            story.append(Paragraph(f"{row.get('label')}: exposure {_f(row.get('exposure_pct')):.1f}% · estimated impact {_f(row.get('estimated_portfolio_impact_pct')):+.2f}%", styles["Normal"]))
    else:
        story.append(Paragraph("Ingen stress-scenarier tilgjengelig.", styles["Normal"]))
    story.append(Spacer(1, 10)); story.append(Paragraph("Challengers", styles["Heading2"]))
    challenger_text = ", ".join(f"{r.get('ticker')} ({_f(r.get('portfolio_score_adjusted'), _f(r.get('portfolio_score'))):.1f}, {r.get('rank_arrow','→')})" for r in data.get("challengers") or []) or "Ingen"
    story.append(Paragraph(challenger_text, styles["Normal"])); story.append(Spacer(1, 8))
    story.append(Paragraph("AI WOULD DO TODAY (advisory only)", styles["Heading2"]))
    actions = data.get("ai_would_do_today") or []
    if actions:
        for action in actions[:12]:
            story.append(Paragraph(f"{action.get('action')} {action.get('ticker')}: {_f(action.get('from_pct')):.1f}% → {_f(action.get('to_pct')):.1f}%", styles["Normal"]))
    else:
        story.append(Paragraph("Ingen foreslåtte endringer.", styles["Normal"]))
    story.append(Spacer(1, 8)); story.append(Paragraph("Siste endringer", styles["Heading2"]))
    for change in list(data.get("last_changes") or [])[:12]:
        story.append(Paragraph(f"{change.get('action')} {change.get('ticker')}: {_f(change.get('from_pct')):.1f}% → {_f(change.get('to_pct')):.1f}% · {change.get('reason','')}", styles["Normal"]))
    doc.build(story)
    return out.getvalue()


def publish_pdf_report(state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    from public_report_store import publish_durable_pdf
    from report_delivery import public_report_url
    run = {"report_id": f"SUPER-{datetime.now().strftime('%Y%m%d-%H%M%S')}", "public_pdf_name": f"SuperPortfolio_{datetime.now().strftime('%Y-%m-%d_%H%M')}.pdf"}
    publish_durable_pdf(run, build_pdf(state), document_kind="super_portfolio")
    run["report_url"] = public_report_url(run)
    return run


def notify_changes(changes: Sequence[Mapping[str, Any]], state: Mapping[str, Any] | None = None) -> tuple[bool, str]:
    if not changes:
        return True, "no changes"
    from notifier import normalize_notification_result, send_pushover_alert
    report = publish_pdf_report(state)
    data = dict(state or load_state())
    health = data.get("portfolio_health") if isinstance(data.get("portfolio_health"), Mapping) else {}
    lines = ["🌍 AI SUPER PORTFOLIO", f"🔄 {len(changes)} endring(er)"]
    if health: lines.append(f"{health.get('icon','')} Health {_f(health.get('score')):.1f}/100")
    icons = {"BUY":"🟢","ADD":"🔵","REDUCE":"🟠","SELL":"🔴"}
    for c in list(changes)[:8]:
        lines.append(f"{icons.get(str(c.get('action')), '•')} {c.get('action')} {c.get('ticker')} {_f(c.get('from_pct')):.1f}% → {_f(c.get('to_pct')):.1f}%")
    response = send_pushover_alert("\n".join(lines), title="Super Portfolio endret", url=report.get("report_url") or None, url_title="Åpne PDF")
    return normalize_notification_result(response)


def notify_stop_alerts(alerts: Sequence[Mapping[str, Any]], state: Mapping[str, Any] | None = None) -> tuple[bool, str]:
    if not alerts:
        return True, "no alerts"
    from notifier import normalize_notification_result, send_pushover_alert
    report = publish_pdf_report(state)
    lines = ["🛡️ SUPER PORTFOLIO – STOP WATCH"]
    for row in list(alerts)[:8]:
        lines.append(f"{row.get('ticker')} {row.get('from')} → {row.get('to')} · {row.get('distance_pct')}% til stop {row.get('direction','→')}")
    response = send_pushover_alert("\n".join(lines), title="Super Portfolio stop-varsel", url=report.get("report_url") or None, url_title="Åpne PDF")
    return normalize_notification_result(response)


def run_scheduled_shadow_cycle() -> dict[str, Any]:
    """Evaluate only when the independent Super Portfolio market feed produced a new run.

    Normal scheduled runs use AUTO policy: daily analysis/stop surveillance,
    weekly ordinary rebalancing, immediate hard-stop exits.
    """
    state = load_state()
    config_data = state.get("config") if isinstance(state.get("config"), Mapping) else {}
    allowed = set(SuperPortfolioConfig.__dataclass_fields__)
    cfg = SuperPortfolioConfig(**{k: v for k, v in config_data.items() if k in allowed})
    pipeline = get_or_build_super_portfolio_market_pipeline(cfg=cfg)
    source_id = str(pipeline.get("run_id") or pipeline.get("report_id") or "")
    if not source_id:
        return {"state": "NO_PIPELINE", "source_run_id": ""}
    if source_id == str(state.get("last_scheduled_source_run_id") or ""):
        return {"state": "NOT_DUE", "source_run_id": source_id}
    result = evaluate(pipeline=pipeline, persist=True, rebalance_policy="AUTO")
    new_state = dict(result.get("state") or load_state())
    new_state["last_scheduled_source_run_id"] = source_id
    index_row = refresh_index_benchmark(new_state)
    benchmark = dict(new_state.get("benchmark") or {})
    benchmark["index"] = index_row
    new_state["benchmark"] = benchmark
    new_state["resource_health"] = resource_health()
    notification = {"changes": "NOT_SENT", "stops": "NOT_SENT"}
    cfg = dict(new_state.get("config") or {})
    if bool(cfg.get("auto_pushover", True)):
        if result.get("changes"):
            ok, detail = notify_changes(result["changes"], new_state)
            notification["changes"] = "SENT" if ok else f"FAILED:{detail}"
        if result.get("stop_alerts"):
            ok, detail = notify_stop_alerts(result["stop_alerts"], new_state)
            notification["stops"] = "SENT" if ok else f"FAILED:{detail}"
    save_state(new_state)
    append_event(AUDIT_KEY, AUDIT_PATH, {"timestamp": _now(), "event": "SCHEDULED_SHADOW_CYCLE", "source_run_id": source_id, "changes": len(result.get("changes") or []), "stop_alerts": len(result.get("stop_alerts") or []), "notification": notification})
    return {"state": "COMPLETED", "source_run_id": source_id, "changes": len(result.get("changes") or []), "stop_alerts": len(result.get("stop_alerts") or []), "rebalance_due": bool(result.get("rebalance_due")), "notification": notification}


def audit_rows(limit: int = 500) -> list[dict[str, Any]]:
    return read_events(AUDIT_KEY, AUDIT_PATH, limit=limit)
