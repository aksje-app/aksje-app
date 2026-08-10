from types import SimpleNamespace

import controlled_parameter_learning as learning
from app_version import APP_VERSION


def test_learning_report_uses_norwegian_number_and_version(monkeypatch):
    captured = {}
    monkeypatch.setattr(learning, "_read", lambda path, default: default)
    monkeypatch.setattr(learning, "_write", lambda *args, **kwargs: None)
    monkeypatch.setattr(learning, "_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(learning, "calculate_performance", lambda: {"drawdown_pct": 0.12})
    monkeypatch.setattr(learning, "_closed_trades", lambda: [])
    monkeypatch.setattr(learning, "load_parameters", lambda: SimpleNamespace(maximum_drawdown_pct=12.0))
    monkeypatch.setattr(
        learning,
        "_notify",
        lambda title, message, payload: captured.update(title=title, message=message, payload=payload),
    )

    report = learning.generate_management_report(force=True)

    assert report is not None
    assert "drawdown 0,12 %." in captured["message"]
    assert f"Programversjon: {APP_VERSION}" in captured["message"]
    assert f"Rapport-ID: {report['report_id']}" in captured["message"]
    assert "0.12%" not in captured["message"]
