"""Controlled Parameter Learning v18.6.89.

Fast Learning / Safe Promotion for the theoretical Autonomous Learning Portfolio.
The module may propose and test bounded parameter changes, apply immediate
risk protection, and promote or roll back parameter sets. It never connects to
a broker and never changes Paper Trading or live-trading settings.
"""
from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from storage_architecture import runtime_data_path
from autonomous_portfolio import (
    AutonomousParameters, load_parameters, save_parameters, load_portfolio,
    calculate_performance, TRADES_PATH, DECISIONS_PATH, NOTIFICATIONS_PATH,
)

VERSION = "v18.6.89"
ROOT = runtime_data_path("controlled_learning")
STATE_PATH = ROOT / "state.json"
HYPOTHESES_PATH = ROOT / "hypotheses.json"
EXPERIMENTS_PATH = ROOT / "experiments.json"
VERSIONS_PATH = ROOT / "parameter_versions.json"
AUDIT_PATH = ROOT / "audit.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _read(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _audit(event: str, payload: Mapping[str, Any]) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"timestamp": _now(), "version": VERSION, "event": event, "payload": dict(payload)}, ensure_ascii=False, default=str) + "\n")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def default_state() -> dict[str, Any]:
    return {
        "version": VERSION,
        "enabled": False,
        "mode": "FAST_LEARNING_SAFE_PROMOTION",
        "auto_risk_protection": True,
        "auto_start_challengers": False,
        "auto_promote": False,
        "auto_rollback": True,
        "warning_min_closed_trades": 10,
        "hypothesis_min_closed_trades": 15,
        "challenger_min_closed_trades": 25,
        "trial_promotion_min_closed_trades": 35,
        "full_promotion_min_closed_trades": 75,
        "minimum_trial_trades": 20,
        "maximum_parameter_step_pct": 15.0,
        "risk_reduction_factor": 0.5,
        "rollback_drawdown_delta_pct": 3.0,
        "cooldown_days": 7,
        "last_evaluation_at": None,
        "last_action": None,
    }


def load_state() -> dict[str, Any]:
    state = default_state()
    raw = _read(STATE_PATH, {})
    if isinstance(raw, dict):
        state.update(raw)
    return state


def save_state(state: Mapping[str, Any]) -> dict[str, Any]:
    merged = default_state(); merged.update(dict(state)); _write(STATE_PATH, merged)
    _audit("LEARNING_SETTINGS_SAVED", merged)
    return merged


def _closed_trades() -> list[dict[str, Any]]:
    trades = _read(TRADES_PATH, [])
    return [t for t in trades if isinstance(t, dict) and t.get("action") == "SELL"] if isinstance(trades, list) else []


def _stats(trades: list[dict[str, Any]]) -> dict[str, float]:
    pnl = [_f(t.get("pnl")) for t in trades]
    winners = [x for x in pnl if x > 0]
    losers = [x for x in pnl if x < 0]
    gross_profit, gross_loss = sum(winners), abs(sum(losers))
    return {
        "trades": len(trades),
        "win_rate_pct": len(winners) / len(pnl) * 100 if pnl else 0.0,
        "expectancy": sum(pnl) / len(pnl) if pnl else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else (999.0 if gross_profit else 0.0),
        "average_win": sum(winners) / len(winners) if winners else 0.0,
        "average_loss": sum(losers) / len(losers) if losers else 0.0,
    }


def _notify(title: str, message: str, payload: Mapping[str, Any]) -> None:
    rows = _read(NOTIFICATIONS_PATH, [])
    if not isinstance(rows, list): rows = []
    rows.insert(0, {"timestamp": _now(), "kind": "LEARNING", "title": title, "message": message, "payload": dict(payload), "delivery": "LOCAL_QUEUE"})
    _write(NOTIFICATIONS_PATH, rows[:1000])
    try:
        from notification_service import send_pushover_notification
        send_pushover_notification(title, message)
        rows[0]["delivery"] = "PUSHOVER_ATTEMPTED"; _write(NOTIFICATIONS_PATH, rows[:1000])
    except Exception:
        pass


def ensure_champion_version() -> dict[str, Any]:
    versions = _read(VERSIONS_PATH, [])
    if not isinstance(versions, list): versions = []
    active = next((v for v in versions if v.get("status") == "CHAMPION"), None)
    if active: return active
    active = {"version_id": "PV-" + uuid.uuid4().hex[:10], "created_at": _now(), "status": "CHAMPION", "parameters": asdict(load_parameters()), "reason": "Initial champion", "baseline_performance": calculate_performance()}
    versions.insert(0, active); _write(VERSIONS_PATH, versions); _audit("CHAMPION_INITIALIZED", active)
    return active


