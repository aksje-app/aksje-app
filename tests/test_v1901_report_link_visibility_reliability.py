import unittest
import ast
from pathlib import Path


class ReportLinkVisibilityReliabilityTests(unittest.TestCase):
    def test_only_absolute_http_urls_are_rendered(self):
        source = (Path(__file__).resolve().parents[1] / "autonomy_overview.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_safe_public_report_url")
        module = ast.Module(body=[function], type_ignores=[])
        namespace = {"Any": object, "urlparse": __import__("urllib.parse", fromlist=["urlparse"]).urlparse}
        exec(compile(module, "autonomy_overview.py", "exec"), namespace)
        safe = namespace["_safe_public_report_url"]
        self.assertEqual(safe("https://example.test/report.pdf"), "https://example.test/report.pdf")
        self.assertEqual(safe("http://example.test/report.pdf"), "http://example.test/report.pdf")
        self.assertEqual(safe("javascript:alert(1)"), "")
        self.assertEqual(safe("/reports/local.pdf"), "")

    def test_report_link_has_stable_normal_and_interaction_styles(self):
        source = (Path(__file__).resolve().parents[1] / "autonomy_overview.py").read_text(encoding="utf-8")
        self.assertIn('class="autonomy-report-link-v1901"', source)
        self.assertIn("a.autonomy-report-link-v1901:visited", source)
        self.assertIn("a.autonomy-report-link-v1901:hover", source)
        self.assertIn("a.autonomy-report-link-v1901:focus-visible", source)
        self.assertIn("background:#172033!important", source)
        self.assertIn("-webkit-text-fill-color:#fff!important", source)

    def test_last_valid_archive_link_is_preserved(self):
        source = (Path(__file__).resolve().parents[1] / "autonomy_overview.py").read_text(encoding="utf-8")
        self.assertIn("latest_linked_archive = next", source)
        self.assertIn('or latest_linked_archive.get("report_url")', source)
        self.assertIn("Offentlig rapportlenke er ikke tilgjengelig", source)


if __name__ == "__main__":
    unittest.main()
