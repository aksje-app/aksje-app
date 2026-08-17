import unittest
from pathlib import Path

from report_replay_export import build_single_report_package
from tests.test_v19220_rc169_export_consistency import sample_run


ROOT = Path(__file__).resolve().parents[1]


class VisiblePackageProgressTests(unittest.TestCase):
    def test_single_package_reports_monotonic_real_stages(self):
        events = []
        payload, _ = build_single_report_package(
            sample_run(),
            progress_callback=lambda done, total, message: events.append((done, total, message)),
        )
        self.assertTrue(payload.startswith(b"PK"))
        self.assertGreaterEqual(len(events), 9)
        self.assertEqual(events[0][0], 0)
        self.assertEqual(events[-1][:2], (12, 12))
        self.assertEqual([row[0] for row in events], sorted(row[0] for row in events))
        messages = " | ".join(row[2] for row in events)
        for expected in ("Canonicaliserer", "JSON", "TXT", "PDF", "Consistency Audit", "Komprimerer", "ferdig"):
            self.assertIn(expected, messages)

    def test_latest_report_button_uses_visible_progress_helper(self):
        source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
        block = source[source.index('if st.button("Bygg ZIP med PDF, JSON, tekst og revisjon"'):source.index('if st.session_state.get(latest_package_key)')]
        self.assertIn("_build_report_package_with_visible_progress_v19220_rc1611", block)
        self.assertNotIn("build_single_report_package(", block)

    def test_archived_report_button_uses_same_visible_progress_helper(self):
        source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
        start = source.index('if p1.button("Bygg ZIP med PDF, JSON, tekst og revisjon"')
        block = source[start:source.index('if st.session_state.get(package_state_key)', start)]
        self.assertIn("_build_report_package_with_visible_progress_v19220_rc1611", block)

    def test_visible_progress_contract_contains_required_fields(self):
        source = (ROOT / "market_intelligence.py").read_text(encoding="utf-8")
        start = source.index("def _build_report_package_with_visible_progress_v19220_rc1611")
        block = source[start:source.index("def render_market_intelligence", start)]
        for expected in ("st.progress", "Aktivt steg", "arbeidsenheter", "kjørt i", "ZIP klar"):
            self.assertIn(expected, block)

    def test_legacy_full_candidate_ranking_gate_is_not_present(self):
        source = (ROOT / "report_integrity.py").read_text(encoding="utf-8")
        self.assertNotIn("PDF dokumenterer ikke full kandidatrangering", source)
        self.assertIn("public buy-only projection", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
