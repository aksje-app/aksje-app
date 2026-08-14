import copy
import sys
import types
from pathlib import Path

from app_version import APP_VERSION
from autonomous_portfolio import (
    AutonomousParameters,
    _fmt_nb_money,
    _fmt_nb_number,
    recommended_production_profile,
)


ROOT = Path(__file__).resolve().parents[1]


def test_release_version():
    assert APP_VERSION == "v19.22.0-rc16.31h"


def test_recommended_profile_changes_only_reviewed_production_fields():
    current = AutonomousParameters(
        initial_cash=2_000_000,
        minimum_data_quality=55,
        maximum_open_positions=30,
        reserve_cash_pct=5,
        stop_loss_pct=3.5,
        trailing_stop_pct=4.5,
        learning_probe_minimum_score=64,
        learning_probe_notional_value=12_345,
        notify_trades=False,
    )
    profile = recommended_production_profile(current)
    assert profile.initial_cash == 2_000_000
    assert profile.minimum_investment_score == 73
    assert profile.minimum_data_quality == 70
    assert profile.maximum_risk_score == 65
    assert profile.maximum_position_pct == 3
    assert profile.maximum_open_positions == 20
    assert profile.reserve_cash_pct == 10
    assert profile.stop_loss_pct == 5
    assert profile.trailing_stop_pct == 7
    assert profile.take_profit_pct == 14
    assert profile.learning_probe_minimum_score == 64
    assert profile.learning_probe_notional_value == 12_345
    assert profile.notify_trades is False


def test_norwegian_financial_format_has_two_decimals():
    assert _fmt_nb_money(1234.5) == "1 234,50 kr"
    assert _fmt_nb_number(-12.345, 2) == "-12,35"


def test_return_baseline_and_graph_are_bound_to_active_portfolio():
    source = (ROOT / "autonomous_portfolio.py").read_text(encoding="utf-8")
    assert 'portfolio_initial_cash = _f(portfolio.get("initial_cash")) or perf["equity"]' in source
    assert 'hist_df["Utvikling %"]' in source
    assert 'start_value = _f(params.initial_cash' not in source
    assert "Startkapital ved neste RESET" in source


def test_currency_alerts_use_three_decimals_end_to_end():
    service = (ROOT / "currency_alert_service.py").read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'Kurs: {rate:.3f}' in service
    assert '{rate:.3f} <= {lower:.3f}' in service
    assert 'format="%.3f"' in app
    block = app[app.index("def render_currency_alerts_control_center_v1863af"):app.index("# v18.5.37")]
    assert "Kurs: {rate:.2f}" not in block
    assert "Grenser: {lower_v:.2f}" not in block


def test_known_legacy_profile_has_scoped_one_time_migration():
    source = (ROOT / "autonomous_portfolio.py").read_text(encoding="utf-8")
    assert "PARAMETERS_MIGRATED_RC16_31H" in source
    assert '"maximum_open_positions": 30.0' in source
    assert "recommended_production_profile(loaded)" in source
    assert "key in raw and abs" in source


def test_currency_notification_rounds_rate_and_limit_to_three_decimals(monkeypatch):
    sys.modules.setdefault("requests", types.SimpleNamespace(post=lambda *args, **kwargs: None))
    import currency_alert_service as service

    settings = {
        "currency_alerts_v1863af": [{
            "enabled": True,
            "pair": "BRL/NOK",
            "symbol": "BRLNOK=X",
            "lower": 1.8400,
            "upper": 2.0000,
            "cooldown_minutes": 0,
        }],
        service.STATE_KEY: {},
    }
    monkeypatch.setattr(service, "load_settings", lambda: copy.deepcopy(settings))

    def save(value):
        settings.clear()
        settings.update(copy.deepcopy(value))
        return True

    monkeypatch.setattr(service, "save_settings", save)
    monkeypatch.setattr(service, "_event", lambda *args, **kwargs: None)
    sent = []
    rows = service._run_currency_alert_checks_locked(
        force=True,
        notify=True,
        source="test",
        fetcher=lambda symbol: (1.83764, "test", "2026-08-14T00:00:00+00:00"),
        sender=lambda message, title=None: sent.append((title, message)) or (True, "ok"),
    )
    assert rows[0]["status"] == "breach_lower"
    assert sent
    assert "Kurs: 1.838" in sent[0][1]
    assert "1.838 <= 1.840" in sent[0][1]
