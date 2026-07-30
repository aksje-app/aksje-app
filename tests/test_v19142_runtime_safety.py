from __future__ import annotations

from pathlib import Path

import pytest

import app_version
import paper_store
import trading_engine
from paper_trading_guard import (
    PaperTradingDisabledError,
    check_paper_trade,
    clear_trade_registry,
    record_paper_trade,
)
from runtime_safety import (
    deployment_identity,
    notifications_allowed,
    paper_trading_decision,
    runtime_background_allowed,
    runtime_safety_snapshot,
    scheduler_allowed,
)

ROOT = Path(__file__).resolve().parents[1]
SAFETY_ENV = (
    "PAPER_TRADING_ENABLED", "ALLOW_PAPER_TRADING_IN_TEST", "APP_ENVIRONMENT",
    "DEPLOYMENT_ENVIRONMENT", "RENDER_ENVIRONMENT", "RENDER_SERVICE_NAME",
    "RENDER_GIT_BRANCH", "GIT_BRANCH", "BRANCH", "PUSHOVER_APP_TOKEN",
    "PUSHOVER_USER_KEY", "ALLOW_NOTIFICATIONS_IN_TEST", "DATABASE_URL",
    "ALLOW_DATABASE_IN_TEST", "REPORT_SCHEDULER_ENABLED", "ALLOW_SCHEDULER_IN_TEST",
    "RUNTIME_BACKGROUND_ENABLED", "ALLOW_BACKGROUND_IN_TEST",
)


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in SAFETY_ENV:
        monkeypatch.delenv(name, raising=False)


def test_version_contract_is_v19143() -> None:
    assert app_version.APP_VERSION == "v19.14.6"
    assert app_version.APP_VERSION_NAME == "PDF-avhengighet og ren oppstart"
    assert app_version.RANKING_MODEL_VERSION == app_version.APP_VERSION
    assert app_version.AUTONOMY_POLICY_VERSION == app_version.APP_VERSION