def generate_hypotheses() -> list[dict[str, Any]]:
    state, params, trades = load_state(), load_parameters(), _closed_trades()
    if len(trades) < int(state["hypothesis_min_closed_trades"]): return []
    existing = _read(HYPOTHESES_PATH, [])
    if not isinstance(existing, list): existing = []
    stats = _stats(trades)
    proposals: list[tuple[str, float, float, str]] = []
    recent = trades[:min(20, len(trades))]
    stop_share = sum(1 for t in recent if "STOP" in str(t.get("reason", "")).upper()) / max(1, len(recent))
    take_share = sum(1 for t in recent if "TAKE PROFIT" in str(t.get("reason", "")).upper()) / max(1, len(recent))
    if stats["expectancy"] < 0 or stats["profit_factor"] < 1.0:
        proposals.append(("minimum_investment_score", params.minimum_investment_score, min(100.0, params.minimum_investment_score + 3.0), "Negativ expectancy eller Profit Factor under 1 tilsier strengere inngang."))
        proposals.append(("maximum_position_pct", params.maximum_position_pct, max(0.5, params.maximum_position_pct * 0.75), "Reduser kapital per handel mens strategien viser svakhet."))
    if stop_share >= 0.40:
        proposals.append(("minimum_data_quality", params.minimum_data_quality, min(100.0, params.minimum_data_quality + 5.0), "Høy andel stop-exits kan indikere svake innganger eller datagrunnlag."))
    if take_share >= 0.35 and stats["profit_factor"] > 1.2:
        proposals.append(("take_profit_pct", params.take_profit_pct, min(300.0, params.take_profit_pct * 1.10), "Mange take-profit-exits og god Profit Factor kan støtte en forsiktig høyere målpris."))
    created = []
    open_keys = {(h.get("parameter"), h.get("status")) for h in existing if h.get("status") in {"NEW", "READY", "TESTING", "TRIAL"}}
    for parameter, before, after, reason in proposals:
        if any(k[0] == parameter for k in open_keys): continue
        h = {"hypothesis_id": "H-" + uuid.uuid4().hex[:10], "created_at": _now(), "status": "NEW", "parameter": parameter, "before": round(before, 6), "after": round(after, 6), "reason": reason, "evidence": stats, "risk_level": "LOW" if parameter in {"minimum_investment_score", "minimum_data_quality", "maximum_position_pct"} else "MEDIUM"}
        existing.insert(0, h); created.append(h); _audit("HYPOTHESIS_CREATED", h)
        _notify("Learning: ny hypotese", f"{parameter}: {before:g} → {after:g}. {reason}", h)
    _write(HYPOTHESES_PATH, existing)
    return created


def start_challenger(hypothesis_id: str) -> dict[str, Any]:
    hypotheses = _read(HYPOTHESES_PATH, [])
    h = next((x for x in hypotheses if x.get("hypothesis_id") == hypothesis_id), None)
    if not h: raise ValueError("Hypotesen finnes ikke.")
    champion = ensure_champion_version()
    params = dict(champion["parameters"]); params[h["parameter"]] = h["after"]
    experiment = {"experiment_id": "E-" + uuid.uuid4().hex[:10], "hypothesis_id": hypothesis_id, "created_at": _now(), "status": "TESTING", "champion_version_id": champion["version_id"], "challenger_parameters": params, "baseline": _stats(_closed_trades()), "trial_trades": [], "minimum_trial_trades": int(load_state()["minimum_trial_trades"]), "conclusion": None}
    experiments = _read(EXPERIMENTS_PATH, []); experiments = experiments if isinstance(experiments, list) else []; experiments.insert(0, experiment); _write(EXPERIMENTS_PATH, experiments)
    h["status"] = "TESTING"; h["experiment_id"] = experiment["experiment_id"]; _write(HYPOTHESES_PATH, hypotheses)
    _audit("CHALLENGER_STARTED", experiment); _notify("Learning: Challenger startet", f"Tester {h['parameter']} {h['before']} → {h['after']}", experiment)
    return experiment


