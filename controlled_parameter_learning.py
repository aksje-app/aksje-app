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
import itertools
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from storage_architecture import runtime_data_path
from persistent_config_store import read_persistent_json, write_persistent_json, persistence_status
from autonomous_portfolio import (
    AutonomousParameters, load_parameters, save_parameters, load_portfolio,
    calculate_performance, TRADES_PATH, DECISIONS_PATH, NOTIFICATIONS_PATH,
)
from durable_runtime import append_event, read_events
from app_version import APP_VERSION

VERSION = "v19.3.0"
ROOT = runtime_data_path("controlled_learning")
STATE_PATH = ROOT / "state.json"
HYPOTHESES_PATH = ROOT / "hypotheses.json"
EXPERIMENTS_PATH = ROOT / "experiments.json"
VERSIONS_PATH = ROOT / "parameter_versions.json"
AUDIT_PATH = ROOT / "audit.jsonl"
REPORTS_PATH = ROOT / "management_reports.json"
APPROVALS_PATH = ROOT / "promotion_approvals.json"

LEARNING_LIFECYCLE = (
    "HYPOTESE", "SIMULERT", "PARALLELLTESTET", "KLAR_FOR_VURDERING",
    "GODKJENT", "AVVIST", "TILBAKERULLERT",
)
PROTECTED_PRODUCTION_PARAMETERS = {
    "maximum_position_pct", "maximum_sector_pct", "maximum_drawdown_pct",
    "stop_loss_pct", "trailing_stop_pct", "take_profit_pct",
    "reserve_cash_pct", "maximum_open_positions", "maximum_risk_score",
    "daily_loss_limit_pct", "minimum_investment_score", "minimum_data_quality",
    "score_exit_threshold", "enable_learning_probe_buys",
}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


_PERSISTENT_PATH_KEYS = {
    STATE_PATH: "controlled_learning/state.json",
    HYPOTHESES_PATH: "controlled_learning/hypotheses.json",
    EXPERIMENTS_PATH: "controlled_learning/experiments.json",
    VERSIONS_PATH: "controlled_learning/parameter_versions.json",
    REPORTS_PATH: "controlled_learning/management_reports.json",
    APPROVALS_PATH: "controlled_learning/promotion_approvals.json",
}


def _read(path: Path, default: Any) -> Any:
    persistent_key = _PERSISTENT_PATH_KEYS.get(path)
    if persistent_key:
        stored = read_persistent_json(persistent_key, default=None)
        if stored is not None:
            return stored
    try:
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            if persistent_key:
                write_persistent_json(persistent_key, value)
            return value
    except Exception:
        pass
    return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)
    persistent_key = _PERSISTENT_PATH_KEYS.get(path)
    if persistent_key:
        write_persistent_json(persistent_key, value)


def _audit(event: str, payload: Mapping[str, Any]) -> None:
    append_event("controlled_learning/audit.jsonl", AUDIT_PATH, {"timestamp": _now(), "version": VERSION, "event": event, "payload": dict(payload)})


def load_audit(limit: int = 1000) -> list[dict[str, Any]]:
    return read_events("controlled_learning/audit.jsonl", AUDIT_PATH, limit=limit)


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
        "mode": "ASSISTED",
        "auto_risk_protection": True,
        "auto_start_challengers": True,
        "auto_promote": False,
        "automatic_evaluation": True,
        "evaluation_interval_minutes": 60,
        "management_report_frequency": "DAILY",
        "last_management_report_at": None,
        "auto_rollback": False,
        "allow_hypothesis_creation": True,
        "allow_auto_challenger": True,
        "allow_auto_trial": True,
        "allow_auto_promotion": False,
        "require_explicit_user_approval": True,
        "production_parameter_auto_change_allowed": False,
        "protected_production_parameters": sorted(PROTECTED_PRODUCTION_PARAMETERS),
        "require_confirmation_major_change": True,
        "major_change_parameter_share_pct": 20.0,
        "material_risk_change_pct": 10.0,
        "notification_level": "ALL",
        "emergency_stop": False,
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
    # v19.3.0 hard safety contract: persisted legacy settings cannot re-enable
    # autonomous production changes after an upgrade.
    state["auto_promote"] = False
    state["auto_rollback"] = False
    state["allow_auto_promotion"] = False
    state["require_explicit_user_approval"] = True
    state["production_parameter_auto_change_allowed"] = False
    state["protected_production_parameters"] = sorted(PROTECTED_PRODUCTION_PARAMETERS)
    return state


