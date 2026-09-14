from pathlib import Path

import app
import retired_module_cleanup as cleanup
import scheduled_runner


class Storage:
    def __init__(self):
        self.values = {
            cleanup._KEYS[0]: {"active": True},
            cleanup._KEYS[1]: {"listings": {"vehicle": {}}},
        }
        self.deleted = []

    def read_json(self, key, default=None):
        return self.values.get(key, default)

    def write_json(self, key, value):
        self.values[key] = value
        return True

    def delete_json(self, key):
        self.deleted.append(key)
        self.values.pop(key, None)
        return True


def test_cleanup_deletes_only_vehicle_namespace_and_is_idempotent(monkeypatch, tmp_path):
    storage = Storage()
    local = (tmp_path / "config.json", tmp_path / "state.json")
    for path in local:
        path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cleanup, "get_storage_service", lambda: storage)
    monkeypatch.setattr(cleanup, "_LOCAL_PATHS", local)

    first = cleanup.purge_retired_jeep_commander_once()
    second = cleanup.purge_retired_jeep_commander_once()

    assert first["state"] == "COMPLETED"
    assert second["state"] == "ALREADY_COMPLETED"
    assert storage.deleted == list(cleanup._KEYS)
    assert all(not path.exists() for path in local)
    assert set(first["deleted_keys"]) == set(cleanup._KEYS)


def test_active_application_and_scheduler_have_no_vehicle_module_route():
    app_source = Path(app.__file__).read_text(encoding="utf-8")
    scheduler_source = Path(scheduled_runner.__file__).read_text(encoding="utf-8")
    assert "render_jeep_commander_control_center" not in app_source
    assert '"🚙 Jeep Commander 2.2"' not in app_source
    assert "from jeep_commander_monitor" not in scheduler_source
    assert '"jeep_commander_monitor"' not in scheduler_source
