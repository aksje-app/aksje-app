"""Adaptive AI Ranking v18.7.4.

Creates transparent weight proposals from evaluated recommendation snapshots.
Production weights change only after explicit approval. Test mode is shadow-only.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from storage_architecture import runtime_data_path
from persistent_config_store import read_persistent_json, write_persistent_json

VERSION = "v18.7.4"
ROOT = runtime_data_path("adaptive_ranking")
STATE_PATH = ROOT / "model_state.json"
PROPOSALS_PATH = ROOT / "model_proposals.json"
AUDIT_PATH = ROOT / "model_audit.json"

MIN_OBSERVATIONS = 100
MIN_HISTORY_DAYS = 90
MAX_ABSOLUTE_SHIFT = 0.05
MIN_SIMULATED_IMPROVEMENT_PP = 1.0

COMPONENT_FIELDS = {
    "discovery": ("discovery_score", "ai_score"),
    "fundamental": ("fundamental_score",),
    "research": ("research_score", "news_score"),
    "validation": ("validation_score", "technical_score"),
    "portfolio_fit": ("portfolio_fit_score",),
    "risk_adjustment": ("risk_adjustment_score",),
    "insider": ("insider_score",),
    "news": ("news_score",),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path: Path, default: Any) -> Any:
    stored = read_persistent_json(f"adaptive_ranking/{path.name}", default=None)
    if stored is not None:
        ROOT.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stored, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return stored
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        write_persistent_json(f"adaptive_ranking/{path.name}", value)
        return value
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_persistent_json(f"adaptive_ranking/{path.name}", payload)


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _normalize(weights: Mapping[str, float]) -> dict[str, float]:
    clean = {str(k): max(0.0, float(v or 0.0)) for k, v in weights.items()}
    total = sum(clean.values()) or 1.0
    return {k: v / total for k, v in clean.items()}


def _state() -> dict[str, Any]:
    return _read(STATE_PATH, {
        "active_model": None,
        "auto_approve": False,
        "created_at": _now(),
    })


def get_active_weights(base_weights: Mapping[str, float]) -> tuple[dict[str, float], dict[str, Any]]:
    """Return approved production weights only. Pending/test proposals never affect ranking."""
    base = _normalize(base_weights)
    state = _state()
    active = state.get("active_model") if isinstance(state.get("active_model"), Mapping) else None
    if not active or not isinstance(active.get("weights"), Mapping):
        return base, {"active": False, "mode": "STANDARD", "model_version": "standard", "reason": "Ingen godkjent adaptiv modell"}
    candidate = _normalize(active["weights"])
    merged = dict(base)
    merged.update({k: candidate[k] for k in merged if k in candidate})
    merged = _normalize(merged)
    return merged, {
        "active": True,
        "mode": "APPROVED",
        "model_version": active.get("model_version"),
        "approved_at": active.get("approved_at"),
        "proposal_id": active.get("proposal_id"),
        "observations": active.get("observations", 0),
    }


def _return_for_row(row: Mapping[str, Any], horizon: int = 30) -> float | None:
    evaluations = row.get("evaluations") if isinstance(row.get("evaluations"), Mapping) else {}
    for key in (str(horizon), "30", "5", "1"):
        ev = evaluations.get(key) if isinstance(evaluations.get(key), Mapping) else {}
        value = _num(ev.get("return_pct"))
        if value is not None:
            return value
    return None


def _component_value(row: Mapping[str, Any], component: str) -> float | None:
    for field in COMPONENT_FIELDS.get(component, ()):
        value = _num(row.get(field))
        if value is not None:
            return max(0.0, min(100.0, value))
    return None


def _correlation(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) < 3 or len(xs) != len(ys):
        return 0.0
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs)
    dy = sum((y - my) ** 2 for y in ys)
    if dx <= 0 or dy <= 0:
        return 0.0
    return numerator / math.sqrt(dx * dy)


def _score_row(row: Mapping[str, Any], weights: Mapping[str, float]) -> float:
    total = 0.0
    used = 0.0
    for component, weight in weights.items():
        value = _component_value(row, component)
        if value is None:
            continue
        total += value * weight
        used += weight
    return total / used if used else 50.0


def _simulation(rows: Sequence[Mapping[str, Any]], weights: Mapping[str, float]) -> dict[str, float]:
    pairs = [(_score_row(row, weights), _return_for_row(row)) for row in rows]
    pairs = [(score, ret) for score, ret in pairs if ret is not None]
    if not pairs:
        return {"count": 0, "hit_rate": 0.0, "average_return": 0.0}
    pairs.sort(key=lambda x: x[0], reverse=True)
    selected = pairs[:max(1, len(pairs) // 2)]
    returns = [float(ret) for _, ret in selected]
    return {
        "count": len(returns),
        "hit_rate": round(sum(x > 0 for x in returns) / len(returns) * 100.0, 2),
        "average_return": round(sum(returns) / len(returns), 3),
    }


def build_proposal(rows: Sequence[Mapping[str, Any]], base_weights: Mapping[str, float], *, force: bool = False) -> dict[str, Any]:
    """Build and persist a pending proposal. No production setting is changed."""
    evaluated = [dict(row) for row in rows if _return_for_row(row) is not None]
    dates = sorted(str(row.get("created_at") or "") for row in evaluated if row.get("created_at"))
    history_days = 0
    if len(dates) >= 2:
        try:
            start = datetime.fromisoformat(dates[0].replace("Z", "+00:00"))
            end = datetime.fromisoformat(dates[-1].replace("Z", "+00:00"))
            history_days = max(0, (end - start).days)
        except Exception:
            history_days = 0
    eligible = len(evaluated) >= MIN_OBSERVATIONS and history_days >= MIN_HISTORY_DAYS
    if not eligible and not force:
        return {
            "created": False,
            "status": "INSUFFICIENT_DATA",
            "observations": len(evaluated),
            "history_days": history_days,
            "required_observations": MIN_OBSERVATIONS,
            "required_history_days": MIN_HISTORY_DAYS,
        }

    base = _normalize(base_weights)
    correlations: dict[str, float] = {}
    sample_counts: dict[str, int] = {}
    raw = dict(base)
    for component in base:
        points = [(_component_value(row, component), _return_for_row(row)) for row in evaluated]
        points = [(x, y) for x, y in points if x is not None and y is not None]
        sample_counts[component] = len(points)
        corr = _correlation([x for x, _ in points], [y for _, y in points])
        correlations[component] = round(corr, 4)
        shift = max(-MAX_ABSOLUTE_SHIFT, min(MAX_ABSOLUTE_SHIFT, corr * 0.05))
        raw[component] = max(0.01, base[component] + shift)
    proposed = _normalize(raw)

    standard_sim = _simulation(evaluated, base)
    adaptive_sim = _simulation(evaluated, proposed)
    improvement_pp = round(adaptive_sim["hit_rate"] - standard_sim["hit_rate"], 2)
    proposal_id = uuid.uuid4().hex[:12]
    proposal = {
        "proposal_id": proposal_id,
        "model_version": f"adaptive-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "created_at": _now(),
        "status": "PENDING",
        "base_weights": base,
        "proposed_weights": proposed,
        "correlations": correlations,
        "sample_counts": sample_counts,
        "observations": len(evaluated),
        "history_days": history_days,
        "standard_simulation": standard_sim,
        "adaptive_simulation": adaptive_sim,
        "simulated_hit_rate_improvement_pp": improvement_pp,
        "recommended": improvement_pp >= MIN_SIMULATED_IMPROVEMENT_PP,
        "guardrails": {
            "max_absolute_shift": MAX_ABSOLUTE_SHIFT,
            "minimum_observations": MIN_OBSERVATIONS,
            "minimum_history_days": MIN_HISTORY_DAYS,
            "minimum_improvement_pp": MIN_SIMULATED_IMPROVEMENT_PP,
            "manual_approval_required": True,
        },
    }
    proposals = _read(PROPOSALS_PATH, [])
    proposals.insert(0, proposal)
    _write(PROPOSALS_PATH, proposals[:100])
    _audit("PROPOSAL_CREATED", proposal_id, {"observations": len(evaluated), "improvement_pp": improvement_pp})
    return {"created": True, **proposal}


def list_proposals() -> list[dict[str, Any]]:
    return [dict(x) for x in _read(PROPOSALS_PATH, []) if isinstance(x, Mapping)]


def _audit(action: str, proposal_id: str | None, details: Mapping[str, Any] | None = None) -> None:
    rows = _read(AUDIT_PATH, [])
    rows.insert(0, {"at": _now(), "action": action, "proposal_id": proposal_id, "details": dict(details or {})})
    _write(AUDIT_PATH, rows[:500])


def set_proposal_status(proposal_id: str, status: str) -> dict[str, Any]:
    status = status.upper().strip()
    if status not in {"TEST", "REJECTED", "APPROVED"}:
        raise ValueError("Ugyldig status")
    proposals = list_proposals()
    selected = next((x for x in proposals if x.get("proposal_id") == proposal_id), None)
    if selected is None:
        raise KeyError("Forslaget finnes ikke")
    selected["status"] = status
    selected["decision_at"] = _now()
    state = _state()
    if status == "APPROVED":
        previous = state.get("active_model")
        state["previous_model"] = previous
        state["active_model"] = {
            "proposal_id": proposal_id,
            "model_version": selected.get("model_version"),
            "weights": selected.get("proposed_weights"),
            "approved_at": _now(),
            "observations": selected.get("observations", 0),
        }
        _write(STATE_PATH, state)
    _write(PROPOSALS_PATH, proposals)
    _audit(f"PROPOSAL_{status}", proposal_id, {"model_version": selected.get("model_version")})
    return selected


def rollback_active_model() -> dict[str, Any]:
    state = _state()
    current = state.get("active_model")
    previous = state.get("previous_model")
    state["active_model"] = previous
    state["previous_model"] = current
    state["rolled_back_at"] = _now()
    _write(STATE_PATH, state)
    _audit("MODEL_ROLLBACK", current.get("proposal_id") if isinstance(current, Mapping) else None)
    return state


def model_summary(base_weights: Mapping[str, float]) -> dict[str, Any]:
    weights, meta = get_active_weights(base_weights)
    state = _state()
    return {"weights": weights, "meta": meta, "state": state, "proposals": list_proposals()}


def render_adaptive_ranking(base_weights: Mapping[str, float], snapshots: Sequence[Mapping[str, Any]]) -> None:
    import pandas as pd
    import streamlit as st

    st.markdown("### 🧠 Adaptiv AI-rangering")
    st.caption("AI-en foreslår endringer. Produksjonsvekter endres først når du trykker Godta. Test er kun skyggekjøring.")
    summary = model_summary(base_weights)
    meta = summary["meta"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Aktiv modell", meta.get("model_version", "standard"))
    c2.metric("Modus", meta.get("mode", "STANDARD"))
    c3.metric("Datagrunnlag", meta.get("observations", 0))

    if st.button("Analyser historikk og lag forslag", key="adaptive_build_v1874", use_container_width=True):
        result = build_proposal(snapshots, base_weights)
        if result.get("created"):
            st.success("Nytt modellforslag er opprettet. Ingen vekter er endret.")
            st.rerun()
        else:
            st.warning(f"For lite historikk: {result['observations']}/{result['required_observations']} observasjoner og {result['history_days']}/{result['required_history_days']} dager.")

    active_rows = [{"Signal": k, "Vekt %": round(v * 100, 2)} for k, v in summary["weights"].items()]
    st.dataframe(pd.DataFrame(active_rows), use_container_width=True, hide_index=True)

    proposals = summary["proposals"]
    if not proposals:
        st.info("Ingen modellforslag ennå.")
        return
    for proposal in proposals[:10]:
        title = f"{proposal.get('model_version')} · {proposal.get('status')} · {proposal.get('observations', 0)} observasjoner"
        with st.expander(title, expanded=proposal.get("status") == "PENDING"):
            a, b, c = st.columns(3)
            a.metric("Standard treff", f"{proposal.get('standard_simulation', {}).get('hit_rate', 0):.2f}%")
            b.metric("Adaptiv treff", f"{proposal.get('adaptive_simulation', {}).get('hit_rate', 0):.2f}%")
            c.metric("Forskjell", f"{proposal.get('simulated_hit_rate_improvement_pp', 0):+.2f} pp")
            comparison = []
            for key, old in proposal.get("base_weights", {}).items():
                new = proposal.get("proposed_weights", {}).get(key, old)
                comparison.append({"Signal": key, "Standard %": round(old*100,2), "Forslag %": round(new*100,2), "Endring pp": round((new-old)*100,2)})
            st.dataframe(pd.DataFrame(comparison), use_container_width=True, hide_index=True)
            if proposal.get("status") in {"PENDING", "TEST"}:
                x, y, z = st.columns(3)
                if x.button("✅ Godta", key=f"approve_{proposal['proposal_id']}", use_container_width=True):
                    set_proposal_status(proposal["proposal_id"], "APPROVED"); st.rerun()
                if y.button("📊 Test først", key=f"test_{proposal['proposal_id']}", use_container_width=True):
                    set_proposal_status(proposal["proposal_id"], "TEST"); st.rerun()
                if z.button("❌ Avvis", key=f"reject_{proposal['proposal_id']}", use_container_width=True):
                    set_proposal_status(proposal["proposal_id"], "REJECTED"); st.rerun()
    if meta.get("active") and st.button("↩️ Rull tilbake aktiv modell", key="adaptive_rollback_v1874", use_container_width=True):
        rollback_active_model(); st.success("Aktiv modell er rullet tilbake."); st.rerun()
