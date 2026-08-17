import io
import json
import subprocess
import sys
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app_version import APP_VERSION
from market_intelligence import build_pdf, build_text_report
from report_export_audit import canonical_public_run, validate_artifacts, validate_zip
from report_replay_export import (
    ReportExportTimeout,
    _build_public_report_artifacts_inline,
    _build_public_report_artifacts_with_timeout,
    build_complete_replay_export,
    build_single_report_package,
)
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
        self.assertEqual(APP_VERSION, "v19.22.0-rc16.19")
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
        block = source[source.index('heading = f"#### Prioritert'):source.index('if latest.get("errors")')]
        self.assertIn("if not displayed_candidates:", block)
        self.assertIn("_render_priority_candidate_cards_v19220_rc1631t", block)
        self.assertNotIn("st.columns(", block)

    def test_12_all_reports_button_is_in_report_archive(self):
        source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
        panel = source[source.index("with tab_reports:"):source.index("with tab_accuracy:")]
        self.assertIn("Komplett rapport-, replay- og læringsarkiv", panel)
        self.assertIn("_replay_export_start_fragment_v19220_rc1616()", panel)
        self.assertIn("_replay_export_status_fragment_v19220_rc16()", panel)

    def test_13_invalid_legacy_report_is_quarantined_without_stopping_archive(self):
        import market_intelligence as mi
        good = dict(self.canonical_run)
        good_id = str(good["report_id"])
        bad = dict(self.canonical_run)
        bad["run_id"] = bad["report_id"] = "MI-BAD"
        entries = [
            {"run_id": good_id, "report_id": good_id, "created_at": good["created_at"]},
            {"run_id": "MI-BAD", "report_id": "MI-BAD", "created_at": bad["created_at"]},
        ]

        good_build = _build_public_report_artifacts_inline(good)

        with patch.object(mi, "_load_report_archive", return_value=entries), \
             patch.object(mi, "load_archived_run", side_effect=[good, bad]), \
             patch("report_replay_export._build_public_report_artifacts_with_timeout", side_effect=[good_build, RuntimeError("udokumentert selskapsrelevans")]), \
             patch("report_replay_export._collect_runtime_exports", return_value={}):
            payload, summary = build_complete_replay_export()

        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = set(archive.namelist())
            self.assertIn(f"reports/{good_id}/report.pdf", names)
            self.assertIn("reports/MI-BAD/quarantine/QUARANTINE_AUDIT.json", names)
            self.assertNotIn("reports/MI-BAD/report.pdf", names)
            self.assertIsNone(archive.testzip())
        self.assertEqual(summary["unique_reports_exported"], 1)
        self.assertEqual(summary["reports_quarantined"], 1)
        self.assertEqual(summary["reports_accounted_for"], 2)

    def test_14_start_action_is_separate_from_periodic_status_fragment(self):
        source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
        start = source.index("def _start_replay_export_callback_v19220_rc1616")
        panel = source[start:source.index("def _build_report_package_with_visible_progress", start)]
        self.assertIn("on_click=_start_replay_export_callback_v19220_rc1616", panel)
        self.assertIn("started = start_export()", panel)
        self.assertIn("_replay_export_start_fragment_v19220_rc1616", panel)
        self.assertNotIn("st.form_submit_button", panel)
        self.assertIn('fragment(run_every="3s")', panel)
        start_block = panel[:panel.index("def _replay_export_status_body_v19220_rc1615")]
        self.assertNotIn("run_every", start_block)
        self.assertNotIn("st.rerun()", panel)

    def test_15_market_membership_is_order_independent(self):
        from report_integrity import validate_report_integrity
        run = dict(self.canonical_run)
        run["market_profile"] = {
            "label": "Testprofil",
            "expanded_markets": ["USA", "Norge", "Sverige"],
        }
        run["markets"] = ["Norge", "Sverige", "USA"]
        errors = validate_report_integrity(run)
        self.assertFalse(any("Markedsprofilen" in error for error in errors), errors)

    def test_16_hung_report_process_is_hard_timed_out(self):
        with patch("report_replay_export.subprocess.run", side_effect=subprocess.TimeoutExpired(["worker"], 1)):
            with self.assertRaises(ReportExportTimeout):
                _build_public_report_artifacts_with_timeout(self.canonical_run, timeout_seconds=1)

    def test_17_stale_worker_status_is_recoverable(self):
        import replay_export_background as background
        stale = {
            "execution_id": "REPLAY-STALE",
            "state": "RUNNING",
            "worker_heartbeat_at": "2020-01-01T00:00:00+00:00",
        }
        with patch.object(background, "_write_status", side_effect=lambda value: dict(value)):
            recovered = background._recover_stale_status(stale)
        self.assertEqual(recovered["state"], "FAILED")
        self.assertTrue(recovered["stale_worker_recovered"])
        self.assertFalse(background.is_running(recovered))

    def test_18_watchdog_heartbeat_is_independent(self):
        source = (ROOT / "replay_export_background.py").read_text(encoding="utf-8")
        self.assertIn("def watchdog()", source)
        self.assertIn('current["watchdog_alive"] = True', source)
        self.assertIn("watchdog_thread.start()", source)

    def test_19_timeout_is_counted_and_written_to_quarantine_audit(self):
        import market_intelligence as mi
        entry = {
            "run_id": self.canonical_run["run_id"],
            "report_id": self.canonical_run["report_id"],
            "created_at": self.canonical_run["created_at"],
        }
        with patch.object(mi, "_load_report_archive", return_value=[entry]), \
             patch.object(mi, "load_archived_run", return_value=self.canonical_run), \
             patch("report_replay_export._build_public_report_artifacts_with_timeout", side_effect=ReportExportTimeout("120 sekunder")), \
             patch("report_replay_export._collect_runtime_exports", return_value={}):
            payload, summary = build_complete_replay_export()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            audit_name = next(name for name in archive.namelist() if name.endswith("QUARANTINE_AUDIT.json"))
            audit = json.loads(archive.read(audit_name))
        self.assertEqual(audit["reason_code"], "REPORT_EXPORT_TIMEOUT")
        self.assertEqual(summary["reports_timed_out"], 1)
        self.assertEqual(summary["reports_quarantined"], 1)

    def test_20_click_callback_starts_worker_and_records_acknowledgement(self):
        import market_intelligence as mi
        fake_streamlit = types.SimpleNamespace(session_state={})
        with patch.dict(sys.modules, {"streamlit": fake_streamlit}), \
             patch("replay_export_background.start_export", return_value={"execution_id": "REPLAY-NEW"}) as starter:
            mi._start_replay_export_callback_v19220_rc1616()
        starter.assert_called_once_with()
        self.assertEqual(
            fake_streamlit.session_state["mi_replay_export_start_ack_v19220_rc1616"],
            "REPLAY-NEW",
        )

    def test_21_archive_is_paginated_and_heavy_details_are_lazy(self):
        source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
        archive = source[source.index("with tab_reports:"):source.index("with tab_accuracy:")]
        self.assertIn("archive_page_size_v19220_rc1617 = 20", archive)
        self.assertIn("for row in visible_archive_rows_v19220_rc1617", archive)
        self.assertNotIn("for row in filtered[:200]", archive)
        toggle_pos = archive.index('"Last rapportdetaljer"')
        load_pos = archive.index("saved_run = load_archived_run(row)")
        self.assertLess(toggle_pos, load_pos)
        between = archive[toggle_pos:load_pos]
        self.assertIn("if not load_details_v19220_rc1617", between)
        self.assertIn("continue", between)

    def test_22_quick_archive_returns_before_heavy_report_center_work(self):
        source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
        render_start = source.index("def render_market_intelligence()")
        render = source[render_start:]
        quick_call = render.index("_render_quick_report_archive_v19220_rc1618(st)")
        early_return = render.index("return", quick_call)
        scheduler = render.index("from scheduler_background import kick_scheduler_background")
        jobs = render.index("quick_jobs = load_jobs()")
        self.assertLess(quick_call, early_return)
        self.assertLess(early_return, scheduler)
        self.assertLess(early_return, jobs)
        quick_fn = source[source.index("def _render_quick_report_archive_v19220_rc1618"):render_start]
        self.assertIn("_replay_export_start_fragment_v19220_rc1616()", quick_fn)
        self.assertIn("archive[:20]", quick_fn)
        self.assertNotIn("load_archived_run", quick_fn)
        self.assertNotIn("resolve_report_delivery", quick_fn)
        self.assertNotIn("render_accuracy_analytics", quick_fn)


if __name__ == "__main__":
    unittest.main(verbosity=2)
