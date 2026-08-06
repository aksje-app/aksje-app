import io, json, zipfile
from app_version import APP_VERSION
from report_export_audit import canonical_public_run, validate_zip
from report_replay_export import build_single_report_package

def sample_run():
    return {
      "run_id":"MI-TEST-169","report_id":"MI-TEST-169","app_version":"v19.22.0-rc16.1","version":"v19.22.0-rc16.1",
      "created_at":"2026-08-05T20:00:00+00:00","timezone_name":"Europe/Oslo","job_id":"MI-DRAFT-AUTOSAVE",
      "report_identity":{"type":"UTKAST","label":"Utkast – Kveldsrapport","slug":"UTKAST_Kveldsrapport"},
      "report_status":{"state":"DRAFT"},"report_revision":{"revision_label":"R1"},"markets":["USA"],
      "summary":{},"report_summary":{},"data_quality":{},"combined_data_quality":{},"decision_report":{},
      "candidates":[
        {"ticker":"BUY1","market":"USA","investment_score":91,"autonomy_outcome_code":"KJØPSKANDIDAT","portfolio_action":"BUY","autonomy_outcome_label":"Kjøpskandidat","final_decision_ready":True},
        {"ticker":"NO1","market":"USA","investment_score":88,"autonomy_outcome_code":"AUTOMATISK_AVVIST","portfolio_action":"SKIP","autonomy_outcome_label":"Automatisk avvist","autonomy_outcome_reason":"Gate"},
      ],
      "priority_top3":[{"ticker":"NO1"}],"raw_top3":[{"ticker":"NO1"}],"errors":[],"warnings":[],
      "report_integrity":{"ok":True,"errors":[]}
    }

def test_canonical_public_run_removes_legacy_rankings_and_bumps_version():
    run=canonical_public_run(sample_run())
    assert run["app_version"] == APP_VERSION == "v19.22.0-rc16.19"
    assert "priority_top3" not in run and "raw_top3" not in run
    assert run["public_report_contract"]["ranking"] == []
    appendix = next(x for x in run["report_document"]["sections"] if x["key"] == "rejected_control_appendix")
    assert {x["ticker"] for x in appendix["payload"]} == {"BUY1", "NO1"}

def test_single_package_has_required_artifacts(monkeypatch):
    monkeypatch.setattr("report_replay_export._read_pdf_without_side_effects", lambda *a, **k: b"%PDF-1.4\n%fake")
    # audit needs readable PDF, so bypass only PDF extraction aspect for unit scope
    monkeypatch.setattr("report_export_audit.validate_artifacts", lambda **k: {"ok":True,"errors":[],"expected":{}})
    payload,_=build_single_report_package(sample_run())
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        names=set(z.namelist())
        assert {"report/report.pdf","report/report.txt","report/report.json","REPORT_CONSISTENCY_AUDIT.json"} <= names
        data=json.loads(z.read("report/report.json"))
        assert data["app_version"] == APP_VERSION
        assert "priority_top3" not in data
    assert validate_zip(payload)["ok"]