def save_state(state: Mapping[str, Any]) -> dict[str, Any]:
    merged = default_state(); merged.update(dict(state))
    merged["auto_promote"] = False
    merged["auto_rollback"] = False
    merged["allow_auto_promotion"] = False
    merged["require_explicit_user_approval"] = True
    merged["production_parameter_auto_change_allowed"] = False
    merged["protected_production_parameters"] = sorted(PROTECTED_PRODUCTION_PARAMETERS)
    _write(STATE_PATH, merged)
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
        from notifier import normalize_notification_result, send_pushover_alert
        ok, detail = normalize_notification_result(send_pushover_alert(message, title=title))
        rows[0]["delivery"] = "PUSHOVER_SENT" if ok else "PUSHOVER_FAILED"
        if detail:
            rows[0]["error"] = str(detail)[:500]
        _write(NOTIFICATIONS_PATH, rows[:1000])
    except Exception as exc:
        rows[0]["delivery"] = "PUSHOVER_FAILED"
        rows[0]["error"] = str(exc)[:500]
        _write(NOTIFICATIONS_PATH, rows[:1000])


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
        h = {"hypothesis_id": "H-" + uuid.uuid4().hex[:10], "created_at": _now(), "status": "NEW", "lifecycle_status": "HYPOTESE", "parameter": parameter, "before": round(before, 6), "after": round(after, 6), "reason": reason, "evidence": stats, "risk_level": "LOW" if parameter in {"minimum_investment_score", "minimum_data_quality", "maximum_position_pct"} else "MEDIUM", "production_applied": False}
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
    experiment = {"experiment_id": "E-" + uuid.uuid4().hex[:10], "hypothesis_id": hypothesis_id, "created_at": _now(), "status": "TESTING", "lifecycle_status": "SIMULERT", "mode": "SHADOW_READ_ONLY", "champion_version_id": champion["version_id"], "challenger_parameters": params, "baseline": _stats(_closed_trades()), "trial_trades": [], "minimum_trial_trades": int(load_state()["minimum_trial_trades"]), "conclusion": None, "production_applied": False}
    experiments = _read(EXPERIMENTS_PATH, []); experiments = experiments if isinstance(experiments, list) else []; experiments.insert(0, experiment); _write(EXPERIMENTS_PATH, experiments)
    h["status"] = "TESTING"; h["lifecycle_status"] = "SIMULERT"; h["experiment_id"] = experiment["experiment_id"]; h["production_applied"] = False; _write(HYPOTHESES_PATH, hypotheses)
    _audit("CHALLENGER_STARTED", experiment); _notify("Learning: Challenger startet", f"Tester {h['parameter']} {h['before']} → {h['after']}", experiment)
    return experiment


def apply_trial(hypothesis_id: str) -> dict[str, Any]:
    """Create a read-only shadow trial; never change production parameters."""
    hypotheses = _read(HYPOTHESES_PATH, []); h = next((x for x in hypotheses if x.get("hypothesis_id") == hypothesis_id), None)
    if not h: raise ValueError("Hypotesen finnes ikke.")
    params = load_parameters(); data = asdict(params); data[h["parameter"]] = h["after"]
    previous = asdict(params)
    versions = _read(VERSIONS_PATH, []); versions = versions if isinstance(versions, list) else []
    existing = next((v for v in versions if v.get("hypothesis_id") == hypothesis_id and v.get("status") == "TRIAL"), None)
    if existing:
        return existing
    trial = {"version_id": "PV-" + uuid.uuid4().hex[:10], "created_at": _now(), "status": "TRIAL", "lifecycle_status": "PARALLELLTESTET", "mode": "SHADOW_READ_ONLY", "parameters": data, "previous_parameters": previous, "hypothesis_id": hypothesis_id, "baseline_performance": calculate_performance(), "production_applied": False, "requires_explicit_user_approval": True}
    versions.insert(0, trial); _write(VERSIONS_PATH, versions); h["status"] = "TRIAL"; h["lifecycle_status"] = "PARALLELLTESTET"; h["production_applied"] = False; _write(HYPOTHESES_PATH, hypotheses)
    _audit("SHADOW_TRIAL_CREATED", trial); _notify("Learning: parallelltest klar", f"{h['parameter']}: {h['before']} → {h['after']} testes uten produksjonspåvirkning.", trial)
    return trial


def rollback(reason: str = "Manuell rollback") -> dict[str, Any]:
    versions = _read(VERSIONS_PATH, []); versions = versions if isinstance(versions, list) else []
    current = next((v for v in versions if v.get("status") == "TRIAL"), None)
    champion = next((v for v in versions if v.get("status") == "CHAMPION"), None)
    target = (current or {}).get("previous_parameters") or (champion or {}).get("parameters")
    if not target: raise ValueError("Ingen tidligere parameter-versjon tilgjengelig.")
    if current and current.get("production_applied"):
        save_parameters(AutonomousParameters(**target))
    if current:
        current["status"] = "ROLLED_BACK"; current["lifecycle_status"] = "TILBAKERULLERT"; current["rollback_reason"] = reason; current["rolled_back_at"] = _now()
        hypotheses = _read(HYPOTHESES_PATH, [])
        if isinstance(hypotheses, list):
            h = next((x for x in hypotheses if x.get("hypothesis_id") == current.get("hypothesis_id")), None)
            if h: h["lifecycle_status"] = "TILBAKERULLERT"; h["status"] = "ROLLED_BACK"
            _write(HYPOTHESES_PATH, hypotheses)
    _write(VERSIONS_PATH, versions); _audit("PARAMETER_ROLLBACK", {"reason": reason, "target": target, "production_changed": bool(current and current.get("production_applied"))}); _notify("Learning: rollback", reason, {"target": target})
    return {"version_id": (current or {}).get("version_id"), "parameters": target, "production_changed": bool(current and current.get("production_applied"))}


