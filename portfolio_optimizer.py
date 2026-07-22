"""Portfolio Optimizer v18.6.82.

Read-only portfolio risk and allocation laboratory. The module analyses the
Paper Trading portfolio and may produce rebalance proposals, but it never
places trades or mutates production rules.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from storage_architecture import runtime_data_path

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None  # type: ignore
try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # type: ignore

OPTIMIZER_DIR = runtime_data_path("portfolio_optimizer")
LATEST_REPORT_PATH = OPTIMIZER_DIR / "latest_report.json"
SETTINGS_PATH = OPTIMIZER_DIR / "settings.json"


@dataclass
class PortfolioLimits:
    max_position_pct: float = 10.0
    max_sector_pct: float = 25.0
    max_positions: int = 15
    min_cash_pct: float = 15.0
    max_pair_correlation: float = 0.85
    annual_risk_budget_pct: float = 18.0
    var_confidence: float = 0.95


DEFAULT_SETTINGS = asdict(PortfolioLimits())


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else float(default)
    except Exception:
        return float(default)


def _atomic_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def load_settings() -> PortfolioLimits:
    data = dict(DEFAULT_SETTINGS)
    try:
        if SETTINGS_PATH.exists():
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, Mapping):
                data.update(raw)
    except Exception:
        pass
    try:
        from autonomi_core.configuration.registry import read
        central = read("portfolio.optimizer", {})
        if isinstance(central, Mapping):
            data.update(central)
    except Exception:
        pass
    return PortfolioLimits(
        max_position_pct=max(1.0, _safe_float(data.get("max_position_pct"), 10.0)),
        max_sector_pct=max(1.0, _safe_float(data.get("max_sector_pct"), 25.0)),
        max_positions=max(1, int(_safe_float(data.get("max_positions"), 15))),
        min_cash_pct=min(95.0, max(0.0, _safe_float(data.get("min_cash_pct"), 15.0))),
        max_pair_correlation=min(0.99, max(0.0, _safe_float(data.get("max_pair_correlation"), 0.85))),
        annual_risk_budget_pct=max(1.0, _safe_float(data.get("annual_risk_budget_pct"), 18.0)),
        var_confidence=min(0.999, max(0.80, _safe_float(data.get("var_confidence"), 0.95))),
    )


def save_settings(limits: PortfolioLimits) -> None:
    try:
        from autonomi_core.configuration.registry import update
        update({"portfolio.optimizer": asdict(limits)}, reason="Kompatibilitet: Portfolio Optimizer", actor="LEGACY_ADAPTER", compatibility=True)
    except Exception:
        pass
    _atomic_write(SETTINGS_PATH, asdict(limits))


def normalise_positions(portfolio: Mapping[str, Any]) -> Tuple[List[Dict[str, Any]], float, float]:
    positions_obj = (portfolio or {}).get("positions") or {}
    items = positions_obj.items() if isinstance(positions_obj, Mapping) else []
    rows: List[Dict[str, Any]] = []
    invested = 0.0
    for ticker, raw in items:
        pos = dict(raw or {})
        shares = _safe_float(pos.get("shares", pos.get("units", pos.get("quantity"))), 0.0)
        price = _safe_float(pos.get("last_price", pos.get("avg_price", pos.get("average_price", pos.get("entry_price")))), 0.0)
        value = max(0.0, shares * price)
        if not ticker or value <= 0:
            continue
        invested += value
        rows.append({
            "ticker": str(ticker).upper(),
            "shares": shares,
            "last_price": price,
            "value": value,
            "sector": str(pos.get("sector") or "Ukjent"),
            "industry": str(pos.get("industry") or ""),
            "currency": str(pos.get("currency") or ""),
            "country": str(pos.get("country") or ""),
            "stop_loss": _safe_float(pos.get("stop_loss"), 0.0),
            "initial_risk_amount": _safe_float(pos.get("initial_risk_amount"), 0.0),
        })
    cash = max(0.0, _safe_float((portfolio or {}).get("cash"), 0.0))
    total = cash + invested
    for row in rows:
        row["weight_pct"] = row["value"] / total * 100.0 if total else 0.0
    return rows, cash, total


def position_size(
    capital: float,
    price: float,
    method: str,
    fixed_amount: float = 0.0,
    portfolio_pct: float = 5.0,
    risk_pct: float = 1.0,
    stop_distance_pct: float = 8.0,
    win_rate: float = 0.55,
    payoff_ratio: float = 1.5,
    max_amount: float = 0.0,
) -> Dict[str, float]:
    capital = max(0.0, _safe_float(capital))
    price = max(0.0, _safe_float(price))
    method_key = str(method or "").strip().lower()
    if method_key == "fast beløp":
        amount = max(0.0, fixed_amount)
    elif method_key == "risikobasert":
        risk_cash = capital * max(0.0, risk_pct) / 100.0
        amount = risk_cash / max(0.0001, stop_distance_pct / 100.0)
    elif method_key == "kelly criterion":
        b = max(0.0001, payoff_ratio)
        p = min(0.99, max(0.01, win_rate))
        kelly = max(0.0, (b * p - (1.0 - p)) / b)
        amount = capital * min(kelly * 0.5, 0.25)  # half-Kelly, hard capped at 25 %
    else:
        amount = capital * max(0.0, portfolio_pct) / 100.0
    if max_amount > 0:
        amount = min(amount, max_amount)
    amount = min(amount, capital)
    shares = amount / price if price > 0 else 0.0
    return {"amount": amount, "shares": shares, "portfolio_pct": amount / capital * 100.0 if capital else 0.0}


def _returns_frame(price_history: Any, tickers: Sequence[str]):
    if pd is None or price_history is None:
        return None
    try:
        frame = pd.DataFrame(price_history).copy()
    except Exception:
        return None
    if frame.empty:
        return None
    cols = [t for t in tickers if t in frame.columns]
    if not cols:
        return None
    frame = frame[cols].apply(pd.to_numeric, errors="coerce").ffill().dropna(how="all")
    returns = frame.pct_change().replace([float("inf"), float("-inf")], float("nan")).dropna(how="all")
    return returns if not returns.empty else None


def risk_metrics(rows: Sequence[Mapping[str, Any]], cash: float, total: float, price_history: Any, confidence: float = 0.95) -> Dict[str, Any]:
    weights = {str(r["ticker"]): _safe_float(r.get("value")) / total for r in rows if total > 0}
    hhi = sum(w * w for w in weights.values())
    effective_positions = 1.0 / hhi if hhi > 0 else 0.0
    diversification = max(0.0, min(100.0, (1.0 - hhi) * 100.0))
    returns = _returns_frame(price_history, list(weights))
    result: Dict[str, Any] = {
        "hhi": hhi,
        "effective_positions": effective_positions,
        "diversification_score": diversification,
        "cash_pct": cash / total * 100.0 if total else 0.0,
        "portfolio_volatility_pct": None,
        "daily_var_amount": None,
        "daily_cvar_amount": None,
        "annual_var_amount": None,
        "correlation": None,
        "asset_volatility_pct": {},
    }
    if returns is None or np is None or pd is None:
        return result
    returns = returns.dropna(axis=1, how="all")
    if returns.empty:
        return result
    active = [c for c in returns.columns if c in weights]
    if not active:
        return result
    returns = returns[active].dropna(how="any")
    if len(returns) < 10:
        return result
    w = np.array([weights[c] for c in active], dtype=float)
    covariance = returns.cov().values * 252.0
    annual_vol = float(math.sqrt(max(0.0, float(w.T @ covariance @ w))))
    portfolio_daily = returns.values @ w
    alpha = max(0.001, 1.0 - confidence)
    q = float(np.quantile(portfolio_daily, alpha))
    tail = portfolio_daily[portfolio_daily <= q]
    cvar = float(tail.mean()) if len(tail) else q
    result.update({
        "portfolio_volatility_pct": annual_vol * 100.0,
        "daily_var_amount": max(0.0, -q * total),
        "daily_cvar_amount": max(0.0, -cvar * total),
        "annual_var_amount": max(0.0, -q * math.sqrt(252.0) * total),
        "correlation": returns.corr().round(3),
        "asset_volatility_pct": {c: float(returns[c].std() * math.sqrt(252.0) * 100.0) for c in active},
    })
    return result


def constraint_violations(rows: Sequence[Mapping[str, Any]], cash: float, total: float, limits: PortfolioLimits, metrics: Mapping[str, Any]) -> List[Dict[str, Any]]:
    violations: List[Dict[str, Any]] = []
    for row in rows:
        weight = _safe_float(row.get("weight_pct"))
        if weight > limits.max_position_pct + 1e-9:
            violations.append({"type": "POSITION", "name": row.get("ticker"), "actual": weight, "limit": limits.max_position_pct, "severity": "HIGH"})
    sectors: Dict[str, float] = {}
    for row in rows:
        sectors[str(row.get("sector") or "Ukjent")] = sectors.get(str(row.get("sector") or "Ukjent"), 0.0) + _safe_float(row.get("weight_pct"))
    for sector, weight in sectors.items():
        if weight > limits.max_sector_pct + 1e-9:
            violations.append({"type": "SECTOR", "name": sector, "actual": weight, "limit": limits.max_sector_pct, "severity": "HIGH"})
    cash_pct = cash / total * 100.0 if total else 0.0
    if cash_pct + 1e-9 < limits.min_cash_pct:
        violations.append({"type": "CASH", "name": "Kontantandel", "actual": cash_pct, "limit": limits.min_cash_pct, "severity": "MEDIUM"})
    if len(rows) > limits.max_positions:
        violations.append({"type": "COUNT", "name": "Åpne posisjoner", "actual": float(len(rows)), "limit": float(limits.max_positions), "severity": "MEDIUM"})
    vol = metrics.get("portfolio_volatility_pct")
    if vol is not None and _safe_float(vol) > limits.annual_risk_budget_pct:
        violations.append({"type": "VOLATILITY", "name": "Årlig porteføljevolatilitet", "actual": _safe_float(vol), "limit": limits.annual_risk_budget_pct, "severity": "HIGH"})
    corr = metrics.get("correlation")
    if pd is not None and isinstance(corr, pd.DataFrame):
        for i, a in enumerate(corr.columns):
            for b in corr.columns[i + 1:]:
                val = _safe_float(corr.loc[a, b], 0.0)
                if val > limits.max_pair_correlation:
                    violations.append({"type": "CORRELATION", "name": f"{a} / {b}", "actual": val, "limit": limits.max_pair_correlation, "severity": "MEDIUM"})
    return violations


def rebalance_proposals(rows: Sequence[Mapping[str, Any]], cash: float, total: float, limits: PortfolioLimits) -> List[Dict[str, Any]]:
    proposals: List[Dict[str, Any]] = []
    target_invested_pct = max(0.0, 100.0 - limits.min_cash_pct)
    n = max(1, len(rows))
    equal_target = min(limits.max_position_pct, target_invested_pct / n)
    for row in rows:
        current = _safe_float(row.get("weight_pct"))
        target = min(equal_target, limits.max_position_pct)
        # Do not recommend increasing positions automatically; suggestions are informative.
        delta = target - current
        if current > limits.max_position_pct:
            target = limits.max_position_pct
            delta = target - current
        if abs(delta) >= 0.5:
            amount = delta / 100.0 * total
            proposals.append({
                "ticker": row.get("ticker"),
                "action": "REDUSER" if amount < 0 else "VURDER ØKNING",
                "current_pct": current,
                "target_pct": target,
                "amount": abs(amount),
                "reason": "Over maksgrense" if current > limits.max_position_pct else "Mot jevnere risikofordeling",
            })
    return sorted(proposals, key=lambda x: (x["action"] != "REDUSER", -x["amount"]))


def scenario_analysis(rows: Sequence[Mapping[str, Any]], total: float, sector_shock_pct: float = -15.0, fx_shock_pct: float = -5.0) -> List[Dict[str, Any]]:
    invested = sum(_safe_float(r.get("value")) for r in rows)
    scenarios = []
    for label, shock in (("Marked -5 %", -5.0), ("Marked -10 %", -10.0), ("Marked -20 %", -20.0)):
        loss = invested * shock / 100.0
        scenarios.append({"scenario": label, "impact_amount": loss, "impact_pct": loss / total * 100.0 if total else 0.0, "estimated_value": total + loss})
    sector_values: Dict[str, float] = {}
    foreign_value = 0.0
    for row in rows:
        value = _safe_float(row.get("value"))
        sector_values[str(row.get("sector") or "Ukjent")] = sector_values.get(str(row.get("sector") or "Ukjent"), 0.0) + value
        if str(row.get("currency") or "").upper() not in {"", "NOK"}:
            foreign_value += value
    if sector_values:
        largest_sector, sector_value = max(sector_values.items(), key=lambda kv: kv[1])
        loss = sector_value * sector_shock_pct / 100.0
        scenarios.append({"scenario": f"{largest_sector} {sector_shock_pct:.0f} %", "impact_amount": loss, "impact_pct": loss / total * 100.0 if total else 0.0, "estimated_value": total + loss})
    if foreign_value > 0:
        loss = foreign_value * fx_shock_pct / 100.0
        scenarios.append({"scenario": f"Valuta {fx_shock_pct:.0f} %", "impact_amount": loss, "impact_pct": loss / total * 100.0 if total else 0.0, "estimated_value": total + loss})
    return scenarios


def explain_portfolio(rows: Sequence[Mapping[str, Any]], cash: float, total: float, limits: PortfolioLimits, metrics: Mapping[str, Any], violations: Sequence[Mapping[str, Any]]) -> List[str]:
    messages: List[str] = []
    cash_pct = cash / total * 100.0 if total else 0.0
    if cash_pct < limits.min_cash_pct:
        messages.append(f"Kontantandelen er {cash_pct:.1f} %, under minimum {limits.min_cash_pct:.1f} %.")
    position_hits = [v for v in violations if v.get("type") == "POSITION"]
    if position_hits:
        names = ", ".join(str(v.get("name")) for v in position_hits[:3])
        messages.append(f"Posisjonsgrensen overskrides av {names}.")
    sector_hits = [v for v in violations if v.get("type") == "SECTOR"]
    if sector_hits:
        top = sector_hits[0]
        messages.append(f"Porteføljen er overeksponert mot {top.get('name')} ({_safe_float(top.get('actual')):.1f} % mot mål {_safe_float(top.get('limit')):.1f} %).")
    corr_hits = [v for v in violations if v.get("type") == "CORRELATION"]
    if corr_hits:
        messages.append(f"{len(corr_hits)} par har korrelasjon over {limits.max_pair_correlation:.2f}; høy samvariasjon kan redusere diversifiseringen.")
    vol = metrics.get("portfolio_volatility_pct")
    if vol is not None:
        messages.append(f"Estimert årlig volatilitet er {_safe_float(vol):.1f} %, mot risikobudsjett {limits.annual_risk_budget_pct:.1f} %.")
    messages.append(f"Diversifiseringsscore er {_safe_float(metrics.get('diversification_score')):.0f}/100 og effektivt antall posisjoner er {_safe_float(metrics.get('effective_positions')):.1f}.")
    if not violations:
        messages.insert(0, "Ingen definerte porteføljegrenser er brutt i denne analysen.")
    return messages


def build_report(portfolio: Mapping[str, Any], price_history: Any, limits: Optional[PortfolioLimits] = None) -> Dict[str, Any]:
    limits = limits or load_settings()
    rows, cash, total = normalise_positions(portfolio)
    metrics = risk_metrics(rows, cash, total, price_history, limits.var_confidence)
    violations = constraint_violations(rows, cash, total, limits, metrics)
    report = {
        "ok": True,
        "created_at": _now_iso(),
        "limits": asdict(limits),
        "summary": {"cash": cash, "invested": total - cash, "total": total, "positions": len(rows)},
        "positions": rows,
        "risk": {k: v for k, v in metrics.items() if k != "correlation"},
        "correlation": metrics["correlation"].to_dict() if pd is not None and isinstance(metrics.get("correlation"), pd.DataFrame) else None,
        "violations": violations,
        "rebalance": rebalance_proposals(rows, cash, total, limits),
        "scenarios": scenario_analysis(rows, total),
        "explanation": explain_portfolio(rows, cash, total, limits, metrics, violations),
        "read_only": True,
    }
    _atomic_write(LATEST_REPORT_PATH, report)
    return report


def _fetch_history(tickers: Sequence[str], period: str = "1y"):
    if pd is None or not tickers:
        return None, "Ingen tickere"
    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:
        return None, f"yfinance mangler: {exc}"
    frames = {}
    errors = []
    for ticker in tickers:
        candidates = [ticker]
        if "." not in ticker:
            candidates.extend([f"{ticker}.OL", f"{ticker}.ST", f"{ticker}.CO"])
        found = False
        for symbol in candidates:
            try:
                hist = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=True, prepost=False)
                if hist is not None and not hist.empty and "Close" in hist:
                    frames[ticker] = hist["Close"].rename(ticker)
                    found = True
                    break
            except Exception:
                continue
        if not found:
            errors.append(ticker)
    if not frames:
        return None, "Fant ingen historiske priser"
    return pd.concat(frames.values(), axis=1).sort_index(), ("Mangler: " + ", ".join(errors)) if errors else ""


def render_portfolio_optimizer() -> None:
    import streamlit as st
    from paper_store import load_portfolio

    st.markdown("#### 🛡️ Risikostyring – Portfolio Optimizer")
    st.caption("Lesebasert kapitalallokering, risikoanalyse og rebalanseringsforslag. Ingen handler utføres, og Paper Trading endres ikke.")
    limits = load_settings()
    with st.expander("Porteføljegrenser", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            max_pos = st.number_input("Maks per aksje (%)", 1.0, 100.0, float(limits.max_position_pct), 0.5, key="po_max_pos_v18682")
            min_cash = st.number_input("Minimum kontantandel (%)", 0.0, 95.0, float(limits.min_cash_pct), 0.5, key="po_min_cash_v18682")
        with c2:
            max_sector = st.number_input("Maks per sektor (%)", 1.0, 100.0, float(limits.max_sector_pct), 0.5, key="po_max_sector_v18682")
            max_count = st.number_input("Maks åpne posisjoner", 1, 100, int(limits.max_positions), 1, key="po_max_count_v18682")
        with c3:
            max_corr = st.number_input("Maks par-korrelasjon", 0.0, 0.99, float(limits.max_pair_correlation), 0.01, key="po_max_corr_v18682")
            risk_budget = st.number_input("Årlig risikobudsjett (%)", 1.0, 100.0, float(limits.annual_risk_budget_pct), 0.5, key="po_risk_budget_v18682")
        limits = PortfolioLimits(float(max_pos), float(max_sector), int(max_count), float(min_cash), float(max_corr), float(risk_budget), limits.var_confidence)
        if st.button("Lagre grenser", key="po_save_limits_v18682"):
            save_settings(limits)
            st.success("Porteføljegrenser lagret i runtime-data.")

    portfolio = load_portfolio()
    rows, cash, total = normalise_positions(portfolio)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Porteføljeverdi", f"{total:,.0f}")
    k2.metric("Investert", f"{total-cash:,.0f}")
    k3.metric("Kontantandel", f"{(cash/total*100 if total else 0):.1f} %")
    k4.metric("Posisjoner", len(rows))
    if not rows:
        st.info("Ingen åpne Paper Trading-posisjoner å analysere.")
        return

    period = st.selectbox("Historikk for risiko/korrelasjon", ["6mo", "1y", "2y", "5y"], index=1, key="po_period_v18682")
    if st.button("Kjør porteføljeanalyse", type="primary", key="po_run_v18682"):
        with st.spinner("Henter historikk og beregner risiko ..."):
            history, warning = _fetch_history([r["ticker"] for r in rows], period)
            report = build_report(portfolio, history, limits)
            st.session_state["po_report_v18682"] = report
            st.session_state["po_history_warning_v18682"] = warning
    report = st.session_state.get("po_report_v18682")
    if not report:
        st.info("Kjør analysen for å beregne korrelasjon, VaR, volatilitet, scenarioer og forslag.")
    else:
        warning = st.session_state.get("po_history_warning_v18682")
        if warning:
            st.warning(warning)
        risk = report.get("risk") or {}
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Diversifisering", f"{_safe_float(risk.get('diversification_score')):.0f}/100")
        c2.metric("Volatilitet", "–" if risk.get("portfolio_volatility_pct") is None else f"{_safe_float(risk.get('portfolio_volatility_pct')):.1f} %")
        c3.metric("Daglig VaR", "–" if risk.get("daily_var_amount") is None else f"{_safe_float(risk.get('daily_var_amount')):,.0f}")
        c4.metric("Daglig CVaR", "–" if risk.get("daily_cvar_amount") is None else f"{_safe_float(risk.get('daily_cvar_amount')):,.0f}")

        tabs = st.tabs(["Eksponering", "Korrelasjon", "Risiko og grenser", "Rebalansering", "Scenario", "Explain Portfolio", "Position Sizing"])
        with tabs[0]:
            display = [{"Ticker": r["ticker"], "Sektor": r["sector"], "Verdi": round(r["value"], 2), "Vekt %": round(r["weight_pct"], 2), "Valuta": r["currency"]} for r in report.get("positions", [])]
            st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)
            sector_df = pd.DataFrame(display).groupby("Sektor", as_index=False)["Vekt %"].sum().sort_values("Vekt %", ascending=False)
            st.bar_chart(sector_df.set_index("Sektor"))
        with tabs[1]:
            corr = report.get("correlation")
            if corr:
                corr_df = pd.DataFrame(corr)
                st.dataframe(corr_df.style.background_gradient(cmap="RdYlGn_r", vmin=-1, vmax=1).format("{:.2f}"), use_container_width=True)
            else:
                st.info("Ikke nok felles historikk til korrelasjonsmatrise.")
        with tabs[2]:
            violations = report.get("violations") or []
            if violations:
                st.error(f"{len(violations)} regelbrudd eller risikoadvarsler funnet.")
                st.dataframe(pd.DataFrame(violations), use_container_width=True, hide_index=True)
            else:
                st.success("Ingen definerte grenser er brutt.")
        with tabs[3]:
            proposals = report.get("rebalance") or []
            st.caption("Kun forslag. Ingen kjøp eller salg blir utført.")
            if proposals:
                st.dataframe(pd.DataFrame(proposals), use_container_width=True, hide_index=True)
            else:
                st.success("Ingen vesentlige rebalanseringsforslag med dagens grenser.")
        with tabs[4]:
            st.dataframe(pd.DataFrame(report.get("scenarios") or []), use_container_width=True, hide_index=True)
        with tabs[5]:
            for text in report.get("explanation") or []:
                st.write("•", text)
            st.caption("Forklaringen er regelbasert og passiv; den endrer ikke porteføljen.")
        with tabs[6]:
            method = st.selectbox("Metode", ["Fast prosent", "Fast beløp", "Risikobasert", "Kelly Criterion"], key="po_size_method_v18682")
            a, b, c = st.columns(3)
            with a:
                price = st.number_input("Pris", min_value=0.01, value=100.0, step=1.0, key="po_size_price_v18682")
                pct = st.number_input("Porteføljeandel (%)", 0.1, 100.0, 5.0, 0.5, key="po_size_pct_v18682")
            with b:
                fixed = st.number_input("Fast beløp", 0.0, value=10000.0, step=1000.0, key="po_size_fixed_v18682")
                risk_pct = st.number_input("Risiko av kapital (%)", 0.1, 20.0, 1.0, 0.1, key="po_size_risk_v18682")
            with c:
                stop_distance = st.number_input("Stop-avstand (%)", 0.1, 100.0, 8.0, 0.5, key="po_size_stop_v18682")
                max_amount = st.number_input("Maks beløp (0 = ingen)", 0.0, value=0.0, step=1000.0, key="po_size_max_v18682")
            size = position_size(total, price, method, fixed, pct, risk_pct, stop_distance, max_amount=max_amount)
            st.metric("Foreslått beløp", f"{size['amount']:,.0f}")
            st.write(f"Antall: **{size['shares']:.4f}** · Porteføljeandel: **{size['portfolio_pct']:.2f} %**")

        payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
        st.download_button("Last ned rapport (JSON)", payload, file_name="portfolio_optimizer_report.json", mime="application/json", key="po_export_json_v18682")
