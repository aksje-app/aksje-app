from __future__ import annotations

import os
import pytest

# Existing historical tests exercise the paper engine. Runtime production code
# itself defaults to AV when the variable is absent. Individual safety tests
# override this value explicitly.
os.environ.setdefault("PAPER_TRADING_ENABLED", "true")


# RC16.31au: every retained test is active. Historical release assertions were
# updated to validate the current contract instead of being hidden as deselected
# debt. HISTORICAL_TEST_MANIFEST.json remains provenance only.