def apply_trial(hypothesis_id: str) -> dict[str, Any]:
    hypotheses = _read(HYPOTHESES_PATH, []); h = next((x for x in hypotheses if x.get("hypothesis_id") == hypothesis_id), None)
    if not h: raise ValueError("Hypotesen finnes ikke.")
    params = load_parameters(); data = asdict(params); data[h["parameter"]] = h["after"]
    previous = asdict(params); save_parameters(AutonomousParameters(**data))
    versions = _read(VERSIONS_PATH, []); versions = versions if isinstance(versions, list) else []
    trial = {"version_id": "PV-" + uuid.uuid4().hex[:10], "created_at": _now(), "status": "TRIAL", "parameters": data, "previous_parameters": previous, "hypothesis_id": hypothesis_id, "baseline_performance": calculate_performance()}
    versions.insert(0, trial); _write(VERSIONS_PATH, versions); h["status"] = "TRIAL"; _write(HYPOTHESES_PATH, hypotheses)
    _audit("TRIAL_PARAMETERS_APPLIED", trial); _notify("Learning: midlertidig endring", f"{h['parameter']}: {h['before']} → {h['after']} i prøvemodus.", trial)
    return trial


def rollback(reason: str = "Manuell rollback") -> dict[str, Any]:
    versions = _read(VERSIONS_PATH, []); versions = versions if isinstance(versions, list) else []
    current = next((v for v in versions if v.get("status") == "TRIAL"), None)
    champion = next((v for v in versions if v.get("status") == "CHAMPION"), None)
    target = (current or {}).get("previous_parameters") or (champion or {}).get("parameters")
    if not target: raise ValueError("Ingen tidligere parameter-versjon tilgjengelig.")
    save_parameters(AutonomousParameters(**target))
    if current: current["status"] = "ROLLED_BACK"; current["rollback_reason"] = reason; current["rolled_back_at"] = _now()
    _write(VERSIONS_PATH, versions); _audit("PARAMETER_ROLLBACK", {"reason": reason, "target": target}); _notify("Learning: rollback", reason, {"target": target})
    return target


def promote_trial() -> dict[str, Any]:
    versions = _read(VERSIONS_PATH, []); versions = versions if isinstance(versions, list) else []
    trial = next((v for v in versions if v.get("status") == "TRIAL"), None)
    if not trial: raise ValueError("Ingen aktiv prøveversjon.")
    old = next((v for v in versions if v.get("status") == "CHAMPION"), None)
    if old: old["status"] = "ARCHIVED_CHAMPION"
    trial["status"] = "CHAMPION"; trial["promoted_at"] = _now(); trial["promotion_performance"] = calculate_performance()
    _write(VERSIONS_PATH, versions); _audit("TRIAL_PROMOTED_TO_CHAMPION", trial); _notify("Learning: ny Champion", f"Parameter-versjon {trial['version_id']} er promotert.", trial)
    return trial


def evaluate_learning() -> dict[str, Any]:
    state = load_state(); perf = calculate_performance(); trades = _closed_trades(); stats = _stats(trades); actions = []
    ensure_champion_version()
    if state.get("enabled"):
        created = generate_hypotheses(); actions += [f"Opprettet {len(created)} hypoteser"] if created else []
        if state.get("auto_risk_protection") and (perf.get("drawdown_pct", 0) >= load_parameters().maximum_drawdown_pct * 0.75 or (len(trades) >= state["warning_min_closed_trades"] and stats["expectancy"] < 0)):
            p = load_parameters(); reduced = max(0.5, p.maximum_position_pct * float(state["risk_reduction_factor"]))
            if reduced < p.maximum_position_pct:
                data = asdict(p); old = p.maximum_position_pct; data["maximum_position_pct"] = reduced; save_parameters(AutonomousParameters(**data))
                action = {"type": "RISK_REDUCTION", "parameter": "maximum_position_pct", "before": old, "after": reduced, "reason": "Drawdown/negativ expectancy trigger"}
                actions.append(action); _audit("AUTOMATIC_RISK_PROTECTION", action); _notify("Learning: risiko redusert", f"Maks posisjon {old:.2f}% → {reduced:.2f}%", action)
    state["last_evaluation_at"] = _now(); state["last_action"] = actions[-1] if actions else "Ingen endring"; _write(STATE_PATH, state)
    result = {"timestamp": _now(), "closed_trades": len(trades), "statistics": stats, "performance": perf, "actions": actions}; _audit("LEARNING_EVALUATED", result)
    return result


