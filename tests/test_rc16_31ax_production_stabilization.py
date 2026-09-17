from __future__ import annotations

from datetime import datetime, timezone


def test_ax_version_lineage():
    from app_version import APP_VERSION, PREVIOUS_APP_VERSION
    assert APP_VERSION == "v19.22.0-rc16.31bd"
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.31bc"


def test_revalidation_is_blocked_around_all_mandatory_reports():
    from market_intelligence import revalidation_blackout_status
    for hour in (6, 12, 20):  # UTC == 08/14/22 in Oslo summer time
        result = revalidation_blackout_status(datetime(2026, 9, 1, hour, 0, tzinfo=timezone.utc))
        assert result["blocked"] is True
        assert result["state"] == "SKIPPED_MANDATORY_REPORT_WINDOW"
    assert revalidation_blackout_status(datetime(2026, 9, 1, 16, 0, tzinfo=timezone.utc))["blocked"] is False


def test_revalidation_returns_without_loading_archive_inside_blackout(monkeypatch):
    import market_intelligence as mi
    monkeypatch.setattr(mi, "_load_report_archive", lambda: (_ for _ in ()).throw(AssertionError("must not load")))
    result = mi.revalidate_provisional_reports(datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc))
    assert result["state"] == "SKIPPED_MANDATORY_REPORT_WINDOW"
    assert result["runs"] == []


def test_mobile_fallback_keys_are_panel_scoped():
    from mobile_file_delivery import render_mobile_file_delivery

    class Context:
        def __enter__(self): return self
        def __exit__(self, *_): return False

    class FakeStreamlit:
        def __init__(self): self.keys = []; self.html = []
        def markdown(self, value, **__): self.html.append(value)
        def caption(self, *_): pass
        def code(self, *_, **__): pass
        def expander(self, *_, **__): return Context()
        def download_button(self, *_, **kwargs): self.keys.append(kwargs["key"])

    st = FakeStreamlit()
    common = dict(url="/report.json", filename="report.json", label="Åpne", mime="application/json",
                  data=b"{}", key="json_RUN")
    render_mobile_file_delivery(st, **common, instance_key="latest")
    render_mobile_file_delivery(st, **common, instance_key="archive_RUN")
    assert len(set(st.keys)) == 2


def test_token_landing_url_is_never_downloaded_as_fake_json():
    from mobile_file_delivery import render_mobile_file_delivery

    class FakeStreamlit:
        def __init__(self): self.html = []; self.labels = []
        def markdown(self, value, **_): self.html.append(value)
        def caption(self, *_): pass
        def code(self, *_ , **__): pass
        def download_button(self, label, **_): self.labels.append(label)

    st = FakeStreamlit()
    render_mobile_file_delivery(
        st,
        url="https://aksje-app.onrender.com/?public_file_token=TOKEN",
        filename="learning.json",
        label="Åpne læringsrapport JSON",
        mime="application/json",
        data=b"{}",
        key="learning_json",
    )
    html = "".join(st.html)
    assert 'download="learning.json"' not in html
    assert "Åpne nedlastingsside" in html
    assert st.labels == ["Last ned korrekt fil direkte"]


def test_storage_retention_is_dry_run_by_default(monkeypatch):
    import storage_retention as retention

    class FakeStorage:
        def __init__(self): self.deleted = []
        def storage_usage_report(self): return {"backend": "local", "database_bytes": 1}
        def list_json_names(self): return [f"operations/run_traces/{i:03d}.json" for i in range(200)]
        def list_jsonl_names(self): return []
        def delete_json(self, name): self.deleted.append(name)

    fake = FakeStorage()
    monkeypatch.delenv("STORAGE_RETENTION_APPLY", raising=False)
    monkeypatch.setattr(retention, "get_storage_service", lambda: fake)
    result = retention.run_storage_retention()
    assert result["state"] == "DRY_RUN"
    assert result["planned_deleted_keys"]["operations/run_traces/"] == 20
    assert fake.deleted == []


def test_diagnostics_carry_database_and_required_report_evidence():
    source = open("manual_job_background.py", encoding="utf-8").read()
    assert "runtime/DATABASE_CAPACITY.json" in source
    assert "scheduler/RECENT_REQUIRED_REPORTS.json" in source


def test_revalidation_does_not_replace_latest_ordinary_report():
    source = open("market_intelligence.py", encoding="utf-8").read()
    assert source.count('if trigger != "REVALIDATION":') >= 3
    assert 'if str(run.get("trigger") or "").upper() != "REVALIDATION":' in source
