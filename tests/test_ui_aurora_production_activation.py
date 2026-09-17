from ui_library.shell import use_v2_shell


def test_production_always_uses_aurora_shell(monkeypatch):
    monkeypatch.setenv("APP_ENVIRONMENT", "production")
    monkeypatch.setenv("AA_UI_SHELL_V2", "0")

    assert use_v2_shell() is True


def test_rollout_flag_remains_available_outside_production(monkeypatch):
    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.setenv("AA_UI_SHELL_V2", "0")

    assert use_v2_shell() is False
