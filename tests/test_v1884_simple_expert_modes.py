from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_user_mission_filters_risk_and_localized_sector_without_hiding_observation():
    from autonomi_core.missions.user_mission import apply_user_mission

    candidates = [
        {"ticker": "SAFE", "risk_score": 20, "sector": "Technology", "valid_for_decision": True, "status": "ANBEFALT FOR VURDERING"},
        {"ticker": "RISK", "risk_score": 70, "sector": "Technology", "valid_for_decision": True, "status": "ANBEFALT FOR VURDERING"},
        {"ticker": "BANK", "risk_score": 20, "sector": "Financial Services", "valid_for_decision": True, "status": "ANBEFALT FOR VURDERING"},
    ]
    summary = apply_user_mission(candidates, {
        "mission_id": "UM-TEST", "goal": "Kapitalvekst", "horizon": "1–3 år",
        "risk": "Forsiktig", "risk_ceiling": 40, "sectors": ["Teknologi"],
    })
    assert summary["eligible"] == 1
    assert summary["excluded"] == 2
    assert candidates[0]["mission_eligible"] is True
    assert candidates[1]["status"] == "UTENFOR VALGT OPPDRAG"
    assert candidates[2]["mission_fit"]["reasons"] == ["Utenfor valgte bransjer"]


def test_no_user_mission_preserves_all_candidates():
    from autonomi_core.missions.user_mission import apply_user_mission

    candidates = [{"ticker": "A"}, {"ticker": "B"}]
    summary = apply_user_mission(candidates, {})
    assert summary == {"active": False, "eligible": 2, "excluded": 0, "reasons": {}}
    assert all(row["mission_eligible"] for row in candidates)


def test_simple_mode_has_only_five_business_inputs_and_start_action():
    source = (ROOT / "autonomy_modes.py").read_text(encoding="utf-8")
    simple = source[source.index("def render_simple_mode"):source.index("def _latest_run")]
    for label in ("Mål", "Tidshorisont", "Risiko", "Markeder", "Eventuelle bransjer", "Start Autonomi"):
        assert label in simple
    assert "load_policy" not in simple
    assert "Faktorvekter" not in simple
    assert "start_manual_job" in simple


def test_expert_mode_exposes_required_technical_areas():
    source = (ROOT / "autonomy_modes.py").read_text(encoding="utf-8")
    expert = source[source.index("def render_expert_console"):]
    for label in ("Motorer", "Terskler", "Datakilder", "Strategier", "Faktorvekter", "Scheduler", "Shadow Mode", "Logger og diagnose"):
        assert label in expert


def test_app_hides_expert_workspaces_in_simple_mode():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("def render_autonomy_core_control_center_v1880")
    block = source[start:start + 5500]
    assert "interface_mode = render_mode_selector()" in block
    assert "if interface_mode != EXPERT:" in block
    assert "render_simple_mode()" in block
    assert block.index("render_simple_mode()") < block.index("workspace_labels = {")
    assert "return" in block[block.index("if interface_mode != EXPERT:"):block.index("workspace_labels = {")]


def test_job_profile_carries_mission_to_pipeline_and_decision_gate():
    source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
    assert 'user_mission_id: str = ""' in source
    assert "apply_user_mission(all_candidates, user_mission)" in source
    assert 'bool(x.get("mission_eligible", True))' in source
    assert '"mission_summary": mission_summary' in source
    assert 'Paragraph("Autonomi-oppdrag"' in source


def test_simple_mode_has_only_one_start_action():
    modes = (ROOT / "autonomy_modes.py").read_text(encoding="utf-8")
    overview = (ROOT / "autonomy_overview.py").read_text(encoding="utf-8")
    assert "render_autonomy_overview(allow_quick_start=False)" in modes
    assert "def render_autonomy_overview(*, allow_quick_start: bool = True)" in overview


def test_release_metadata_v1884():
    version = (ROOT / "app_version.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "v18.8.4"' in version
    assert 'APP_VERSION_NAME = "Enkel modus og ekspertmodus"' in version
