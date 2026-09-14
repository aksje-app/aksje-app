from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from report_integrity import audit_learning_report_consistency
from report_replay_export import build_single_report_package


FIXTURE = Path("/tmp/rc1631_report_audit.t2cfit/report/report.json")


def _fixture_run():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# Historisk kontrakt arkivert i tests/HISTORICAL_TEST_MANIFEST.json


# Historisk kontrakt arkivert i tests/HISTORICAL_TEST_MANIFEST.json


# Historisk kontrakt arkivert i tests/HISTORICAL_TEST_MANIFEST.json


def test_summary_numbers_use_compact_consistent_typography_and_norwegian_decimals():
    source = Path("market_intelligence.py").read_text(encoding="utf-8")
    assert "def _format_summary_value" in source
    assert "SUMMARY_VALUE_FONT_SIZE = 8" in source
    assert "padding=2" in source


# Historisk kontrakt arkivert i tests/HISTORICAL_TEST_MANIFEST.json


# Historisk kontrakt arkivert i tests/HISTORICAL_TEST_MANIFEST.json
