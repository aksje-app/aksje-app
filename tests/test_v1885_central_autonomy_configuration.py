import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


class FakeStorage:
    def __init__(self, data=None):
        self.data = deepcopy(data or {})

    def read_json(self, key, default=None):
        return deepcopy(self.data.get(key, default))

    def write_json(self, key, value):
        self.data[key] = deepcopy(value)
        return True

    def health(self):
        return SimpleNamespace(backend="postgres", persistent=True, ok=True)


def _ready_document(registry):
    doc = registry._empty()
    doc["migration"] = {"complete": True, "sources": []}
    return doc


def test_versioned_update_approval_and_rollback(monkeypatch):
    from autonomi_core.configuration import registry

    fake = FakeStorage({registry.REGISTRY_KEY: _ready_document(registry)})
    monkeypatch.setattr(registry, "_storage", lambda: fake)
    first = registry.update({"autonomy.theoretical_only": True, "discovery.minimum_data_quality": 55}, reason="test")
    assert first["config_version"] == "CFG-000001"
    approval = registry.update({"portfolio.parameters.maximum_risk_score": 60}, reason="risk")
    assert approval["status"] == "PENDING"
    approved = registry.resolve_approval(approval["approval_id"], True)
    assert approved["config_version"] == "CFG-000002"
    assert registry.read("portfolio.parameters.maximum_risk_score") == 60
    rolled = registry.rollback("CFG-000001")
    assert rolled["config_version"] == "CFG-000003"
    assert registry.read("portfolio.parameters.maximum_risk_score") is None
    assert [row["event"] for row in rolled["history"][:2]] == ["ROLLBACK", "APPROVED_UPDATE"]


def test_validation_export_and_import_requires_approval(monkeypatch):
    from autonomi_core.configuration import registry

    fake = FakeStorage({registry.REGISTRY_KEY: _ready_document(registry)})
    monkeypatch.setattr(registry, "_storage", lambda: fake)
    try:
        registry.update({"discovery.minimum_data_quality": 120}, reason="invalid")
        assert False, "invalid value accepted"
    except ValueError:
        pass
    registry.update({"notifications.pushover_enabled": True}, reason="valid")
    bundle = json.loads(registry.export_bundle())
    assert bundle["format"] == "AI_AKSJE_ANALYZER_CENTRAL_AUTONOMY_CONFIG"
    proposal = registry.import_bundle(json.dumps(bundle))
    assert proposal["status"] in {"PENDING", "NO_CHANGE"}


def test_legacy_adapter_maps_old_keys_to_single_namespaces():
    source = (ROOT / "persistent_config_store.py").read_text(encoding="utf-8")
    registry = (ROOT / "autonomi_core/configuration/registry.py").read_text(encoding="utf-8")
    for root in ("autonomy", "discovery", "analysis", "portfolio", "learning", "runtime", "notifications", "reporting"):
        assert f'"{root}"' in registry
    assert "LEGACY_KEY_MAP" in source
    assert "compatibility=True" in source


def test_postgres_history_migration_and_central_ui_are_present():
    registry = (ROOT / "autonomi_core/configuration/registry.py").read_text(encoding="utf-8")
    ui = (ROOT / "autonomy_modes.py").read_text(encoding="utf-8")
    assert "get_storage_service" in registry
    for feature in ("validate_values", "resolve_approval", "rollback", "export_bundle", "import_bundle", "_migrate"):
        assert f"def {feature}" in registry
    assert "Central Autonomy Configuration" in ui


def test_migration_preserves_existing_portfolio_and_scheduler_values(monkeypatch):
    from autonomi_core.configuration import registry
    import settings_store

    framework = {"sections": {
        "autonomous_portfolio": {"parameters": {"maximum_risk_score": 61}},
        "market_intelligence": {"jobs": [{"name": "Morgenanalyse"}]},
    }}
    fake = FakeStorage({"configuration/framework.json": framework})
    monkeypatch.setattr(registry, "_storage", lambda: fake)
    monkeypatch.setattr(registry, "_CACHE", None)
    monkeypatch.setattr(registry, "_CACHE_AT", 0.0)
    monkeypatch.setattr(registry, "_CACHE_STORAGE_ID", None)
    monkeypatch.setattr(settings_store, "load_settings", lambda: {"pushover_enabled": True, "max_tickers_per_market": 25})
    doc = registry.load_registry()
    assert doc["values"]["portfolio"]["parameters"]["maximum_risk_score"] == 61
    assert doc["values"]["runtime"]["scheduler"]["jobs"][0]["name"] == "Morgenanalyse"
    assert doc["values"]["notifications"]["pushover_enabled"] is True
    assert doc["migration"]["complete"] is True
