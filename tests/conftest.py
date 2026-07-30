from __future__ import annotations

import os

# Existing historical tests exercise the paper engine. Runtime production code
# itself defaults to AV when the variable is absent. Individual safety tests
# override this value explicitly.
os.environ.setdefault("PAPER_TRADING_ENABLED", "true")
