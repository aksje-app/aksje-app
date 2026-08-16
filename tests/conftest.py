from __future__ import annotations

import os
import json
from pathlib import Path

import pytest

# Existing historical tests exercise the paper engine. Runtime production code
# itself defaults to AV when the variable is absent. Individual safety tests
# override this value explicitly.
os.environ.setdefault("PAPER_TRADING_ENABLED", "true")


_HISTORICAL_MANIFEST = Path(__file__).with_name("HISTORICAL_TEST_MANIFEST.json")


def pytest_collection_modifyitems(config, items):
    """Keep superseded release contracts visible without treating them as current acceptance tests."""
    contracts = json.loads(_HISTORICAL_MANIFEST.read_text(encoding="utf-8"))["tests"]
    for item in items:
        entry = contracts.get(item.nodeid)
        if entry:
            item.add_marker(pytest.mark.xfail(
                strict=True,
                reason=f"{entry['category']}: {entry['reason']}",
            ))
