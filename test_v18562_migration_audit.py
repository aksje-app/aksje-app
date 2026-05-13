from pathlib import Path


def test_v18562_version_and_migration_docs_exist():
    import app_version
    assert app_version.APP_VERSION == "v18.5.74"
    assert Path("PROJECT_AUDIT_V18562.md").exists()
    assert Path("PORTFOLIO_INTELLIGENCE_ENGINE_ROADMAP.md").exists()
    assert Path("NEW_CHAT_START_PROMPT.txt").exists()


def test_v18562_roadmap_mentions_full_engine_gaps():
    text = Path("PORTFOLIO_INTELLIGENCE_ENGINE_ROADMAP.md").read_text(encoding="utf-8")
    for phrase in [
        "Stress Testing Engine",
        "Portfolio Construction",
        "Backtesting",
        "Risk Budgeting",
        "Governance",
    ]:
        assert phrase in text
