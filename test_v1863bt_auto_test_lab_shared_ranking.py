from pathlib import Path
import py_compile

from auto_test_lab import (
    attach_shared_ranking_to_auto_lab_result,
    auto_lab_rows_to_ranking_rows,
    rank_auto_lab_rows,
    run_auto_test_lab,
)


def test_auto_lab_rows_map_decision_quality_and_invert_risk_pressure():
    rows = auto_lab_rows_to_ranking_rows(
        [
            {
                "ticker": "risk.ol",
                "name": "Risk ASA",
                "decision_quality": 72,
                "ai_score": 7.2,
                "smart_score": 70,
                "momentum_score": 64,
                "risk_score": 25,
                "event_score": 80,
                "data_quality": 70,
                "grade": "Middels",
                "action": "Test videre",
            }
        ],
        source="Auto Test Lab Aksjer",
        scope="Norge",
        target="Balansert",
        test_mode="Normal",
    )

    row = rows[0]
    assert row["ticker"] == "RISK.OL"
    assert row["score"] == 72
    assert row["risk_score"] == 75
    assert row["source_scope"] == "Norge"
    assert row["evidence_items"][0]["type"] == "Auto Test Lab"
    assert "Normal" in row["signals"]


def test_rank_auto_lab_rows_returns_shared_ranking_with_internal_evidence():
    result = rank_auto_lab_rows(
        [
            {"ticker": "AAA.OL", "decision_quality": 88, "risk_score": 80, "event_score": 82, "data_quality": 80, "grade": "Hoy"},
            {"ticker": "BBB.OL", "decision_quality": 64, "risk_score": 40, "event_score": 60, "data_quality": 65, "grade": "Middels"},
        ],
        source="Auto Test Lab Aksjer",
        max_count=5,
    )

    assert result["status"] == "ok"
    assert result["ranked"][0]["ticker"] == "AAA.OL"
    assert result["ranked"][0]["evidence_summary"]["totalt"] == 1
    assert result["ranked"][0]["candidate"]["evidence_items"][0]["source"] == "Auto Test Lab Aksjer"


def test_run_auto_test_lab_attaches_shared_ranking_without_extra_provider_calls():
    calls = []
    data = {
        "AAA.OL": {
            "ticker": "AAA.OL",
            "name": "AAA",
            "score": 8.4,
            "smart_score": 82,
            "strength": 74,
            "risk_score": 20,
            "ret_1m": 0.04,
            "ret_3m": 0.08,
        },
        "BBB.OL": {
            "ticker": "BBB.OL",
            "name": "BBB",
            "score": 6.6,
            "smart_score": 62,
            "strength": 45,
            "risk_score": 55,
        },
    }

    def provider(ticker, use_news):
        calls.append((ticker, use_news))
        return data.get(ticker)

    result = run_auto_test_lab(
        ["AAA.OL", "BBB.OL"],
        score_provider=provider,
        test_mode="Rask",
        max_candidates=5,
        use_news=False,
    )

    assert calls == [("AAA.OL", False), ("BBB.OL", False)]
    assert result["status"] == "ok"
    assert result["shared_ranking"]["status"] == "ok"
    assert result["ranked"][0]["shared_rank"] == 1
    assert result["summary"]["shared_top_ticker"] == "AAA.OL"


def test_attach_shared_ranking_can_be_rebuilt_after_ui_adds_scope():
    result = {
        "scope": "Norge",
        "target": "Balansert",
        "test_mode": "Normal",
        "ranked": [
            {"ticker": "KOG.OL", "decision_quality": 84, "risk_score": 75, "event_score": 80, "data_quality": 90, "grade": "Hoy"}
        ],
        "summary": {},
    }

    attached = attach_shared_ranking_to_auto_lab_result(result, source="Auto Test Lab Aksjer")

    assert attached["shared_ranking"]["ranked"][0]["candidate"]["metadata"]["source_score"] == 84
    assert attached["shared_ranking_rows"][0]["shared_rank"] == 1
    assert attached["summary"]["shared_ranked_candidates"] == 1


def test_auto_test_lab_shared_ranking_static_guards():
    for name in ["auto_test_lab.py", "app.py"]:
        py_compile.compile(name, doraise=True)

    auto_lab = Path("auto_test_lab.py").read_text(encoding="utf-8", errors="ignore")
    app = Path("app.py").read_text(encoding="utf-8", errors="ignore")

    assert "attach_shared_ranking_to_auto_lab_result" in auto_lab
    assert "rank_auto_lab_rows" in auto_lab
    assert "import streamlit" not in auto_lab.lower()
    assert "latest_shared_rankings_v1863br" in app
    assert "auto_test_lab/latest_shared_ranking.json" in app
    assert "Felles ranking / testbenk" in app

    start = app.find("def render_auto_test_lab_control_center_v18536")
    end = app.find("# v18.5.43: Fund Selection Engine", start)
    block = app[start:end]
    assert "run_clicked = st.button" in block
    assert "if run_clicked:" in block
    assert block.find("run_auto_test_lab(") > block.find("if run_clicked:")





