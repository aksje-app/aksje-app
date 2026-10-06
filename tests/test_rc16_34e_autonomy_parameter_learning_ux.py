from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import controlled_parameter_learning as cpl
from app_version import APP_VERSION, PREVIOUS_APP_VERSION
from autonomous_portfolio import AutonomousParameters

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_release_identity_rc16_34e():
    assert APP_VERSION == "v19.22.0-rc16.34e"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.34d"


def test_production_parameters_are_rendered_before_activation_analysis():
    source = _source("autonomous_portfolio.py")
    render_start = source.index("def render_autonomous_portfolio")
    block = source[render_start:]
    controls = block.index("_render_production_parameter_controls_v1934e")
    analysis = block.index("_render_activation_analysis_v1980")
    assert controls < analysis
    assert 'with st.expander("Faste parametere"' not in block
    assert "Produksjonsparametere" in source
    assert "Maks posisjon %" in source
    assert "Parameterlagring aktiv" in source


def test_activation_tables_are_not_forced_side_by_side():
    source = _source("autonomous_portfolio.py")
    start = source.index("def _render_activation_analysis_v1980")
    end = source.index("def render_autonomous_portfolio", start)
    block = source[start:end]
    assert 'left, right = st.columns(2)' not in block
    assert '**Vanligste blokkeringer**' in block
    assert '**Simulerte scoregrenser**' in block


def test_learning_report_separates_paper_and_learning_statistics():
    source = _source("controlled_parameter_learning.py")
    assert '"paper_statistics": dict(paper_snapshot.get("trade_statistics_pct") or {})' in source
    assert '"learning_statistics": stats' in source
    assert '"PAPER: treffrate' in source
    assert '"PRODUKSJON/LÆRING: Profit Factor' in source
    assert "PAPER – separat resultat" in source
    assert "PRODUKSJON/LÆRING – separat evidens" in source


def test_risk_proposal_approval_applies_parameter_only_after_explicit_decision(monkeypatch):
    rows = [{
        "proposal_id": "RP-TEST",
        "fingerprint": "maximum_position_pct|3.0|1.5|reason",
        "created_at": "2026-10-06T12:00:00+00:00",
        "updated_at": "2026-10-06T12:00:00+00:00",
        "status": "PENDING",
        "parameter": "maximum_position_pct",
        "before": 3.0,
        "after": 1.5,
        "reason": "reason",
        "evidence_closed_trades": 100,
        "evidence_mature_observations": 50,
    }]
    saved = []

    monkeypatch.setattr(cpl, "_risk_proposals", lambda: rows)
    monkeypatch.setattr(cpl, "_save_risk_proposals", lambda value: rows.__setitem__(slice(None), [dict(x) for x in value]))
    monkeypatch.setattr(cpl, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(cpl, "_notify", lambda *args, **kwargs: None)
    monkeypatch.setattr(cpl, "_current_evidence_counts", lambda: (100, 50))
    monkeypatch.setattr(cpl, "load_parameters", lambda: AutonomousParameters(maximum_position_pct=3.0))
    monkeypatch.setattr(cpl, "save_parameters", lambda p: saved.append(p) or p)

    import parameter_integrity
    monkeypatch.setattr(parameter_integrity, "write_approved_seal", lambda **kwargs: {"ok": True})

    result = cpl.resolve_risk_reduction_proposal("RP-TEST", "APPROVE", note="godkjent")
    assert result["status"] == "APPROVED"
    assert result["production_applied"] is True
    assert saved
    assert saved[-1].maximum_position_pct == 1.5


def test_rejected_proposal_can_return_only_after_new_evidence(monkeypatch):
    base = {
        "proposal_id": "RP-OLD",
        "fingerprint": "maximum_position_pct|3.0|1.5|reason",
        "created_at": "2026-10-06T12:00:00+00:00",
        "decided_at": "2026-10-06T12:00:00+00:00",
        "status": "REJECTED",
        "parameter": "maximum_position_pct",
        "before": 3.0,
        "after": 1.5,
        "reason": "reason",
        "evidence_closed_trades": 100,
        "evidence_mature_observations": 50,
    }
    state = cpl.default_state()

    monkeypatch.setattr(cpl, "_current_evidence_counts", lambda: (105, 52))
    eligible, _ = cpl._proposal_reeligible(base, state)
    assert eligible is False

    monkeypatch.setattr(cpl, "_current_evidence_counts", lambda: (120, 52))
    eligible, why = cpl._proposal_reeligible(base, state)
    assert eligible is True
    assert "20 nye avsluttede handler" in why


def test_block_choice_can_disable_future_learning_proposals(monkeypatch):
    rows = [{
        "proposal_id": "RP-BLOCK",
        "status": "PENDING",
        "parameter": "maximum_position_pct",
        "before": 3.0,
        "after": 1.5,
        "reason": "reason",
    }]
    state = cpl.default_state()
    monkeypatch.setattr(cpl, "_risk_proposals", lambda: rows)
    monkeypatch.setattr(cpl, "_save_risk_proposals", lambda value: None)
    monkeypatch.setattr(cpl, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(cpl, "_current_evidence_counts", lambda: (120, 60))
    monkeypatch.setattr(cpl, "load_state", lambda: state)
    monkeypatch.setattr(cpl, "save_state", lambda value: value)

    result = cpl.resolve_risk_reduction_proposal("RP-BLOCK", "BLOCK", note="ikke foreslå")
    assert result["status"] == "BLOCKED"
    assert "maximum_position_pct" in state["blocked_risk_parameters"]



def test_stale_risk_proposal_never_overwrites_newer_manual_value(monkeypatch):
    rows = [{
        "proposal_id": "RP-STALE",
        "status": "PENDING",
        "parameter": "maximum_position_pct",
        "before": 3.0,
        "after": 1.5,
        "reason": "reason",
    }]
    saved = []
    monkeypatch.setattr(cpl, "_risk_proposals", lambda: rows)
    monkeypatch.setattr(cpl, "_save_risk_proposals", lambda value: None)
    monkeypatch.setattr(cpl, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(cpl, "_notify", lambda *args, **kwargs: None)
    monkeypatch.setattr(cpl, "load_parameters", lambda: AutonomousParameters(maximum_position_pct=2.0))
    monkeypatch.setattr(cpl, "save_parameters", lambda p: saved.append(p) or p)

    result = cpl.resolve_risk_reduction_proposal("RP-STALE", "APPROVE", note="approve")
    assert result["status"] == "STALE"
    assert result["production_applied"] is False
    assert saved == []
    assert "aktiv verdi er nå 2.00%" in result["decision_note"]

def test_ui_exposes_approve_reject_defer_and_block_choices():
    autonomy = _source("autonomous_portfolio.py")
    learning = _source("controlled_parameter_learning.py")
    for token in ("Godkjenn forslag", "Avvis nå", "Utsett", "Ikke foreslå igjen", "Bekreft beslutning"):
        assert token in autonomy
        assert token in learning
    assert "Endringshistorikk og rollback" in autonomy
    assert "Rollback siste parameterendring" in autonomy
