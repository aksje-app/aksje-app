from __future__ import annotations

from pathlib import Path


def test_semantic_market_colours_follow_generic_pill_rule():
    source = Path("workspace_layout.py").read_text(encoding="utf-8")
    generic = source.rfind("html body .stApp .ptw-pill,")
    opened = source.rfind("html body .stApp .ptw-pill.ptw-market-open")
    closed = source.rfind("html body .stApp .ptw-pill.ptw-market-closed")
    assert generic >= 0
    assert opened > generic
    assert closed > generic
    assert "rgba(34,197,94,.72) !important" in source[opened:opened + 350]
    assert "rgba(239,68,68,.72) !important" in source[closed:closed + 350]
