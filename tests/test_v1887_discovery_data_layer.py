import unittest
from datetime import date
from unittest.mock import patch

from autonomi_core.discovery_data.layer import DiscoveryComposition, select_discovery_candidates


class MemoryStorage:
    def __init__(self): self.values = {}
    def read_json(self, key, default=None): return self.values.get(key, default)
    def write_json(self, key, value): self.values[key] = value; return True


def rows(prefix, count, source):
    return [{"ticker": f"{prefix}{number:02d}", "market": "USA", "source": source} for number in range(count)]


class DiscoveryDataLayerTests(unittest.TestCase):
    def setUp(self): self.storage = MemoryStorage()

    def select(self, day):
        with patch("autonomi_core.discovery_data.layer.get_storage_service", return_value=self.storage):
            return select_discovery_candidates(
                rows("DOC", 30, "Market Scanner"), rows("NEW", 40, "Outside index reserve"),
                market="USA", limit=10, mission_id="MIS-1", configuration_version="CFG-1",
                composition=DiscoveryComposition(), run_date=date.fromisoformat(day),
            )

    def test_first_run_uses_70_20_10_contract(self):
        selected, summary = self.select("2026-07-22")
        self.assertEqual(len(selected), 10)
        self.assertEqual(summary["composition_actual"], {"DOCUMENTED": 7, "NEW": 2, "EXPERIMENTAL": 1})
        self.assertFalse(summary["degraded"])

    def test_next_day_does_not_repeat_same_universe(self):
        first, _ = self.select("2026-07-22")
        second, summary = self.select("2026-07-23")
        self.assertNotEqual([row["ticker"] for row in first], [row["ticker"] for row in second])
        self.assertTrue(summary["rotated_from_previous"])

    def test_every_candidate_carries_mission_and_source_control_metadata(self):
        selected, _ = self.select("2026-07-22")
        for row in selected:
            self.assertEqual(row["mission_id"], "MIS-1")
            self.assertEqual(row["configuration_version"], "CFG-1")
            self.assertIn(row["discovery_bucket"], {"DOCUMENTED", "NEW", "EXPERIMENTAL"})
            self.assertIn("analysis_quarantine", row)
            self.assertTrue(row["discovery_fingerprint"])

    def test_unchanged_candidate_is_quarantined_on_later_run(self):
        first, _ = self.select("2026-07-22")
        second, _ = self.select("2026-07-23")
        overlap = {row["ticker"]: row for row in second if row["ticker"] in {x["ticker"] for x in first}}
        self.assertTrue(overlap)
        self.assertTrue(any(row["analysis_quarantine"] for row in overlap.values()))


if __name__ == "__main__": unittest.main()