def render_controlled_learning() -> None:
    import pandas as pd
    import streamlit as st
    st.markdown("#### 🧪 Controlled Parameter Learning")
    st.caption("Fast Learning / Safe Promotion. Rask risikobeskyttelse, trinnvis testing og varslede endringer. Kun teoretisk autonom portefølje.")
    state = load_state(); trades = _closed_trades(); stats = _stats(trades)
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Læring", "AKTIV" if state["enabled"] else "AV")
    c2.metric("Lukkede handler", len(trades)); c3.metric("Expectancy", f"{stats['expectancy']:,.0f}")
    c4.metric("Profit Factor", f"{stats['profit_factor']:.2f}"); c5.metric("Siste evaluering", str(state.get("last_evaluation_at") or "–")[:16])
    a,b,c = st.columns(3)
    enabled = a.toggle("Aktiver kontrollert læring", value=bool(state["enabled"]), key="cpl_enabled_v18689")
    risk = b.toggle("Automatisk risikobeskyttelse", value=bool(state["auto_risk_protection"]), key="cpl_risk_v18689")
    rollback_on = c.toggle("Automatisk rollback", value=bool(state["auto_rollback"]), key="cpl_rollback_v18689")
    if (enabled, risk, rollback_on) != (state["enabled"], state["auto_risk_protection"], state["auto_rollback"]):
        state.update({"enabled": enabled, "auto_risk_protection": risk, "auto_rollback": rollback_on}); save_state(state)
    with st.expander("Adaptive terskler", expanded=False):
        cols = st.columns(5)
        keys = [("warning_min_closed_trades","Tidlig varsel"),("hypothesis_min_closed_trades","Hypotese"),("challenger_min_closed_trades","Challenger"),("trial_promotion_min_closed_trades","Prøvemodus"),("full_promotion_min_closed_trades","Full Champion")]
        values = {}
        for col,(key,label) in zip(cols,keys): values[key] = int(col.number_input(label, 1, 1000, int(state[key]), 1, key=f"cpl_{key}_v18689"))
        if st.button("Lagre læringsterskler", key="cpl_save_thresholds_v18689"):
            state.update(values); save_state(state); st.success("Tersklene er lagret.")
    x,y,z = st.columns(3)
    if x.button("Evaluer nå", type="primary", use_container_width=True, key="cpl_eval_v18689"):
        result = evaluate_learning(); st.success(f"Evaluert {result['closed_trades']} lukkede handler. {len(result['actions'])} handlinger."); st.rerun()
    if y.button("Generer hypoteser", use_container_width=True, key="cpl_hyp_v18689"):
        created = generate_hypotheses(); st.success(f"{len(created)} nye hypoteser opprettet."); st.rerun()
    if z.button("Rollback til Champion", use_container_width=True, key="cpl_rb_v18689"):
        try: rollback(); st.success("Rollback utført."); st.rerun()
        except ValueError as exc: st.warning(str(exc))
    hypotheses = _read(HYPOTHESES_PATH, []); experiments = _read(EXPERIMENTS_PATH, []); versions = _read(VERSIONS_PATH, [])
    t1,t2,t3 = st.tabs(["Hypoteser", "Eksperimenter", "Parameterhistorikk"])
    with t1:
        if hypotheses:
            st.dataframe(pd.DataFrame(hypotheses), use_container_width=True, hide_index=True)
            choices = {f"{h['hypothesis_id']} · {h['parameter']} {h['before']} → {h['after']} ({h['status']})": h for h in hypotheses if h.get("status") in {"NEW","TESTING"}}
            if choices:
                label = st.selectbox("Velg hypotese", list(choices), key="cpl_select_h_v18689"); h = choices[label]
                p,q = st.columns(2)
                if p.button("Start Challenger", key="cpl_start_ch_v18689"):
                    start_challenger(h["hypothesis_id"]); st.success("Challenger startet."); st.rerun()
                if q.button("Aktiver i prøvemodus", key="cpl_trial_v18689"):
                    apply_trial(h["hypothesis_id"]); st.success("Midlertidig parameterendring aktivert og varslet."); st.rerun()
        else: st.info("Ingen hypoteser ennå. Modulen venter på nok lukkede handler eller manuell evaluering.")
    with t2:
        if experiments: st.dataframe(pd.DataFrame(experiments), use_container_width=True, hide_index=True)
        else: st.caption("Ingen eksperimenter.")
    with t3:
        if versions: st.dataframe(pd.DataFrame(versions), use_container_width=True, hide_index=True)
        else: st.caption("Champion opprettes ved første evaluering.")
        if st.button("Promoter aktiv prøveversjon til Champion", key="cpl_promote_v18689"):
            try: promote_trial(); st.success("Ny Champion er aktivert og varslet."); st.rerun()
            except ValueError as exc: st.warning(str(exc))
