from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_contract_validates_and_serializes_all_required_fields():
    from autonomi_core.missions.investment_mission import InvestmentMission

    mission = InvestmentMission(
        mission_id="IM-TEST", configuration_version="CFG-000007", search_for="undervurdert kvalitet",
        markets=("Norge",), sectors=("Energi",), strategy="Kvalitet til rimelig pris",
        horizon="1–3 år", risk="Balansert", risk_ceiling=65, portfolio_need="Ny sektor",
        minimum_data_quality=60, candidate_count=10, exclusions=("BAD.OL",),
        objective="Kapitalvekst", created_at="2026-07-22T10:00:00+00:00",
    )
    mission.validate(); payload = mission.to_dict()
    for field in ("mission_id", "configuration_version", "search_for", "markets", "sectors", "strategy", "horizon", "risk", "portfolio_need", "minimum_data_quality", "candidate_count", "exclusions"):
        assert field in payload
    assert payload["strategy_profile"]["focus"]


def test_all_seven_strategy_profiles_exist():
    from autonomi_core.missions.investment_mission import STRATEGY_PROFILES

    expected = {"Kvalitet til rimelig pris", "Strukturell vekst", "Midlertidig feilprising", "Bærekraftig utbytte", "Insiderbekreftet verdi", "Momentum med fundamental støtte", "Porteføljediversifisering"}
    assert set(STRATEGY_PROFILES) == expected


def test_pipeline_preserves_mission_and_configuration_version():
    from investment_pipeline import PipelineConfig

    config = PipelineConfig(mission_id="IM-X", configuration_version="CFG-000009").normalized()
    assert config.mission_id == "IM-X"
    assert config.configuration_version == "CFG-000009"


def test_engine_handoff_uses_identical_ids():
    from autonomi_core.missions.investment_mission import engine_handoff

    handoff = engine_handoff({"mission_id": "IM-X", "configuration_version": "CFG-7"}, ["Discovery", "Analysis", "Portfolio", "Reporting"])
    assert len({row["mission_id"] for row in handoff.values()}) == 1
    assert len({row["configuration_version"] for row in handoff.values()}) == 1


def test_run_stamps_and_guards_contract_across_every_layer():
    market = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
    pipeline = (ROOT / "investment_pipeline.py").read_text(encoding="utf-8")
    runtime = (ROOT / "autonomi_core/runtime/orchestrator.py").read_text(encoding="utf-8")
    background = (ROOT / "manual_job_background.py").read_text(encoding="utf-8")
    assert '"engine_handoff": engine_handoff' in market
    assert "Sentral konfigurasjon er endret" in market
    assert 'row["mission_id"] = cfg.mission_id' in pipeline
    assert '"configuration_version": governed_run.get' in runtime
    assert '"mission_id": result.get("mission_id")' in background


def test_release_metadata_v1886_contains_both_releases():
    version = (ROOT / "app_version.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "v18.8.' in version
    assert '"v18.8.5: Central Autonomy Configuration:' in version
    assert '"v18.8.6: Investment Mission Contract:' in version
