import unittest
from unittest.mock import patch


class NavigationPerformanceTests(unittest.TestCase):
    def test_static_safety_audit_tracks_current_release(self):
        from safety_audit import run_static_regression_checks

        result = run_static_regression_checks()
        self.assertTrue(result["ok"], result)

    def test_performance_metrics_are_buffered_between_menu_renders(self):
        import performance_monitor as pm

        writes = []
        with (
            patch.object(pm, "durable_write_json", side_effect=lambda *args, **kwargs: writes.append((args, kwargs))),
            patch.object(pm, "_LAST_PERSIST_MONOTONIC", pm.time.monotonic()),
        ):
            for index in range(20):
                pm.record_render(f"panel:{index}", 1.0)

        self.assertEqual(writes, [])

    def test_configuration_reads_use_short_process_cache(self):
        from autonomi_core.configuration import registry

        calls = []

        class Storage:
            def read_json(self, *args, **kwargs):
                calls.append(args)
                doc = registry._empty()
                doc["migration"] = {"complete": True, "sources": []}
                return doc

            def write_json(self, *args, **kwargs):
                return True

        with (
            patch.object(registry, "_storage", return_value=Storage()),
            patch.object(registry, "_CACHE", None),
        ):
            first = registry.load_registry()
            second = registry.load_registry()

        self.assertEqual(first["checksum"], second["checksum"])
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
