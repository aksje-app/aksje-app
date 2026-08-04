from analysis_explainability import build_candidate_explainability
from analysis_transparency import build_candidate_transparency
from daily_user_experience import ADVANCED_NAVIGATION


def sample():
    return {
        "ticker":"TEST.OL", "investment_score":78.4, "shared_rank":1, "portfolio_action":"WATCH",
        "positives":["Sterk kvalitet", "Positiv trend"], "risks":["Lav kildedekning"],
        "confidence_profile":{"decision_confidence":67},
        "evidence_passport":{"areas":{"news":{"status":"NOT_SEARCHED", "sources":[], "facts":[]}}},
    }

def test_explainability_is_attached_and_non_decisional():
    c=sample(); t=build_candidate_transparency(c); e=t["explainability"]
    assert e["schema_version"] == "19.21.0-rc1"
    assert e["rank_explanation"]["not_recalculated"] is True
    assert e["separation"]["model_score"] == 78.4
    assert "TEST.OL" in e["summary"]

def test_overview_and_reports_are_adjacent():
    slugs=[x[2] for x in ADVANCED_NAVIGATION]
    assert slugs[:2] == ["dashboard", "reports"]

def test_quick_switch_contract_present():
    text=open("workspace_layout.py", encoding="utf-8").read()
    assert "ai_cc_quick_group_v19210_" in text
    assert "Bytt arbeidsområde direkte" in text
