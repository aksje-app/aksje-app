#!/usr/bin/env python3
"""Export the sanitised v19.9.0 strategy evaluation ZIP from the CLI."""
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
    parser = argparse.ArgumentParser(description="Eksporter delbar test- og aktiveringspakke.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = get_evaluation_export_service().build_zip()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(f"Opprettet: {args.output}")
    print(f"Størrelse: {len(payload)} bytes")
    print(f"SHA-256: {hashlib.sha256(payload).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
