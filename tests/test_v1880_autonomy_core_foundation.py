from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_autonomy_core_target_structure_exists():
    expected = [
        "analysis_ranking", "configuration", "discovery_data",
        "learning_reporting", "missions", "portfolio_decisions", "runtime",
    ]
    for name in expected:
        assert (ROOT / "autonomi_core" / name / "__init__.py").is_file()


def test_market_pipeline_enters_through_autonomy_core():
    source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
    assert "from autonomi_core.runtime.orchestrator import execute_market_mission" in source
    assert 'run["autonomous_chain"] = execute_market_mission(' in source


def test_core_gateway_preserves_legacy_execution(monkeypatch):
    import autonomous_orchestrator
    from autonomi_core.runtime import orchestrator

    captured = {}

    def fake_legacy(market_run, **kwargs):
        captured.update(kwargs)
        return {"status": "OK", "source_run_id": market_run["run_id"]}

    monkeypatch.setattr(autonomous_orchestrator, "run_post_scan_chain", fake_legacy)
    monkeypatch.setattr(orchestrator, "load_policy", lambda: orchestrator.AutonomyPolicy())
    result = orchestrator.execute_market_mission(
        {"run_id": "MI-TEST", "candidates": []}, trigger="TEST",
        run_autonomous=True, run_learning=False, require_active_portfolio=True,
    )
    assert result["status"] == "OK"
    assert result["autonomy_core"]["version"] == "v19.14.3"
    assert result["autonomy_core"]["theoretical_only"] is True
    assert captured["run_learning"] is False


def test_policy_guardrails_are_explicit():
    from autonomi_core.configuration.policy import AutonomyPolicy

    policy = AutonomyPolicy()
    assert policy.theoretical_only is True
    assert policy.allow_automatic_model_approval is False
    assert policy.require_report_persistence is True


def test_autonomy_is_first_class_control_center_group():
    workspace = (ROOT / "workspace_layout.py").read_text(encoding="utf-8")
    sidebar = (ROOT / "ui_sidebar_stable.py").read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert '"Autonomi": _matching_panel_labels("autonomi")' in workspace
    assert '("Autonomi", "🧠 Autonomi – Kontrollsenter")' in sidebar
    assert '"🧠 Autonomi – Kontrollsenter", render_autonomy_core_control_center_v1880' in app
    assert "Velg arbeidsflate" in app


def test_release_version_is_v1880():
    source = (ROOT / "app_version.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "v18.8.' in source
    assert "v18.8.0: Autonomy Core Foundation" in source
