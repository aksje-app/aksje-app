#!/usr/bin/env python3
"""Export sanitised v19.12.0 promotion, binding and Strategy Lab evidence."""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.evaluation_export_service import get_evaluation_export_service


def main() -> int:
    parser = argparse.ArgumentParser(description="Export shareable strategy approval, promotion, rollback and evaluation evidence.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = get_evaluation_export_service().build_zip(additional_metadata={"release": "v19.12.0"})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(f"Created: {args.output}")
    print(f"Size: {len(payload)} bytes")
    print(f"SHA-256: {hashlib.sha256(payload).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
