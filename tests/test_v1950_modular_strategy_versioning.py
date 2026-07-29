from __future__ import annotations

from pathlib import Path

import pytest

from app_core.context import build_renderer_context
from app_version import APP_VERSION, get_version_contract
from domain.strategy_versioning import (
    ExecutionMode,
    StrategyStatus,
    build_version_id,
    validate_strategy_version,
)
from repositories.application import RepositoryRegistry
from services.storage_service import StorageService
from services.strategy_registry_service import StrategyRegistryError, StrategyRegistryService


def _service(tmp_path) -> StrategyRegistryService:
    storage = StorageService(base_dir=tmp_path, database_url="", mode="local")
    return StrategyRegistryService(RepositoryRegistry(storage))


def test_version_contract_exposes_strategy_registry():
    assert APP_VERSION == "v19.14.4"
    contract = get_version_contract()
    assert contract["strategy_registry_version"] == "1.0"


def test_default_strategies_are_separate_and_persistent(tmp_path):
    service = _service(tmp_path)
    defaults = service.ensure_defaults()
    assert len(defaults) == 4
    technical = service.production_for_family("technical")
    autonomy = service.production_for_family("autonomy")
    assert technical["strategy_id"] == "technical_benchmark"
    assert autonomy["strategy_id"] == "autonomy_main"
    assert technical["version_id"] != autonomy["version_id"]
    assert technical["execution_mode"] == ExecutionMode.PAPER.value
    # Recreate service to prove repository persistence and idempotent bootstrap.
    recreated = _service(tmp_path)
    assert len(recreated.ensure_defaults()) == 4
    assert len(recreated.list_versions()) == 4


def test_challenger_is_shadow_read_only_and_does_not_replace_production(tmp_path):
    service = _service(tmp_path)
    service.ensure_defaults()
    production = service.production_for_family("technical")
    challenger = service.create_challenger(
        production["version_id"], "1.1.0", parameter_version="technical-params-1.1",
        description="Test bedre trendfilter", actor="tester",
    )
    assert challenger["status"] == StrategyStatus.SHADOW.value
    assert challenger["execution_mode"] == ExecutionMode.SHADOW_READ_ONLY.value
    assert challenger["metadata"]["production_applied"] is False
    assert service.production_for_family("technical")["version_id"] == production["version_id"]


def test_production_binding_is_locked_in_v1950(tmp_path):
    service = _service(tmp_path)
    service.ensure_defaults()
    production = service.production_for_family("autonomy")
    with pytest.raises(StrategyRegistryError):
        service.set_status(production["version_id"], "PAUSED", actor="tester")


def test_shadow_lifecycle_is_audited(tmp_path):
    service = _service(tmp_path)
    service.ensure_defaults()
    production = service.production_for_family("technical")
    challenger = service.create_challenger(production["version_id"], "1.2.0", actor="tester")
    changed = service.set_status(challenger["version_id"], "CHALLENGER", actor="tester", reason="klar for paralleltest")
    assert changed["status"] == "CHALLENGER"
    assert changed["execution_mode"] == "SHADOW_READ_ONLY"
    events = service.events.list(limit=20)
    assert any(row["event_type"] == "STRATEGY_STATUS_CHANGED" for row in events)
    assert any(row.get("reason") == "klar for paralleltest" for row in events)


def test_strategy_contract_rejects_writable_shadow():
    row = {
        "strategy_id": "technical_benchmark",
        "strategy_family": "technical",
        "display_name": "Teknisk benchmark",
        "strategy_version": "2.0.0",
        "parameter_version": "p2",
        "status": "SHADOW",
        "execution_mode": "PAPER",
        "implementation_version": "v19.5.0",
        "version_id": build_version_id("technical_benchmark", "2.0.0"),
    }
    result = validate_strategy_version(row)
    assert result["ok"] is False
    assert any("skrivebeskyttet" in error.lower() for error in result["errors"])


def test_renderer_context_does_not_expose_unreferenced_globals():
    def helper(value=42):
        return value

    def renderer():
        return helper()

    namespace = {"helper": helper, "secret_unrelated": "do not export"}
    context = build_renderer_context(namespace, renderer, services=None)
    assert context["helper"]() == 42
    assert "helper" in context
    assert "secret_unrelated" not in context
    assert context.diagnostics()["renderer"].endswith("renderer")


def test_app_monolith_is_reduced_and_style_layers_are_external():
    app = Path("app.py").read_text(encoding="utf-8")
    styles = Path("ui/global_styles.py").read_text(encoding="utf-8")
    assert len(app.splitlines()) < 19050
    assert "inject_foundation_styles_v1950" in app
    assert "def _inject_visual_truth_fix_css_v18591" not in app
    assert "def _inject_visual_truth_fix_css_v18591" in styles
    assert "get_page_context_v1950(_implementation)" in app
    assert "_implementation(globals()" not in app


def test_autonomy_exposes_strategy_version_workspace():
    source = Path("pages/autonomy.py").read_text(encoding="utf-8")
    page = Path("pages/strategy_versions.py").read_text(encoding="utf-8")
    assert '"strategy_versions": "Strategiversjoner"' in source
    assert "render_strategy_versions(app_context)" in source
    assert "Automatisk promotering er av" in page


def test_paper_decision_is_stamped_with_technical_strategy(monkeypatch):
    import trading_engine
    monkeypatch.setattr(trading_engine, "score_signal", lambda item, context: {"decision": "HOLD", "score": 5})
    monkeypatch.setattr(
        trading_engine,
        "stamp_strategy_metadata",
        lambda row, family: {**row, "strategy_family": family, "strategy_id": "technical_benchmark", "strategy_version": "legacy-1.0.0"},
    )
    decision = trading_engine.build_trading_decision({"ticker": "EQNR.OL"}, {})
    assert decision["strategy_family"] == "technical"
    assert decision["strategy_id"] == "technical_benchmark"
    assert decision["strategy_version"] == "legacy-1.0.0"


def test_autonomy_trade_and_decision_paths_stamp_strategy_identity():
    source = Path("autonomous_portfolio.py").read_text(encoding="utf-8")
    assert 'stamp_strategy_metadata(trade, "autonomy")' in source
    assert 'stamp_strategy_metadata(raw, "autonomy")' in source
    assert 'row.setdefault("strategy_role", "AUTONOMY_MAIN")' in source