def test_paper_gate_is_fail_closed_for_missing_invalid_and_false(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    assert paper_trading_decision().allowed is False
    assert paper_trading_decision().code == "DISABLED"

    monkeypatch.setenv("PAPER_TRADING_ENABLED", "perhaps")
    assert paper_trading_decision().allowed is False
    assert paper_trading_decision().code == "INVALID_CONFIGURATION"

    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
    assert paper_trading_decision().allowed is False
    assert paper_trading_decision().label == "AV"


def test_paper_gate_requires_explicit_test_override(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
    assert paper_trading_decision().code == "TEST_ENVIRONMENT_BLOCK"
    monkeypatch.setenv("ALLOW_PAPER_TRADING_IN_TEST", "true")
    assert paper_trading_decision().allowed is True


def test_all_manual_order_entrypoints_stop_before_portfolio_read(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("APP_ENVIRONMENT", "production")
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")

    def forbidden(*args, **kwargs):
        raise AssertionError("portfolio must not be read when the global gate is off")

    monkeypatch.setattr(trading_engine, "load_portfolio", forbidden)
    cases = (
        lambda: trading_engine.paper_buy("AAPL", 100.0, 80),
        lambda: trading_engine.paper_sell("AAPL", 100.0),
        lambda: trading_engine.paper_buy_instrument("SPY", 500.0, 1000.0),
        lambda: trading_engine.paper_sell_instrument("SPY", 500.0),
    )
    for call in cases:
        ok, message = call()
        assert ok is False
        assert "deaktivert" in message.lower() or "blokkert" in message.lower()


def test_persistence_layer_is_defence_in_depth(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
    portfolio = {"trades": []}
    with pytest.raises(PaperTradingDisabledError):
        paper_store.add_trade(portfolio, {"type": "BUY", "ticker": "AAPL"})
    assert portfolio["trades"] == []


def test_automatic_buy_requires_auditable_candidate_context(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("APP_ENVIRONMENT", "production")
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
    denied = check_paper_trade("BUY", ticker="AAPL", source="scanner", automatic=True)
    assert denied.allowed is False
    assert denied.code == "MISSING_CANDIDATE_CONTEXT"

    candidate = {
        "portfolio_action": "BUY",
        "valid_for_decision": True,
        "evidence_valid_for_decision": True,
    }
    allowed = check_paper_trade("BUY", ticker="AAPL", source="scanner", automatic=True, candidate=candidate)
    assert allowed.allowed is True


def test_candidate_decision_and_evidence_are_hard_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("APP_ENVIRONMENT", "production")
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
    base = {"portfolio_action": "BUY", "valid_for_decision": True, "evidence_valid_for_decision": True}
    assert check_paper_trade("BUY", ticker="AAPL", candidate=base).allowed
    assert check_paper_trade("BUY", ticker="AAPL", candidate={**base, "portfolio_action": "REVIEW"}).code == "ACTION_NOT_BUY"
    assert check_paper_trade("BUY", ticker="AAPL", candidate={**base, "valid_for_decision": False}).code == "INVALID_MARKET_DATA"
    assert check_paper_trade("BUY", ticker="AAPL", candidate={**base, "evidence_valid_for_decision": False}).code == "INVALID_EVIDENCE"
    assert check_paper_trade("BUY", ticker="AAPL", candidate={**base, "autonomy_outcome_code": "OVERVÅKES_AUTOMATISK"}).code == "CANDIDATE_NOT_APPROVED"


def test_same_run_buy_sell_roundtrip_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("APP_ENVIRONMENT", "production")
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
    clear_trade_registry()
    record_paper_trade("BUY", ticker="AAPL", run_id="RUN-1")
    result = check_paper_trade("SELL", ticker="AAPL", run_id="RUN-1")
    assert result.allowed is False
    assert result.code == "SAME_RUN_ROUNDTRIP"


def test_test_environment_isolated_services_are_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    assert scheduler_allowed()[0] is False
    assert runtime_background_allowed()[0] is False
    assert notifications_allowed()[0] is False


def test_test_database_configuration_blocks_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/test")
    snapshot = runtime_safety_snapshot()
    assert snapshot["safe"] is False
    assert snapshot["database_allowed"] is False
    assert snapshot["blocking_violations"]


def test_deployment_identity_exposes_exact_branch_and_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("RENDER_SERVICE_NAME", "aksje-app-stabilisering")
    monkeypatch.setenv("RENDER_GIT_BRANCH", "stabilisering-v19-14-1-ren")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abcdef1234567890")
    identity = deployment_identity()
    assert identity["service"] == "aksje-app-stabilisering"
    assert identity["branch"] == "stabilisering-v19-14-1-ren"
    assert identity["commit"] == "abcdef1234567890"
    assert identity["commit_short"] == "abcdef12"


def test_ui_and_worker_sources_use_the_shared_runtime_truth() -> None:
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    scanner_source = (ROOT / "scanner_worker.py").read_text(encoding="utf-8")
    store_source = (ROOT / "paper_store.py").read_text(encoding="utf-8")
    assert "paper_trading_decision()" in app_source
    assert "return decision.label, decision.color" in app_source
    assert "paper_trading_decision()" in scanner_source
    assert '"candidate": _paper_candidate_context(result)' in scanner_source
    assert "require_paper_trade(" in store_source
    assert '"run_id": run_id' not in scanner_source


def test_remember_token_is_removed_from_shareable_url_and_banner_links() -> None:
    auth_source = (ROOT / "auth.py").read_text(encoding="utf-8")
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    banner_source = (ROOT / "ui" / "live_market_banner.py").read_text(encoding="utf-8")
    assert 'searchParams.delete("remember_token")' in auth_source
    assert "history.replaceState" in auth_source
    assert "st.context" in auth_source
    assert "SameSite=Lax" in auth_source
    assert "clearLegacyQuery();" in auth_source
    assert 'searchParams.set("remember_token"' not in auth_source
    assert 'remember_token=' not in app_source
    assert 'remember_token=' not in banner_source


def test_render_and_streamlit_configuration_lock_working_server_mode() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "streamlit==1.57.0" in requirements
    assert "useStarlette" not in config
    assert "STREAMLIT_SERVER_USE_STARLETTE" not in render
    assert 'value: "false"' in render
