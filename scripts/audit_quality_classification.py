"""Print a bounded, read-only stored-quality audit. No cleanup or production edits."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quality_classification_audit import audit_storage
from services.storage_service import get_storage_service

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-runs", type=int, default=500)
    args = parser.parse_args()
    print(json.dumps(audit_storage(get_storage_service(), max_runs=args.max_runs), ensure_ascii=False, indent=2))
