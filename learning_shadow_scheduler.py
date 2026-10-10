"""Keep optional experiment CPU/memory out of web and trading processes."""
from ui_library.work_progress import tracked_job
import json
import os
from pathlib import Path
import subprocess
import sys


@tracked_job('Læring · shadow')
def run_shadow_job():
    from autonomous_portfolio import _available_memory_mb
    headroom = _available_memory_mb()
    if headroom is not None and headroom < 384:
        return {'status': 'DEFERRED_MEMORY', 'production_changed': False}
    env = {**os.environ, 'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1'}
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).parent / 'tools/learning_shadow_worker.py')],
            capture_output=True, text=True, timeout=50, env=env)
    except subprocess.TimeoutExpired:
        return {'status': 'DEFERRED_TIMEOUT', 'production_changed': False}
    if result.returncode:
        return {'status': 'FAILED', 'error': result.stderr[-500:], 'production_changed': False}
    return json.loads(result.stdout.strip().splitlines()[-1])
