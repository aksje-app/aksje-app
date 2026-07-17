"""Controlled, human-approved Learning Loop for AI Aksje Analyzer v18.6.80.

The loop may generate proposals from completed paper-trade analytics, but it can
never apply changes automatically. A proposal must be explicitly approved and
then explicitly activated by a user. Every applied change stores a before/after
snapshot and can be rolled back.
"""
from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from services.storage_service import get_storage_service

VERSION = "v18.6.80"
STATE_KEY = "ai_discovery/learning_loop_v18680.json"
AUDIT_KEY = "ai_discovery/learning_loop_audit_v18680.jsonl"

DEFAULT_STATE = {
    "version": VERSION,
    "mode": "OFF",  # OFF | PROPOSAL_ONLY | APPROVAL_REQUIRED
    "proposals": [],
    "applied_history": [],
    "updated_at": "",
}

# Hard guardrails. The learning loop cannot propose or apply keys outside this set.
RULE_GUARDRAILS = {
    "min_buy_confidence": {"min": 55, "max": 95, "max_step": 3, "type": "int"},
    "min_buy_score": {"min": 5.0, "max": 9.5, "max_step": 0.3, "type": "float"},
    "position_size_pct": {"min": 2.0, "max": 20.0, "max_step": 2.0, "type": "float"},
    "max_open_positions": {"min": 1, "max": 15, "max_step": 1, "type": "int"},
    "stop_loss_pct": {"min": 3.0, "max": 15.0, "max_step": 1.0, "type": "float"},
    "take_profit_pct": {"min": 5.0, "max": 35.0, "max_step": 2.0, "type": "float"},
    "trailing_stop_pct": {"min": 3.0, "max": 20.0, "max_step": 1.0, "type": "float"},
    "minimum_hold_hours": {"min": 0, "max": 168, "max_step": 12, "type": "int"},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _storage():
    return get_storage_service()


def load_state() -> dict:
    raw = _storage().read_json(STATE_KEY, default=None)
    state = copy.deepcopy(DEFAULT_STATE)
    if isinstance(raw, dict):
        state.update(raw)
    state.setdefault("proposals", [])
    state.setdefault("applied_history", [])
    return state


def save_state(state: dict) -> None:
    state = copy.deepcopy(state)
    state["version"] = VERSION
    state["updated_at"] = _now()
    _storage().write_json(STATE_KEY, state)


def _audit(event: str, details: dict) -> None:
    _storage().append_jsonl(AUDIT_KEY, {"time": _now(), "version": VERSION, "event": event, **details})


def set_mode(mode: str) -> dict:
    mode = str(mode or "OFF").upper()
    if mode not in {"OFF", "PROPOSAL_ONLY", "APPROVAL_REQUIRED"}:
        raise ValueError("Ugyldig Learning Loop-modus")
    state = load_state()
    old = state.get("mode", "OFF")
    state["mode"] = mode
    save_state(state)
    _audit("MODE_CHANGED", {"from": old, "to": mode})
    return state


def _coerce(rule_key: str, value: Any) -> int | float:
    guard = RULE_GUARDRAILS[rule_key]
    number = float(value)
    number = max(float(guard["min"]), min(float(guard["max"]), number))
    return int(round(number)) if guard["type"] == "int" else round(number, 3)


def validate_change(rule_key: str, current: Any, proposed: Any) -> tuple[bool, str, int | float | None]:
    if rule_key not in RULE_GUARDRAILS:
        return False, "Regelen er ikke tillatt av guardrails", None
    try:
        current_num = float(current)
        proposed_num = _coerce(rule_key, proposed)
    except Exception:
        return False, "Verdien er ikke numerisk", None
    guard = RULE_GUARDRAILS[rule_key]
    if abs(float(proposed_num) - current_num) > float(guard["max_step"]) + 1e-9:
        return False, f"Endringen overstiger maks steg {guard['max_step']}", None
    return True, "OK", proposed_num


def _proposal(rule_key: str, current: Any, proposed: Any, reason: str, evidence: dict, confidence: str = "MEDIUM") -> dict | None:
    ok, validation, clean = validate_change(rule_key, current, proposed)
    if not ok or clean == current:
        return None
    now = _now()
    return {
        "proposal_id": uuid.uuid4().hex[:12],
        "created_at": now,
        "updated_at": now,
        "status": "PENDING",
        "rule_key": rule_key,
        "current_value": current,
        "proposed_value": clean,
        "reason": reason,
        "evidence": evidence,
        "proposal_confidence": confidence,
        "validation": validation,
        "review_note": "",
        "reviewed_at": "",
        "applied_at": "",
        "rollback_available": False,
    }


def generate_proposals(report: dict, rules: dict, minimum_observations: int = 12) -> list[dict]:
    """Create conservative suggestions. This function never changes live rules."""
    state = load_state()
    if state.get("mode") == "OFF":
        raise RuntimeError("Learning Loop er AV. Velg Proposal only eller Approval required først.")

    metrics = report.get("metrics") or {}
    n = int(metrics.get("trade_count") or 0)
    if n < int(minimum_observations):
        raise RuntimeError(f"For lite datagrunnlag: {n}/{minimum_observations} avsluttede handler.")

    candidates: list[dict | None] = []
    hit = float(metrics.get("hit_rate_pct") or 0)
    pf = float(metrics.get("profit_factor") or 0)
    dd = abs(float(metrics.get("max_drawdown_pct") or 0))
    avg_win = float(metrics.get("average_win_pct") or 0)
    avg_loss = abs(float(metrics.get("average_loss_pct") or 0))

    # Confidence calibration: require a bucket with at least five observations.
    calibrated = [r for r in report.get("confidence_calibration", []) if int(r.get("observations") or 0) >= 5]
    if calibrated:
        strongest = max(calibrated, key=lambda r: (float(r.get("hit_rate_pct") or 0), int(r.get("observations") or 0)))
        best_hit = float(strongest.get("hit_rate_pct") or 0)
        current = int(rules.get("min_buy_confidence", 70))
        if best_hit < 50 and hit < 50:
            candidates.append(_proposal("min_buy_confidence", current, current + 2,
                "Svak realisert treffprosent tilsier en litt strengere confidence-terskel.",
                {"trade_count": n, "overall_hit_rate_pct": hit, "best_calibrated_bucket": strongest}, "MEDIUM"))
        elif best_hit >= 70 and hit >= 58 and current > 60:
            candidates.append(_proposal("min_buy_confidence", current, current - 1,
                "God kalibrert treffprosent kan støtte en svært liten utvidelse av kandidatgrunnlaget.",
                {"trade_count": n, "overall_hit_rate_pct": hit, "best_calibrated_bucket": strongest}, "LOW"))

    if pf < 1.0 or dd >= 15:
        current = float(rules.get("position_size_pct", 10.0))
        candidates.append(_proposal("position_size_pct", current, current - min(2.0, max(0.5, current * 0.1)),
            "Profit Factor under 1 eller høy drawdown tilsier lavere kapital per posisjon.",
            {"trade_count": n, "profit_factor": pf, "max_drawdown_pct": -dd}, "HIGH" if pf < 0.8 else "MEDIUM"))

    if avg_loss > 0 and avg_win > 0 and avg_loss > avg_win * 1.15:
        current = float(rules.get("stop_loss_pct", 7.0))
        candidates.append(_proposal("stop_loss_pct", current, current - 0.5,
            "Gjennomsnittstapet er større enn gjennomsnittsgevinsten; et marginalt strammere stop-loss foreslås.",
            {"average_win_pct": avg_win, "average_loss_pct": -avg_loss, "trade_count": n}, "MEDIUM"))

    if avg_win >= float(rules.get("take_profit_pct", 12.0)) * 1.25 and pf > 1.2:
        current = float(rules.get("take_profit_pct", 12.0))
        candidates.append(_proposal("take_profit_pct", current, current + 1.0,
            "Vinnerhandler løper betydelig lenger enn dagens take-profit og Profit Factor er positiv.",
            {"average_win_pct": avg_win, "profit_factor": pf, "trade_count": n}, "LOW"))

    created = [p for p in candidates if p]
    # Avoid duplicate pending proposals for the same key/value.
    existing = {(p.get("rule_key"), p.get("proposed_value")) for p in state["proposals"] if p.get("status") in {"PENDING", "APPROVED"}}
    created = [p for p in created if (p["rule_key"], p["proposed_value"]) not in existing]
    state["proposals"] = created + state["proposals"]
    save_state(state)
    _audit("PROPOSALS_GENERATED", {"count": len(created), "minimum_observations": minimum_observations, "trade_count": n})
    return created


def review_proposal(proposal_id: str, decision: str, note: str = "") -> dict:
    decision = str(decision or "").upper()
    status = {"APPROVE": "APPROVED", "REJECT": "REJECTED"}.get(decision)
    if not status:
        raise ValueError("Decision må være APPROVE eller REJECT")
    state = load_state()
    for proposal in state["proposals"]:
        if proposal.get("proposal_id") == proposal_id:
            if proposal.get("status") not in {"PENDING", "APPROVED"}:
                raise RuntimeError(f"Forslaget kan ikke vurderes fra status {proposal.get('status')}")
            proposal.update({"status": status, "review_note": note, "reviewed_at": _now(), "updated_at": _now()})
            save_state(state)
            _audit("PROPOSAL_REVIEWED", {"proposal_id": proposal_id, "decision": status, "note": note})
            return proposal
    raise KeyError("Forslaget finnes ikke")


def apply_proposal(proposal_id: str) -> dict:
    """Apply one approved proposal to trading_rules. Never called automatically."""
    state = load_state()
    if state.get("mode") != "APPROVAL_REQUIRED":
        raise RuntimeError("Aktivering krever modus APPROVAL_REQUIRED.")
    proposal = next((p for p in state["proposals"] if p.get("proposal_id") == proposal_id), None)
    if not proposal:
        raise KeyError("Forslaget finnes ikke")
    if proposal.get("status") != "APPROVED":
        raise RuntimeError("Forslaget må godkjennes før aktivering.")

    from trading_settings import load_rules, save_rules
    before = load_rules()
    key = proposal["rule_key"]
    ok, reason, clean = validate_change(key, before.get(key), proposal.get("proposed_value"))
    if not ok:
        raise RuntimeError(reason)
    after = copy.deepcopy(before)
    after[key] = clean
    save_rules(after)
    applied_at = _now()
    record = {
        "application_id": uuid.uuid4().hex[:12], "proposal_id": proposal_id, "applied_at": applied_at,
        "rule_key": key, "before_value": before.get(key), "after_value": clean,
        "before_rules": before, "after_rules": after, "rolled_back_at": "",
    }
    state["applied_history"].insert(0, record)
    proposal.update({"status": "APPLIED", "applied_at": applied_at, "updated_at": applied_at, "rollback_available": True})
    save_state(state)
    _audit("PROPOSAL_APPLIED", {k: record[k] for k in ("application_id", "proposal_id", "rule_key", "before_value", "after_value")})
    return record


def rollback_application(application_id: str) -> dict:
    state = load_state()
    record = next((r for r in state["applied_history"] if r.get("application_id") == application_id), None)
    if not record:
        raise KeyError("Aktiveringen finnes ikke")
    if record.get("rolled_back_at"):
        raise RuntimeError("Endringen er allerede rullet tilbake")
    from trading_settings import save_rules
    save_rules(record["before_rules"])
    rolled = _now()
    record["rolled_back_at"] = rolled
    proposal = next((p for p in state["proposals"] if p.get("proposal_id") == record.get("proposal_id")), None)
    if proposal:
        proposal.update({"status": "ROLLED_BACK", "rollback_available": False, "updated_at": rolled})
    save_state(state)
    _audit("APPLICATION_ROLLED_BACK", {"application_id": application_id, "proposal_id": record.get("proposal_id")})
    return record


def render_learning_loop_tab(report: dict | None = None) -> None:
    import streamlit as st
    from ai_learning_foundation import learning_report
    from trading_settings import load_rules

    state = load_state()
    report = report or learning_report()
    rules = load_rules()

    st.markdown("### Kontrollert Learning Loop")
    st.caption("Analyse kan foreslå små regelendringer. Ingen endring aktiveres uten separat godkjenning og eksplisitt Aktiver-klikk.")

    labels = {"OFF": "AV", "PROPOSAL_ONLY": "Kun forslag", "APPROVAL_REQUIRED": "Forslag + manuell aktivering"}
    reverse = {v: k for k, v in labels.items()}
    selected = st.selectbox("Modus", list(reverse), index=list(reverse).index(labels.get(state.get("mode"), "AV")), key="learning_loop_mode_v18680")
    requested_mode = reverse[selected]
    if requested_mode != state.get("mode"):
        if st.button("Lagre modus", key="learning_loop_save_mode_v18680"):
            set_mode(requested_mode); st.success("Modus lagret."); st.rerun()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Modus", labels.get(state.get("mode"), "AV"))
    c2.metric("Avsluttede handler", int((report.get("metrics") or {}).get("trade_count") or 0))
    c3.metric("Ventende forslag", sum(p.get("status") == "PENDING" for p in state["proposals"]))
    c4.metric("Aktive endringer", sum(p.get("status") == "APPLIED" for p in state["proposals"]))

    minimum = st.number_input("Minimum avsluttede handler før forslag", min_value=8, max_value=200, value=12, step=1, key="learning_loop_min_obs_v18680")
    if st.button("Generer nye forslag", disabled=state.get("mode") == "OFF", key="learning_loop_generate_v18680"):
        try:
            new = generate_proposals(report, rules, int(minimum))
            st.success(f"{len(new)} nye forslag opprettet." if new else "Ingen nye forslag passerte guardrails.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    st.markdown("#### Forslagskø")
    proposals = load_state()["proposals"]
    if not proposals:
        st.info("Ingen forslag ennå.")
    for p in proposals[:50]:
        title = f"{p['rule_key']}: {p['current_value']} → {p['proposed_value']} · {p['status']}"
        with st.expander(title, expanded=p.get("status") in {"PENDING", "APPROVED"}):
            st.write(p.get("reason"))
            st.json(p.get("evidence") or {})
            st.caption(f"Forslags-confidence: {p.get('proposal_confidence')} · Opprettet {p.get('created_at')}")
            note = st.text_input("Vurderingsnotat", value=p.get("review_note") or "", key=f"ll_note_{p['proposal_id']}")
            a, b, c = st.columns(3)
            if a.button("Godkjenn", disabled=p.get("status") != "PENDING", key=f"ll_approve_{p['proposal_id']}"):
                try: review_proposal(p["proposal_id"], "APPROVE", note); st.rerun()
                except Exception as exc: st.error(str(exc))
            if b.button("Avvis", disabled=p.get("status") not in {"PENDING", "APPROVED"}, key=f"ll_reject_{p['proposal_id']}"):
                try: review_proposal(p["proposal_id"], "REJECT", note); st.rerun()
                except Exception as exc: st.error(str(exc))
            confirm = st.checkbox("Jeg bekrefter aktivering av denne ene regelendringen", key=f"ll_confirm_{p['proposal_id']}")
            if c.button("Aktiver", disabled=not (p.get("status") == "APPROVED" and state.get("mode") == "APPROVAL_REQUIRED" and confirm), key=f"ll_apply_{p['proposal_id']}"):
                try: apply_proposal(p["proposal_id"]); st.success("Endringen er aktivert og snapshot er lagret."); st.rerun()
                except Exception as exc: st.error(str(exc))

    history = load_state()["applied_history"]
    st.markdown("#### Aktiveringshistorikk og rollback")
    if not history:
        st.info("Ingen regelendringer er aktivert av Learning Loop.")
    for record in history[:30]:
        label = f"{record['rule_key']}: {record['before_value']} → {record['after_value']} · {record['applied_at']}"
        with st.expander(label):
            st.json({k: v for k, v in record.items() if k not in {"before_rules", "after_rules"}})
            rollback_confirm = st.checkbox("Bekreft rollback", key=f"ll_rb_confirm_{record['application_id']}")
            if st.button("Rull tilbake", disabled=bool(record.get("rolled_back_at")) or not rollback_confirm, key=f"ll_rb_{record['application_id']}"):
                try: rollback_application(record["application_id"]); st.success("Reglene er rullet tilbake."); st.rerun()
                except Exception as exc: st.error(str(exc))

    st.warning("Sikkerhetsmodell: ingen auto-apply, ingen endring uten godkjenning, begrensede regelsett, maks endringssteg, full audit og rollback.")
