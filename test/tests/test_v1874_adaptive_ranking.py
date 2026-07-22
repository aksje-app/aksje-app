from datetime import datetime, timedelta, timezone

import adaptive_ranking as ar


def rows(n=120):
    start = datetime.now(timezone.utc) - timedelta(days=150)
    out=[]
    for i in range(n):
        insider = 20 + (i % 80)
        ret = (insider - 50) / 8
        out.append({
            "created_at": (start + timedelta(days=i)).isoformat(),
            "insider_score": insider,
            "news_score": 50,
            "ai_score": 50,
            "fundamental_score": 50,
            "technical_score": 50,
            "evaluations": {"30": {"return_pct": ret}},
        })
    return out


def base():
    return {"discovery":.28,"fundamental":.18,"research":.14,"validation":.17,"portfolio_fit":.13,"risk_adjustment":.08,"insider":.08,"news":.10}


def test_pending_does_not_change_production(tmp_path, monkeypatch):
    monkeypatch.setattr(ar, "ROOT", tmp_path)
    monkeypatch.setattr(ar, "STATE_PATH", tmp_path/"state.json")
    monkeypatch.setattr(ar, "PROPOSALS_PATH", tmp_path/"proposals.json")
    monkeypatch.setattr(ar, "AUDIT_PATH", tmp_path/"audit.json")
    result=ar.build_proposal(rows(), base(), force=True)
    assert result["created"] and result["status"] == "PENDING"
    weights, meta=ar.get_active_weights(base())
    assert meta["mode"] == "STANDARD"
    assert abs(weights["insider"] - ar._normalize(base())["insider"]) < 1e-9


def test_manual_approval_activates_and_rollback(tmp_path, monkeypatch):
    monkeypatch.setattr(ar, "ROOT", tmp_path)
    monkeypatch.setattr(ar, "STATE_PATH", tmp_path/"state.json")
    monkeypatch.setattr(ar, "PROPOSALS_PATH", tmp_path/"proposals.json")
    monkeypatch.setattr(ar, "AUDIT_PATH", tmp_path/"audit.json")
    proposal=ar.build_proposal(rows(), base(), force=True)
    ar.set_proposal_status(proposal["proposal_id"], "TEST")
    _, meta=ar.get_active_weights(base())
    assert meta["mode"] == "STANDARD"
    ar.set_proposal_status(proposal["proposal_id"], "APPROVED")
    weights, meta=ar.get_active_weights(base())
    assert meta["mode"] == "APPROVED"
    assert meta["proposal_id"] == proposal["proposal_id"]
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    ar.rollback_active_model()
    _, meta=ar.get_active_weights(base())
    assert meta["mode"] == "STANDARD"


def test_guardrails_require_history(tmp_path, monkeypatch):
    monkeypatch.setattr(ar, "ROOT", tmp_path)
    monkeypatch.setattr(ar, "STATE_PATH", tmp_path/"state.json")
    monkeypatch.setattr(ar, "PROPOSALS_PATH", tmp_path/"proposals.json")
    monkeypatch.setattr(ar, "AUDIT_PATH", tmp_path/"audit.json")
    result=ar.build_proposal(rows(10), base())
    assert not result["created"]
    assert result["status"] == "INSUFFICIENT_DATA"
