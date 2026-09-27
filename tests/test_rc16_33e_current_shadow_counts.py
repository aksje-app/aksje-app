from __future__ import annotations

from quality_v2_shadow_store import record_shadow_run


def _result(disagreements=8, weakening=5, evaluated=20):
    rows = [{"ticker": f"X{i}.OL"} for i in range(evaluated)]
    return {
        "state": "COMPLETED",
        "generated_at": "2026-09-27T01:00:00+00:00",
        "run_key": "quality/test",
        "quality_v2_shadow": {
            "shadow_only": True,
            "evaluated": evaluated,
            "disagreement_count": disagreements,
            "weakening_count": weakening,
            "rows": rows,
        },
    }


def test_repeated_same_run_counts_stay_current_not_cumulative(monkeypatch):
    state = {
        "complete_runs": 2,
        "evaluated_companies": 40,
        "disagreement_count": 16,
        "weakening_count": 10,
    }
    monkeypatch.setattr("quality_v2_shadow_store.load_shadow_state", lambda: dict(state))
    written = {}
    monkeypatch.setattr("quality_v2_shadow_store.write_json", lambda key, path, value: written.update(value))
    monkeypatch.setattr("quality_v2_shadow_store.load_shadow_evaluation", lambda: {})
    out = record_shadow_run(_result())
    assert out["complete_runs"] == 3
    assert out["evaluated_companies"] == 20
    assert out["disagreement_count"] == 8
    assert out["weakening_count"] == 5
    assert out["evaluated_observations_total"] == 60
    assert out["disagreement_observations_total"] == 24
    assert out["weakening_observations_total"] == 15


def test_overview_labels_current_counts():
    src = open("pages/overview.py", encoding="utf-8").read()
    assert "VURDERT NÅ" in src
    assert "AKTIVE V1.1 ↔ V2 UENIGHETER" in src
    assert ("SVEKKENDE NÅ" in src or "AV DISSE: V2 SVAKERE" in src)
    assert "latest_shadow.get(\"disagreement_count\")" in src
