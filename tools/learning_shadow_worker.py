"""Separate, killable worker; only experiment namespace is persisted."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'

def main():
    import json
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024**2, 768 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (45, 45))
    from learning_runtime import run_forward_batch, backfill_legacy_batch
    result = run_forward_batch()
    result['backfill'] = backfill_legacy_batch()
    print(json.dumps(result, default=str))

if __name__ == '__main__':
    main()
