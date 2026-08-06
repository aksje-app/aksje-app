import io
import json
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app_version import APP_VERSION
from market_intelligence import build_pdf, build_text_report
from report_export_audit import canonical_public_run, validate_artifacts, validate_zip
from report_replay_export import build_complete_replay_export, build_single_report_package
from tests.test_v19220_rc169_export_consistency import sample_run


ROOT = Path(__file__).resolve().parents[1]


class VerifiedExportClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical_run = canonical_public_run(sample_run())
        cls.pdf = build_pdf(cls.canonical_run)
        cls.txt = build_text_report(cls.canonical_run).encode("utf-8")
        cls.json_bytes = json.dumps(cls.canonical_run, ensure_ascii=False, indent=2, default=str).encode("utf-8")

    def test_01_version_contract_is_rc1610(self):
        self.assertEqual(APP_VERSION, "v19.22.0-rc16.11")
        self.assertEqual(self.canonical_run["app_version"], APP_VERSION)

    def test_02_noto_sans_is_embedded(self):
        from pypdf import PdfReader
        fonts = set()
        for page in PdfReader(io.BytesIO(self.pdf)).pages:
            for ref in ((page.get("/Resources") or {}).get("/Font") or {}).values():
                fonts.add(str(ref.get_object().get("/BaseFont") or ""))
        self.assertTrue(any("NotoSans" in name for name in fonts), fonts)

    def test_03_pdf_has_bookmarks(self):
        from pypdf import PdfReader
        self.assertTrue(list(PdfReader(io.BytesIO(self.pdf)).outline or []))

    def test_04_artifact_audit_passes(self):
        result = validate_artifacts(run=self.canonical_run, pdf=self.pdf, txt=self.txt, json_bytes=self.json_bytes)
        self.assertTrue(result["ok"], result)

    def test_05_artifact_audit_rejects_wrong_json_version(self):
        payload = json.loads(self.json_bytes)
        payload["app_version"] = "v0"
        payload["version"] = "v0"
        result = validate_artifacts(
            run=self.canonical_run, pdf=self.pdf, txt=self.txt,
            json_bytes=json.dumps(payload).encode("utf-8"),
        )
        self.assertFalse(result["ok"])

    def test_06_single_zip_contains_mandatory_artifacts_and_audit(self):
        payload, _ = build_single_report_package(self.canonical_run)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = set(archive.namelist())
            self.assertTrue({
                "report/report.pdf", "report/report.txt", "report/report.json",
                "REPORT_CONSISTENCY_AUDIT.json", "SHA256SUMS.txt",
            } <= names)
            self.assertTrue(json.loads(archive.read("REPORT_CONSISTENCY_AUDIT.json"))["ok"])
        self.assertTrue(validate_zip(payload)["ok"])

    def test_07_zip_validator_rejects_corrupt_payload(self):
        self.assertFalse(validate_zip(b"not-a-zip")["ok"])

    def test_08_legacy_public_rankings_are_removed(self):
        self.assertNotIn("priority_top3", self.canonical_run)
        self.assertNotIn("raw_top3", self.canonical_run)
        self.assertIn("public_report_contract", self.canonical_run)
        self.assertEqual(self.canonical_run["public_report_contract"], self.canonical_run["channel_consistency"])

    def test_09_rejected_cases_only_use_control_appendix(self):
        document = self.canonical_run["report_document"]
        candidate_section = next(row for row in document["sections"] if row["key"] == "candidate_decisions")
        rejected_section = next(row for row in document["sections"] if row["key"] == "rejected_control_appendix")
        self.assertEqual(candidate_section["payload"], [])
        self.assertTrue(rejected_section["payload"])

    def test_10_complete_zip_audits_every_report(self):
        import market_intelligence as mi
        entry = {"run_id": self.canonical_run["run_id"], "report_id": self.canonical_run["report_id"], "created_at": self.canonical_run["created_at"]}
        with patch.object(mi, "_load_report_archive", return_value=[entry]), \
             patch.object(mi, "load_archived_run", return_value=self.canonical_run), \
             patch("report_replay_export._collect_runtime_exports", return_value={}):
            payload, summary = build_complete_replay_export()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            audit_names = [name for name in archive.namelist() if name.endswith("REPORT_CONSISTENCY_AUDIT.json")]
            self.assertEqual(len(audit_names), 1)
            self.assertTrue(json.loads(archive.read(audit_names[0]))["ok"])
            self.assertIsNone(archive.testzip())
        self.assertEqual(summary["unique_reports_exported"], 1)

    def test_11_empty_projection_never_creates_zero_columns(self):
        source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
        self.assertIn("st.columns(min(3, len(displayed_candidates))) if displayed_candidates else []", source)

    def test_12_all_reports_button_is_in_report_archive(self):
        source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
        panel = source[source.index("with tab_reports:"):source.index("with tab_accuracy:")]
        self.assertIn("Bygg samlet ZIP av alle rapporter", panel)
        self.assertIn("_replay_export_status_fragment_v19220_rc16()", panel)


if __name__ == "__main__":
    unittest.main(verbosity=2)