def promote_trial(*, explicit_user_approval: bool = False, approval_id: str = "") -> dict[str, Any]:
    """Promote only after an explicit user approval; never from automation."""
    if not explicit_user_approval or not approval_id:
        raise PermissionError("Champion-promotering krever en eksplisitt godkjenningsbeslutning fra bruker.")
    versions = _read(VERSIONS_PATH, []); versions = versions if isinstance(versions, list) else []
    trial = next((v for v in versions if v.get("status") == "TRIAL"), None)
    if not trial: raise ValueError("Ingen aktiv prøveversjon.")
    approvals = _read(APPROVALS_PATH, []); approvals = approvals if isinstance(approvals, list) else []
    approval = next((a for a in approvals if a.get("approval_id") == approval_id and a.get("version_id") == trial.get("version_id") and a.get("status") == "PENDING"), None)
    if not approval:
        raise PermissionError("Gyldig ventende brukergodkjenning ble ikke funnet.")
    previous = asdict(load_parameters())
    save_parameters(AutonomousParameters(**dict(trial.get("parameters") or {})))
    old = next((v for v in versions if v.get("status") == "CHAMPION"), None)
    if old: old["status"] = "ARCHIVED_CHAMPION"
    trial["status"] = "CHAMPION"; trial["lifecycle_status"] = "GODKJENT"; trial["production_applied"] = True; trial["approval_id"] = approval_id; trial["previous_parameters"] = previous; trial["promoted_at"] = _now(); trial["promotion_performance"] = calculate_performance()
    hypotheses = _read(HYPOTHESES_PATH, [])
    if isinstance(hypotheses, list):
        h = next((x for x in hypotheses if x.get("hypothesis_id") == trial.get("hypothesis_id")), None)
        if h: h["lifecycle_status"] = "GODKJENT"; h["status"] = "APPROVED"; h["production_applied"] = True
        _write(HYPOTHESES_PATH, hypotheses)
    _write(VERSIONS_PATH, versions); _audit("TRIAL_PROMOTED_TO_CHAMPION", trial); _notify("Learning: ny Champion", f"Parameter-versjon {trial['version_id']} er godkjent og promotert.", trial)
    return trial



def _parse_time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except Exception:
        return None


def _mode_policy(state: Mapping[str, Any]) -> dict[str, bool]:
    mode = str(state.get("mode") or "ASSISTED").upper()
    stopped = bool(state.get("emergency_stop", False))
    return {
        "observe_only": mode == "OBSERVER" or stopped,
        "auto_hypothesis": not stopped and bool(state.get("allow_hypothesis_creation", True)),
        "auto_challenger": not stopped and mode in {"ASSISTED", "FULL"} and bool(state.get("allow_auto_challenger", True)),
        "auto_trial": not stopped and mode in {"ASSISTED", "FULL"} and bool(state.get("allow_auto_trial", True)),
        "auto_promote": False,
        "auto_rollback": False,
    }


