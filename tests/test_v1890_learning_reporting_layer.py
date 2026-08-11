import unittest
from unittest.mock import patch
from pathlib import Path

from autonomi_core.learning_reporting.layer import (
    build_canonical_result, canonical_payload, save_canonical_result,
)


def sample_run():
    return {
        "run_id": "MI-V1890-TEST", "created_at": "2026-07-22T12:00:00+00:00",
        "job_id": "job-1", "job_name": "Morgenanalyse", "markets": ["Norge"],
        "summary": {"recommended": 1},
        "candidates": [{"ticker": "TEST.OL", "investment_score": 77.0}],
        "executive_intelligence": {"recommended": 1},
        "portfolio_decisions": {"decisions": [{"ticker": "TEST.OL", "action": "BUY"}]},
        "changes": {"new": [{"ticker": "TEST.OL"}]},
        "report_identity": {"type": "MORNING_REPORT", "label": "Morgenrapport"},
    }


class LearningReportingLayerTests(unittest.TestCase):
    def test_one_stable_identity_and_hash(self):
        first = build_canonical_result(sample_run())
        second = build_canonical_result(sample_run())
        self.assertEqual(first["result_id"], "RESULT-MI-V1890-TEST")
        self.assertEqual(first["content_hash"], second["content_hash"])
        self.assertEqual(len(first["consumers"]), 8)

    def test_delivery_fields_are_not_part_of_immutable_result(self):
        run = sample_run()
        run.update({"pdf_path": "/tmp/a.pdf", "report_url": "https://example.invalid", "notification": {"sent": True}})
        record = build_canonical_result(run)
        for key in ("pdf_path", "report_url", "notification"):
            self.assertNotIn(key, record["payload"])

    def test_all_consumers_receive_same_result_reference(self):
        view = canonical_payload(build_canonical_result(sample_run()))
        self.assertTrue(view["canonical_result"]["stored_once"])
        self.assertEqual(view["canonical_result"]["result_id"], "RESULT-MI-V1890-TEST")
        self.assertEqual(view["candidates"][0]["ticker"], "TEST.OL")

    @patch("autonomi_core.learning_reporting.layer.write_immutable_json")
    @patch("autonomi_core.learning_reporting.layer.write_json")
    @patch("autonomi_core.learning_reporting.layer.read_json")
    def test_retry_is_idempotent_and_conflict_fails_closed(self, read_json, write_json, write_immutable_json):
        record = build_canonical_result(sample_run())
        write_immutable_json.return_value = record
        read_json.return_value = [{k: record[k] for k in ("result_id", "run_id", "stored_at", "content_hash", "schema_version")}]
        self.assertEqual(save_canonical_result(sample_run())["content_hash"], record["content_hash"])
        write_json.assert_not_called()

        conflicting = dict(record, content_hash="different")
        write_immutable_json.return_value = conflicting
        with self.assertRaises(RuntimeError):
            save_canonical_result(sample_run())

    def test_pipeline_consumers_use_canonical_view(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "market_intelligence.py").read_text(encoding="utf-8")
        orchestrator = (root / "autonomous_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("build_pdf(canonical_run)", source)
        self.assertIn("register_run(canonical_run)", source)
        self.assertIn("archive_report(archive_view)", source)
        self.assertIn("_notification(job, notification_view)", source)
        self.assertIn('learning["source_result_id"]', orchestrator)


if __name__ == "__main__":
    unittest.main()
