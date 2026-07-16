from __future__ import annotations

import json
import math
import uuid
from copy import deepcopy
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

from ai_learning_foundation import build_trade_outcomes
from storage_architecture import runtime_data_path

STORE_PATH = runtime_data_path("ai_strategy_optimization_v18684.json")
MIN_OBSERVATIONS = 20


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _load_store() -> dict:
    try:
        data = json.loads(Path(STORE_PATH).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("proposals", [])
            data.setdefault("audit", [])
            return data
    except Exception:
        pass
    return {"version": "v18.6.84", "proposals": [], "audit": []}


def _save_store(data: dict) -> None:
    path = Path(STORE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _metrics(returns: Iterable[float]) -> dict:
    vals = [float(x) for x in returns]
    if not vals:
        return {
            "observations": 0,
            "hit_rate_pct": 0.0,
            "avg_return_pct": 0.0,
            "median_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "profit_factor": 0.0,
            "sharpe_proxy": 0.0,
        }
    equity = 100.0
    peak = equity
    worst = 0.0
    for value in vals:
        equity *= 1.0 + value / 100.0
        peak = max(peak, equity)
        if peak:
            worst = min(worst, (equity - peak) / peak * 100.0)
    gains = sum(v for v in vals if v > 0)
    losses = abs(sum(v for v in vals if v < 0))
    avg = mean(vals)
    variance = mean([(v - avg) ** 2 for v in vals]) if len(vals) > 1 else 0.0
    return {
        "observations": len(vals),
        "hit_rate_pct": round(sum(v > 0 for v in vals) / len(vals) * 100.0, 1),
        "avg_return_pct": round(avg, 3),
        "median_return_pct": round(median(vals), 3),
        "max_drawdown_pct": round(worst, 3),
        "profit_factor": round(gains / losses, 3) if losses else round(gains, 3),
        "sharpe_proxy": round(avg / math.sqrt(variance), 3) if variance > 0 else 0.0,
    }


def _confidence_bucket(value: float) -> str:
    c = int(value)
    if c < 60:
        return "50-59"
    if c < 70:
        return "60-69"
    if c < 80:
        return "70-79"
    if c < 90:
        return "80-89"
    return "90+"


def _recommend_confidence(outcomes: list[dict]) -> dict | None:
    candidates = []
    for threshold in (60, 65, 70, 73, 75, 80, 85):
        rows = [x for x in outcomes if _f(x.get("confidence")) >= threshold]
        if len(rows) < max(8, MIN_OBSERVATIONS // 2):
            continue
        m = _metrics(_f(x.get("return_pct")) for x in rows)
        candidates.append((threshold, m))
    if not candidates:
        return None
    threshold, best = max(candidates, key=lambda x: (x[1]["profit_factor"], x[1]["avg_return_pct"], x[1]["observations"]))
    return {
        "parameter": "minimum_confidence",
        "current_value": 73,
        "proposed_value": threshold,
        "rationale": f"Historiske handler med confidence >= {threshold} ga best balansert profit factor og snittavkastning i tilgjengelig datasett.",
        "simulation": best,
    }


def _recommend_exit(outcomes: list[dict]) -> dict | None:
    groups: dict[str, list[float]] = {}
    for row in outcomes:
        key = str(row.get("exit_rule") or row.get("exit_reason") or "Ukjent")
        groups.setdefault(key, []).append(_f(row.get("return_pct")))
    viable = [(name, _metrics(vals)) for name, vals in groups.items() if len(vals) >= 5]
    if not viable:
        return None
    name, best = max(viable, key=lambda x: (x[1]["avg_return_pct"], x[1]["profit_factor"]))
    return {
        "parameter": "preferred_exit_observation",
        "current_value": "mixed",
        "proposed_value": name,
        "rationale": f"Exit-typen {name} har best historisk snittavkastning blant exit-typer med minst fem observasjoner. Dette er kun et analyseforslag.",
        "simulation": best,
    }


def _recommend_signal_weights(outcomes: list[dict]) -> dict | None:
    groups: dict[str, list[float]] = {}
    for row in outcomes:
        key = str(row.get("signal") or "Ukjent")
        groups.setdefault(key, []).append(_f(row.get("return_pct")))
    viable = [(name, _metrics(vals)) for name, vals in groups.items() if len(vals) >= 5]
    if len(viable) < 2:
        return None
    viable.sort(key=lambda x: (x[1]["avg_return_pct"], x[1]["profit_factor"]), reverse=True)
    best_name, best = viable[0]
    weak_name, weak = viable[-1]
    return {
        "parameter": "signal_weight_review",
        "current_value": {best_name: 1.0, weak_name: 1.0},
        "proposed_value": {best_name: 1.10, weak_name: 0.90},
        "rationale": f"Vurder moderat oppvekt av {best_name} og nedvekt av {weak_name}. Forslaget bygger på relativ historisk prestasjon og aktiveres ikke automatisk.",
        "simulation": {"best_signal": best, "weak_signal": weak},
    }


def build_optimization_analysis(portfolio: dict | None = None) -> dict:
    outcomes = build_trade_outcomes(portfolio)
    baseline = _metrics(_f(x.get("return_pct")) for x in outcomes)
    proposals = [x for x in (
        _recommend_confidence(outcomes),
        _recommend_exit(outcomes),
        _recommend_signal_weights(outcomes),
    ) if x]
    sufficient = len(outcomes) >= MIN_OBSERVATIONS
    recommendation_confidence = min(95.0, round(35.0 + len(outcomes) * 1.5, 1)) if sufficient else round(len(outcomes) / MIN_OBSERVATIONS * 50.0, 1)
    return {
        "version": "v18.6.84",
        "generated_at": _now(),
        "mode": {
            "data_collection": "ON",
            "analysis": "ON",
            "generate_proposals": "ON",
            "simulate_proposals": "ON",
            "automatic_activation": "OFF",
            "automatic_rule_changes": "OFF",
            "automatic_signal_weight_changes": "OFF",
        },
        "minimum_observations": MIN_OBSERVATIONS,
        "data_sufficient": sufficient,
        "recommendation_confidence_pct": recommendation_confidence,
        "baseline": baseline,
        "proposals": proposals if sufficient else [],
        "notice": "Forslag er rådgivende. Godkjenning registrerer beslutningen, men endrer ikke aktiv handelsmotor automatisk.",
    }


def save_analysis_as_proposals(analysis: dict) -> list[dict]:
    store = _load_store()
    existing_open = {(p.get("parameter"), json.dumps(p.get("proposed_value"), sort_keys=True, ensure_ascii=False)) for p in store["proposals"] if p.get("status") in {"OPEN", "APPROVED"}}
    created = []
    for raw in analysis.get("proposals") or []:
        key = (raw.get("parameter"), json.dumps(raw.get("proposed_value"), sort_keys=True, ensure_ascii=False))
        if key in existing_open:
            continue
        proposal = {
            "proposal_id": uuid.uuid4().hex[:12],
            "version": 1,
            "created_at": _now(),
            "updated_at": _now(),
            "status": "OPEN",
            "recommendation_confidence_pct": analysis.get("recommendation_confidence_pct", 0.0),
            **deepcopy(raw),
        }
        store["proposals"].append(proposal)
        store["audit"].append({"time": _now(), "action": "CREATE", "proposal_id": proposal["proposal_id"], "status": "OPEN"})
        created.append(proposal)
    _save_store(store)
    return created


def list_proposals() -> list[dict]:
    return list(reversed(_load_store().get("proposals") or []))


def decide_proposal(proposal_id: str, decision: str, note: str = "") -> dict:
    decision = decision.upper().strip()
    if decision not in {"APPROVED", "REJECTED", "ROLLED_BACK"}:
        raise ValueError("Ugyldig beslutning")
    store = _load_store()
    for proposal in store.get("proposals") or []:
        if proposal.get("proposal_id") != proposal_id:
            continue
        previous = proposal.get("status")
        proposal["status"] = decision
        proposal["updated_at"] = _now()
        proposal["decision_note"] = note
        proposal["activation_effect"] = "NONE"  # explicit safety boundary
        store["audit"].append({
            "time": _now(), "action": decision, "proposal_id": proposal_id,
            "previous_status": previous, "note": note,
            "activation_effect": "NONE",
        })
        _save_store(store)
        return proposal
    raise KeyError(proposal_id)


def optimization_audit() -> list[dict]:
    return list(reversed(_load_store().get("audit") or []))


def render_ai_strategy_optimization_tab() -> None:
    import streamlit as st
    try:
        import pandas as pd
    except Exception:
        pd = None

    st.markdown("#### AI Assisted Strategy Optimization")
    st.caption("Rådgivende analyse og simulering. Ingen regel, terskel eller signalvekt endres automatisk.")
    analysis = build_optimization_analysis()

    with st.expander("Sikkerhetsgrenser", expanded=False):
        st.json(analysis["mode"])

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    base = analysis["baseline"]
    c1.metric("Observasjoner", base["observations"])
    c2.metric("Datagrunnlag", "OK" if analysis["data_sufficient"] else "For lite")
    c3.metric("Forslags-confidence", f"{analysis['recommendation_confidence_pct']:.1f}%")
    c4.metric("Hit rate", f"{base['hit_rate_pct']:.1f}%")
    c5.metric("Profit factor", f"{base['profit_factor']:.2f}")
    c6.metric("Max DD", f"{base['max_drawdown_pct']:.2f}%")

    if not analysis["data_sufficient"]:
        st.warning(f"Minst {analysis['minimum_observations']} avsluttede handler kreves før optimaliseringsforslag opprettes. Nå: {base['observations']}.")
    else:
        st.success("Datagrunnlaget er stort nok for rådgivende forslag. Resultatene må fortsatt vurderes manuelt.")

    tabs = st.tabs(["Nye forslag", "Forslagsarkiv", "Hva hvis?", "Audit / rollback"])
    with tabs[0]:
        rows = analysis.get("proposals") or []
        if rows:
            display = []
            for row in rows:
                display.append({
                    "parameter": row.get("parameter"),
                    "nå": row.get("current_value"),
                    "forslag": row.get("proposed_value"),
                    "begrunnelse": row.get("rationale"),
                })
            st.dataframe(pd.DataFrame(display) if pd is not None else display, use_container_width=True, hide_index=True)
            if st.button("Lagre nye forslag til vurdering", key="save_strategy_proposals_v18684"):
                created = save_analysis_as_proposals(analysis)
                st.success(f"{len(created)} nye forslag lagret.")
                st.rerun()
        else:
            st.info("Ingen forslag tilgjengelig ennå.")

    with tabs[1]:
        proposals = list_proposals()
        if not proposals:
            st.info("Ingen lagrede forslag.")
        else:
            for proposal in proposals:
                title = f"{proposal['proposal_id']} · {proposal.get('parameter')} · {proposal.get('status')}"
                with st.expander(title, expanded=False):
                    st.json(proposal)
                    note = st.text_input("Beslutningsnotat", key=f"note_{proposal['proposal_id']}")
                    a, b, c = st.columns(3)
                    if a.button("Godkjenn", key=f"approve_{proposal['proposal_id']}"):
                        decide_proposal(proposal["proposal_id"], "APPROVED", note)
                        st.rerun()
                    if b.button("Avvis", key=f"reject_{proposal['proposal_id']}"):
                        decide_proposal(proposal["proposal_id"], "REJECTED", note)
                        st.rerun()
                    if c.button("Rollback markering", key=f"rollback_{proposal['proposal_id']}"):
                        decide_proposal(proposal["proposal_id"], "ROLLED_BACK", note)
                        st.rerun()
            st.info("Godkjenning er kun en auditert beslutning. Aktiv handelskonfigurasjon endres ikke i v18.6.84.")

    with tabs[2]:
        for proposal in analysis.get("proposals") or []:
            st.markdown(f"##### {proposal.get('parameter')}")
            st.write(proposal.get("rationale"))
            st.json(proposal.get("simulation") or {})
        if not analysis.get("proposals"):
            st.info("Ingen simuleringer kan vises før datagrunnlaget er tilstrekkelig.")

    with tabs[3]:
        audit = optimization_audit()
        if audit:
            st.dataframe(pd.DataFrame(audit) if pd is not None else audit, use_container_width=True, hide_index=True)
        else:
            st.info("Ingen audit-hendelser ennå.")

    st.download_button(
        "Last ned Strategy Optimization JSON",
        json.dumps({"analysis": analysis, "proposals": list_proposals(), "audit": optimization_audit()}, ensure_ascii=False, indent=2),
        "AI_STRATEGY_OPTIMIZATION_v18_6_84.json",
        "application/json",
    )