def _promotion_guard(trial: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    champion = ensure_champion_version()
    before = dict(champion.get("parameters") or {})
    after = dict(trial.get("parameters") or {})
    comparable = [k for k in before if k in after]
    changed = [k for k in comparable if before.get(k) != after.get(k)]
    share = (len(changed) / max(1, len(comparable))) * 100.0
    risk_keys = {
        "maximum_position_pct", "maximum_sector_pct", "maximum_drawdown_pct",
        "stop_loss_pct", "trailing_stop_pct", "take_profit_pct", "reserve_cash_pct",
        "maximum_open_positions", "maximum_risk_score", "daily_loss_limit_pct",
    }
    risk_changes = []
    material_limit = float(state.get("material_risk_change_pct", 10.0))
    for key in changed:
        if key not in risk_keys:
            continue
        old = _f(before.get(key))
        new = _f(after.get(key))
        rel = abs(new - old) / max(abs(old), 1e-9) * 100.0
        if rel >= material_limit:
            risk_changes.append({"parameter": key, "before": old, "after": new, "relative_change_pct": rel})
    major = share > float(state.get("major_change_parameter_share_pct", 20.0))
    material_risk = bool(risk_changes)
    return {
        "requires_confirmation": True,
        "major_change": major,
        "material_risk_change": material_risk,
        "changed_parameters": changed,
        "changed_parameter_share_pct": share,
        "risk_changes": risk_changes,
    }


def _queue_promotion_approval(trial: Mapping[str, Any], guard: Mapping[str, Any]) -> dict[str, Any]:
    approvals = _read(APPROVALS_PATH, [])
    approvals = approvals if isinstance(approvals, list) else []
    existing = next((a for a in approvals if a.get("version_id") == trial.get("version_id") and a.get("status") == "PENDING"), None)
    if existing:
        return existing
    item = {
        "approval_id": "PA-" + uuid.uuid4().hex[:10],
        "created_at": _now(),
        "status": "PENDING",
        "lifecycle_status": "KLAR_FOR_VURDERING",
        "version_id": trial.get("version_id"),
        "hypothesis_id": trial.get("hypothesis_id"),
        "guard": dict(guard),
    }
    approvals.insert(0, item)
    _write(APPROVALS_PATH, approvals)
    trial["lifecycle_status"] = "KLAR_FOR_VURDERING"
    versions = _read(VERSIONS_PATH, [])
    if isinstance(versions, list):
        for version in versions:
            if version.get("version_id") == trial.get("version_id"):
                version["lifecycle_status"] = "KLAR_FOR_VURDERING"
        _write(VERSIONS_PATH, versions)
    hypotheses = _read(HYPOTHESES_PATH, [])
    if isinstance(hypotheses, list):
        h = next((x for x in hypotheses if x.get("hypothesis_id") == trial.get("hypothesis_id")), None)
        if h: h["lifecycle_status"] = "KLAR_FOR_VURDERING"
        _write(HYPOTHESES_PATH, hypotheses)
    _audit("CHAMPION_PROMOTION_APPROVAL_REQUIRED", item)
    _notify("Autonomi: godkjenning kreves", f"Champion-promotering {trial.get('version_id')} krever brukerbekreftelse.", item)
    return item


def resolve_promotion_approval(approval_id: str, approve: bool, *, note: str = "") -> dict[str, Any]:
    approvals = _read(APPROVALS_PATH, [])
    approvals = approvals if isinstance(approvals, list) else []
    item = next((a for a in approvals if a.get("approval_id") == approval_id), None)
    if not item:
        raise ValueError("Godkjenningsforespørselen finnes ikke.")
    if item.get("status") != "PENDING":
        raise ValueError("Godkjenningsforespørselen er allerede behandlet.")
    if approve:
        promoted = promote_trial(explicit_user_approval=True, approval_id=approval_id)
        item["status"] = "APPROVED"
        item["lifecycle_status"] = "GODKJENT"
        item["resolved_at"] = _now()
        item["decision_note"] = note
        item["resolved_by"] = "USER"
        item["promoted_version_id"] = promoted.get("version_id")
        _audit("CHAMPION_PROMOTION_APPROVED", item)
    else:
        item["status"] = "REJECTED"
        item["lifecycle_status"] = "AVVIST"
        item["resolved_at"] = _now()
        item["decision_note"] = note
        item["resolved_by"] = "USER"
        hypotheses = _read(HYPOTHESES_PATH, [])
        if isinstance(hypotheses, list):
            h = next((x for x in hypotheses if x.get("hypothesis_id") == item.get("hypothesis_id")), None)
            if h: h["lifecycle_status"] = "AVVIST"; h["status"] = "REJECTED"
            _write(HYPOTHESES_PATH, hypotheses)
        _audit("CHAMPION_PROMOTION_REJECTED", item)
        _notify("Autonomi: promotering avvist", f"Champion-promotering {item.get('version_id')} ble avvist.", item)
    _write(APPROVALS_PATH, approvals)
    return item


def _experiment_progress(experiment: Mapping[str, Any], closed_count: int) -> int:
    baseline = int(_f((experiment.get("baseline") or {}).get("trades"), 0))
    return max(0, closed_count - baseline)


def _refresh_experiments(state: Mapping[str, Any], perf: Mapping[str, Any], stats: Mapping[str, Any]) -> list[dict[str, Any]]:
    experiments = _read(EXPERIMENTS_PATH, [])
    if not isinstance(experiments, list):
        return []
    changed = False
    for exp in experiments:
        if exp.get("status") not in {"TESTING", "TRIAL"}:
            continue
        exp["observed_trades"] = _experiment_progress(exp, int(stats.get("trades", 0)))
        exp["latest_statistics"] = dict(stats)
        exp["latest_performance"] = dict(perf)
        exp["updated_at"] = _now()
        minimum = max(1, int(exp.get("minimum_trial_trades") or state.get("minimum_trial_trades", 20)))
        if int(exp.get("observed_trades") or 0) >= minimum:
            baseline_pf = _f((exp.get("baseline") if isinstance(exp.get("baseline"), Mapping) else {}).get("profit_factor"), 0.0)
            current_pf = _f(stats.get("profit_factor"), 0.0)
            improved = current_pf >= max(1.0, baseline_pf)
            exp["lifecycle_status"] = "KLAR_FOR_VURDERING" if improved else "PARALLELLTESTET"
            exp["conclusion"] = "FORBEDRET" if improved else "IKKE_DOKUMENTERT_FORBEDRING"
            hypotheses = _read(HYPOTHESES_PATH, [])
            if isinstance(hypotheses, list):
                hypothesis = next((h for h in hypotheses if h.get("hypothesis_id") == exp.get("hypothesis_id")), None)
                if hypothesis:
                    hypothesis["lifecycle_status"] = exp["lifecycle_status"]
                    hypothesis["parallel_test_result"] = exp["conclusion"]
                _write(HYPOTHESES_PATH, hypotheses)
        changed = True
    if changed:
        _write(EXPERIMENTS_PATH, experiments)
    return experiments


def generate_management_report(force: bool = False) -> dict[str, Any] | None:
    state = load_state()
    frequency = str(state.get("management_report_frequency") or "DAILY").upper()
    if frequency == "OFF" and not force:
        return None
    last = _parse_time(state.get("last_management_report_at"))
    now = datetime.now(timezone.utc).astimezone()
    due_hours = 24 if frequency == "DAILY" else 24 * 7
    if not force and last and (now - last).total_seconds() < due_hours * 3600:
        return None
    trades = _closed_trades()
    stats = _stats(trades)
    perf = calculate_performance()
    hypotheses = _read(HYPOTHESES_PATH, [])
    experiments = _read(EXPERIMENTS_PATH, [])
    versions = _read(VERSIONS_PATH, [])
    active_tests = [e for e in experiments if e.get("status") in {"TESTING", "TRIAL"}] if isinstance(experiments, list) else []
    open_h = [h for h in hypotheses if h.get("status") in {"NEW", "TESTING", "TRIAL"}] if isinstance(hypotheses, list) else []
    champion = next((v for v in versions if v.get("status") == "CHAMPION"), None) if isinstance(versions, list) else None
    observations = []
    if stats["expectancy"] < 0: observations.append("Negativ expectancy krever forsiktig kapitalbruk.")
    if stats["profit_factor"] < 1 and stats["trades"] >= int(state.get("warning_min_closed_trades", 10)): observations.append("Profit Factor er under 1,0.")
    if _f(perf.get("drawdown_pct")) >= load_parameters().maximum_drawdown_pct * 0.75: observations.append("Drawdown nærmer seg maksimalgrensen.")
    if not observations: observations.append("Ingen kritiske lærings- eller risikohendelser i perioden.")
    report = {
        "report_id": "MR-" + uuid.uuid4().hex[:10], "created_at": _now(), "frequency": frequency,
        "mode": state.get("mode"), "closed_trades": len(trades), "statistics": stats, "performance": perf,
        "open_hypotheses": len(open_h), "active_experiments": len(active_tests),
        "champion_version_id": champion.get("version_id") if champion else None,
        "observations": observations,
        "recommendation": "Fortsett kontrollert testing" if active_tests else "Samle flere observasjoner og vurder nye hypoteser",
    }
    reports = _read(REPORTS_PATH, [])
    reports = reports if isinstance(reports, list) else []
    reports.insert(0, report); _write(REPORTS_PATH, reports[:365])
    state["last_management_report_at"] = report["created_at"]; _write(STATE_PATH, state)
    _audit("MANAGEMENT_REPORT_CREATED", report)
    drawdown_text = f"{_f(perf.get('drawdown_pct')):.2f}".replace(".", ",")
    _notify(
        "Autonomi: læringsrapport",
        "\n".join([
            f"{len(open_h)} åpne hypoteser, {len(active_tests)} aktive tester, drawdown {drawdown_text} %.",
            f"Rapport-ID: {report['report_id']}",
            f"Programversjon: {APP_VERSION}",
            f"Rapporttid: {report['created_at']}",
        ]),
        report,
    )
    return report


def run_automatic_learning_if_due(trigger: str = "APP", force: bool = False) -> dict[str, Any]:
    state = load_state()
    if not state.get("enabled") or not state.get("automatic_evaluation", True):
        return {"ran": False, "reason": "Læring eller automatisk evaluering er av"}
    last = _parse_time(state.get("last_evaluation_at"))
    interval = max(1, int(state.get("evaluation_interval_minutes", 60)))
    now = datetime.now(timezone.utc).astimezone()
    if not force and last and (now - last).total_seconds() < interval * 60:
        generate_management_report(False)
        return {"ran": False, "reason": "Ikke forfalt"}
    result = evaluate_learning(trigger=trigger)
    report = generate_management_report(False)
    return {"ran": True, "evaluation": result, "management_report": report}


def evaluate_learning(trigger: str = "MANUAL") -> dict[str, Any]:
    state = load_state(); perf = calculate_performance(); trades = _closed_trades(); stats = _stats(trades); actions: list[Any] = []
    policy = _mode_policy(state)
    ensure_champion_version()
    experiments = _refresh_experiments(state, perf, stats)
    if state.get("enabled") and not state.get("emergency_stop", False):
        created = generate_hypotheses() if policy.get("auto_hypothesis") else []
        if created: actions.append({"type": "HYPOTHESES_CREATED", "count": len(created)})
        # Safety actions are allowed in assisted/full modes, but observer only reports.
        risk_trigger = perf.get("drawdown_pct", 0) >= load_parameters().maximum_drawdown_pct * 0.75 or (len(trades) >= state["warning_min_closed_trades"] and stats["expectancy"] < 0)
        if state.get("auto_risk_protection") and risk_trigger:
            if policy["observe_only"]:
                actions.append({"type": "RISK_WARNING", "reason": "Drawdown/negativ expectancy trigger", "applied": False})
            else:
                p = load_parameters(); reduced = max(0.5, p.maximum_position_pct * float(state["risk_reduction_factor"]))
                if reduced < p.maximum_position_pct:
                    action = {"type": "RISK_REDUCTION_PROPOSED", "parameter": "maximum_position_pct", "before": p.maximum_position_pct, "after": reduced, "reason": "Drawdown/negativ expectancy trigger", "applied": False, "requires_explicit_user_approval": True}
                    actions.append(action); _audit("RISK_PROTECTION_PROPOSAL", action); _notify("Learning: risikoforslag", f"Forslag: maks posisjon {p.maximum_position_pct:.2f}% → {reduced:.2f}%. Ingen automatisk endring er utført.", action)
        hypotheses = _read(HYPOTHESES_PATH, []); hypotheses = hypotheses if isinstance(hypotheses, list) else []
        if policy["auto_challenger"] and len(trades) >= int(state["challenger_min_closed_trades"]):
            candidate = next((h for h in hypotheses if h.get("status") == "NEW"), None)
            if candidate:
                exp = start_challenger(candidate["hypothesis_id"]); actions.append({"type": "CHALLENGER_STARTED", "experiment_id": exp["experiment_id"]})
        hypotheses = _read(HYPOTHESES_PATH, []); hypotheses = hypotheses if isinstance(hypotheses, list) else []
        if policy["auto_trial"] and len(trades) >= int(state["trial_promotion_min_closed_trades"]):
            candidate = next((h for h in hypotheses if h.get("status") == "TESTING"), None)
            if candidate:
                trial = apply_trial(candidate["hypothesis_id"]); actions.append({"type": "SHADOW_TRIAL_CREATED", "version_id": trial["version_id"], "production_applied": False})
        if policy["auto_promote"] and len(trades) >= int(state["full_promotion_min_closed_trades"]):
            versions = _read(VERSIONS_PATH, []); versions = versions if isinstance(versions, list) else []
            trial = next((v for v in versions if v.get("status") == "TRIAL"), None)
            if trial:
                baseline = trial.get("baseline_performance") or {}
                enough = len(trades) >= int(state["full_promotion_min_closed_trades"])
                improved = _f(stats.get("profit_factor")) >= max(1.0, _f(baseline.get("profit_factor"), 0)) and _f(perf.get("drawdown_pct")) <= _f(baseline.get("drawdown_pct"), 0) + 1.0
                if enough and improved:
                    guard = _promotion_guard(trial, state)
                    if guard["requires_confirmation"]:
                        approval = _queue_promotion_approval(trial, guard)
                        actions.append({"type": "CHAMPION_APPROVAL_REQUIRED", "approval_id": approval["approval_id"], "guard": guard})
                    else:
                        approval = _queue_promotion_approval(trial, guard)
                        actions.append({"type": "CHAMPION_APPROVAL_REQUIRED", "approval_id": approval["approval_id"], "guard": guard})
        # Roll back a trial quickly when drawdown materially worsens.
        if policy["auto_rollback"]:
            versions = _read(VERSIONS_PATH, []); versions = versions if isinstance(versions, list) else []
            trial = next((v for v in versions if v.get("status") == "TRIAL"), None)
            if trial:
                baseline_dd = _f((trial.get("baseline_performance") or {}).get("drawdown_pct"))
                if _f(perf.get("drawdown_pct")) >= baseline_dd + _f(state.get("rollback_drawdown_delta_pct"), 3.0):
                    rb = rollback(); actions.append({"type": "AUTOMATIC_ROLLBACK", "version_id": rb["version_id"]})
    state["last_evaluation_at"] = _now(); state["last_action"] = actions[-1] if actions else "Ingen endring"; _write(STATE_PATH, state)
    result = {"timestamp": _now(), "trigger": trigger, "mode": state.get("mode"), "closed_trades": len(trades), "statistics": stats, "performance": perf, "actions": actions}
    _audit("LEARNING_EVALUATED", result)
    return result

def render_controlled_learning(namespace: str = "controlled_learning") -> None:
    import pandas as pd
    import streamlit as st

    def _k(name: str) -> str:
        # Stable keys are required so Streamlit keeps the selected value across reruns.
        # The caller supplies a unique namespace when the panel can be rendered elsewhere.
        return f"{namespace}_{name}"
    st.markdown("#### 🧪 Controlled Parameter Learning")
    storage_info = persistence_status()
    if storage_info.get("persistent"):
        st.caption("🔒 Innstillinger, læringsterskler og godkjenninger lagres persistent.")
    else:
        st.caption("⚠ Lokal lagring er aktiv; DATABASE_URL kreves for å overleve ny Render-deploy.")
    st.caption("Fast Learning / Safe Promotion. Rask risikobeskyttelse, trinnvis testing og varslede endringer. Kun teoretisk autonom portefølje.")
    state = load_state(); trades = _closed_trades(); stats = _stats(trades)
    run_automatic_learning_if_due(trigger="UI_RENDER", force=False)
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Læring", "NØDSTOPP" if state.get("emergency_stop") else ("AKTIV" if state["enabled"] else "AV"))
    c2.metric("Lukkede handler", len(trades)); c3.metric("Expectancy", f"{stats['expectancy']:,.0f}")
    c4.metric("Profit Factor", f"{stats['profit_factor']:.2f}"); c5.metric("Siste evaluering", str(state.get("last_evaluation_at") or "–")[:16])

    overview_tab, settings_tab, approvals_tab = st.tabs(["Læring og eksperimenter", "⚙️ Autonomy Settings", "🛡️ Godkjenninger"])
    with settings_tab:
        st.markdown("##### Autonomy Settings")
        st.caption("Styr driftsmodus, automatiske tillatelser, sikkerhetsgrenser, varsling, evaluering og nødstopp.")
        mode_labels = {"OBSERVER": "🟢 Observatør", "ASSISTED": "🟡 Assistert autonomi", "FULL": "🔴 Full autonomi"}
        a,b,c = st.columns(3)
        enabled_key = _k("cpl_enabled_v18689b")
        mode_key = _k("cpl_mode_v18689b")

        def _persist_enabled() -> None:
            latest = load_state()
            latest["enabled"] = bool(st.session_state.get(enabled_key, False))
            save_state(latest)
            _audit("AUTONOMY_SETTING_CHANGED", {"field": "enabled", "value": latest["enabled"], "source": "UI_ON_CHANGE"})

        def _persist_mode() -> None:
            latest = load_state()
            value = str(st.session_state.get(mode_key) or "ASSISTED")
            if value not in mode_labels:
                value = "ASSISTED"
            latest["mode"] = value
            save_state(latest)
            _audit("AUTONOMY_SETTING_CHANGED", {"field": "mode", "value": value, "source": "UI_ON_CHANGE"})

        enabled = a.toggle(
            "Aktiver kontrollert læring",
            value=bool(state["enabled"]),
            key=enabled_key,
            on_change=_persist_enabled,
        )
        selected_mode = b.selectbox(
            "Driftsmodus",
            list(mode_labels),
            index=list(mode_labels).index(str(state.get("mode") or "ASSISTED")),
            format_func=lambda x: mode_labels[x],
            key=mode_key,
            on_change=_persist_mode,
        )
        emergency = c.toggle("🛑 Nødstopp", value=bool(state.get("emergency_stop", False)), key=_k("cpl_emergency_v18689b"), help="Stopper automatiske læringshandlinger umiddelbart. Teoretisk portefølje kan pauses separat.")
        if emergency and not state.get("emergency_stop", False):
            try:
                from autonomous_portfolio import set_status
                set_status(False, "Nødstopp aktivert i Autonomy Settings")
            except Exception:
                pass
        st.caption({"OBSERVER":"Observerer, varsler og foreslår – endrer ingen parametere.", "ASSISTED":"Starter Challengers og prøvemodus automatisk; Champion krever godkjenning.", "FULL":"Kan starte tester, aktivere prøvemodus og promotere Champion, men store eller vesentlige risikoendringer krever bekreftelse."}[selected_mode])

        st.markdown("###### Tillatte automatiske handlinger")
        p1,p2,p3,p4,p5 = st.columns(5)
        allow_h = p1.toggle("Hypoteser", value=bool(state.get("allow_hypothesis_creation", True)), key=_k("cpl_allow_h_v18689b"))
        allow_c = p2.toggle("Challengers", value=bool(state.get("allow_auto_challenger", True)), key=_k("cpl_allow_c_v18689b"))
        allow_t = p3.toggle("Prøvemodus", value=bool(state.get("allow_auto_trial", True)), key=_k("cpl_allow_t_v18689b"))
        allow_p = p4.toggle("Champion-promotering", value=bool(state.get("allow_auto_promotion", True)), key=_k("cpl_allow_p_v18689b"))
        rollback_on = p5.toggle("Rollback", value=bool(state.get("auto_rollback", True)), key=_k("cpl_rollback_v18689b"))

        st.markdown("###### Sikkerhetsgrenser for Champion-promotering")
        s1,s2,s3 = st.columns(3)
        confirmation = s1.toggle("Krev bekreftelse ved stor endring", value=bool(state.get("require_confirmation_major_change", True)), key=_k("cpl_confirm_v18689b"))
        major_share = float(s2.number_input("Stor endring over (%)", 1.0, 100.0, float(state.get("major_change_parameter_share_pct", 20.0)), 1.0, key=_k("cpl_major_share_v18689b")))
        material_risk = float(s3.number_input("Vesentlig risikoendring over (%)", 1.0, 100.0, float(state.get("material_risk_change_pct", 10.0)), 1.0, key=_k("cpl_material_risk_v18689b")))
        st.info("Alle produksjonsendringer settes på vent og krever eksplisitt brukergodkjenning. Risiko-, kjøpsterskel-, stop-loss-, posisjons- og autonomiregler kan aldri endres automatisk.")

        st.markdown("###### Evaluering og varsling")
        e1,e2,e3,e4 = st.columns(4)
        automatic = e1.toggle("Automatisk evaluering", value=bool(state.get("automatic_evaluation", True)), key=_k("cpl_auto_eval_v18689b"))
        interval = int(e2.number_input("Evaluer hvert minutt", 1, 10080, int(state.get("evaluation_interval_minutes", 60)), 5, key=_k("cpl_interval_v18689b")))
        report_freq = e3.selectbox("AI-sjef rapport", ["OFF", "DAILY", "WEEKLY"], index=["OFF", "DAILY", "WEEKLY"].index(str(state.get("management_report_frequency") or "DAILY")), format_func=lambda x: {"OFF":"Av", "DAILY":"Daglig", "WEEKLY":"Ukentlig"}[x], key=_k("cpl_report_freq_v18689b"))
        notification_level = e4.selectbox("Varslingsnivå", ["ALL", "IMPORTANT", "CRITICAL"], index=["ALL", "IMPORTANT", "CRITICAL"].index(str(state.get("notification_level") or "ALL")), format_func=lambda x: {"ALL":"Alle hendelser", "IMPORTANT":"Viktige", "CRITICAL":"Kun kritiske"}[x], key=_k("cpl_notification_v18689b"))
        risk = st.toggle("Automatisk risikobeskyttelse", value=bool(state["auto_risk_protection"]), key=_k("cpl_risk_v18689b"))

        with st.expander("Adaptive læringsterskler", expanded=False):
            cols = st.columns(5)
            keys = [("warning_min_closed_trades","Tidlig varsel"),("hypothesis_min_closed_trades","Hypotese"),("challenger_min_closed_trades","Challenger"),("trial_promotion_min_closed_trades","Prøvemodus"),("full_promotion_min_closed_trades","Full Champion")]
            values = {}
            for col,(key,label) in zip(cols,keys): values[key] = int(col.number_input(label, 1, 1000, int(state[key]), 1, key=f"cpl_{key}_v18689b"))

        es1, es2 = st.columns(2)
        if es1.button("🛑 Aktiver nødstopp nå", width="stretch", key=_k("cpl_emergency_on_v18689b")):
            state["emergency_stop"] = True
            state["enabled"] = False
            save_state(state)
            try:
                from autonomous_portfolio import set_status
                set_status(False, "Nødstopp aktivert i Autonomy Settings")
            except Exception:
                pass
            _audit("AUTONOMY_EMERGENCY_STOP_ACTIVATED", {"source": "UI"})
            _notify("Autonomi: NØDSTOPP", "Automatisk læring og den teoretiske porteføljen er pauset.", {"source": "UI"})
            st.error("Nødstopp er aktivert."); st.rerun()
        if es2.button("Opphev nødstopp", width="stretch", key=_k("cpl_emergency_off_v18689b")):
            state["emergency_stop"] = False
            save_state(state)
            _audit("AUTONOMY_EMERGENCY_STOP_RELEASED", {"source": "UI"})
            st.success("Nødstopp er opphevet. Porteføljen må aktiveres separat."); st.rerun()

        if st.button("Lagre Autonomy Settings", type="primary", width="stretch", key=_k("cpl_save_settings_v18689b")):
            state.update({
                "enabled": enabled, "mode": selected_mode, "emergency_stop": emergency,
                "allow_hypothesis_creation": allow_h, "allow_auto_challenger": allow_c,
                "allow_auto_trial": allow_t, "allow_auto_promotion": allow_p,
                "auto_rollback": rollback_on, "require_confirmation_major_change": confirmation,
                "major_change_parameter_share_pct": major_share, "material_risk_change_pct": material_risk,
                "automatic_evaluation": automatic, "evaluation_interval_minutes": interval,
                "management_report_frequency": report_freq, "notification_level": notification_level,
                "auto_risk_protection": risk, **values,
            })
            save_state(state); st.success("Autonomy Settings er lagret."); st.rerun()

    with approvals_tab:
        approvals = _read(APPROVALS_PATH, [])
        approvals = approvals if isinstance(approvals, list) else []
        pending = [a for a in approvals if a.get("status") == "PENDING"]
        st.markdown("##### Ventende Champion-godkjenninger")
        if not pending:
            st.info("Ingen ventende godkjenninger.")
        if pending:
            from approval_governance_ui import render_approval_card, inject_approval_mobile_css
            inject_approval_mobile_css()
            for item in pending:
                enriched = dict(item)
                enriched.setdefault("approval_source", "LEARNING")
                render_approval_card(enriched, key_prefix="learning_portfolio", compact=False)
        if approvals:
            st.dataframe(pd.DataFrame(approvals), width="stretch", hide_index=True)

    with overview_tab:
        x,y,z = st.columns(3)
        if x.button("Evaluer nå", type="primary", width="stretch", key=_k("cpl_eval_v18689b")):
            result = evaluate_learning(); st.success(f"Evaluert {result['closed_trades']} lukkede handler. {len(result['actions'])} handlinger."); st.rerun()
        if y.button("Generer hypoteser", width="stretch", key=_k("cpl_hyp_v18689b")):
            created = generate_hypotheses(); st.success(f"{len(created)} nye hypoteser opprettet."); st.rerun()
        if z.button("Rollback til Champion", width="stretch", key=_k("cpl_rb_v18689b")):
            try: rollback(); st.success("Rollback utført."); st.rerun()
            except ValueError as exc: st.warning(str(exc))
        hypotheses = _read(HYPOTHESES_PATH, []); experiments = _read(EXPERIMENTS_PATH, []); versions = _read(VERSIONS_PATH, [])
        t1,t2,t3,t4 = st.tabs(["Hypoteser", "Eksperimenter", "Parameterhistorikk", "AI-sjef rapporter"])
        with t1:
            if hypotheses:
                st.dataframe(pd.DataFrame(hypotheses), width="stretch", hide_index=True)
                choices = {f"{h['hypothesis_id']} · {h['parameter']} {h['before']} → {h['after']} ({h['status']})": h for h in hypotheses if h.get("status") in {"NEW","TESTING"}}
                if choices:
                    label = st.selectbox("Velg hypotese", list(choices), key=_k("cpl_select_h_v18689b")); h = choices[label]
                    p,q = st.columns(2)
                    if p.button("Start Challenger", key=_k("cpl_start_ch_v18689b")):
                        start_challenger(h["hypothesis_id"]); st.success("Challenger startet."); st.rerun()
                    if q.button("Aktiver i prøvemodus", key=_k("cpl_trial_v18689b")):
                        apply_trial(h["hypothesis_id"]); st.success("Midlertidig parameterendring aktivert og varslet."); st.rerun()
            else: st.info("Ingen hypoteser ennå. Modulen venter på nok lukkede handler eller manuell evaluering.")
        with t2:
            if experiments: st.dataframe(pd.DataFrame(experiments), width="stretch", hide_index=True)
            else: st.caption("Ingen eksperimenter.")
        with t3:
            if versions: st.dataframe(pd.DataFrame(versions), width="stretch", hide_index=True)
            else: st.caption("Champion opprettes ved første evaluering.")
            if st.button("Send aktiv prøveversjon til godkjenning", key=_k("cpl_promote_v18689b")):
                try:
                    trial = next((v for v in versions if v.get("status") == "TRIAL"), None)
                    if not trial: raise ValueError("Ingen aktiv parallelltest.")
                    approval = _queue_promotion_approval(trial, _promotion_guard(trial, state))
                    st.success(f"Godkjenning opprettet: {approval.get('approval_id')}"); st.rerun()
                except (ValueError, PermissionError) as exc: st.warning(str(exc))
        with t4:
            reports = _read(REPORTS_PATH, [])
            r1, r2 = st.columns(2)
            if r1.button("Generer rapport nå", width="stretch", key=_k("cpl_report_now_v18689b")):
                generate_management_report(force=True); st.success("Læringsrapport opprettet og varslet."); st.rerun()
            if r2.button("Kjør full automatisk evaluering nå", width="stretch", key=_k("cpl_auto_now_v18689b")):
                run_automatic_learning_if_due(trigger="MANUAL_FORCE", force=True); st.success("Automatisk evalueringsløp fullført."); st.rerun()
            if reports:
                latest = reports[0]
                st.markdown(f"**Siste rapport:** {latest.get('created_at','–')} · {latest.get('mode','–')}")
                for observation in latest.get("observations", []): st.write(f"- {observation}")
                st.json(latest, expanded=False)
                st.dataframe(pd.DataFrame(reports[:100]), width="stretch", hide_index=True)
                st.download_button("Last ned rapporthistorikk JSON", json.dumps(reports, ensure_ascii=False, indent=2), "autonomous_management_reports.json", "application/json", key=_k("cpl_reports_json_v18689b"))
            else:
                st.info("Ingen AI-sjef-rapporter ennå.")
