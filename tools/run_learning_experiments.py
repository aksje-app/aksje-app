"""Run bounded offline SP experiments in a separate process.

Example: python tools/run_learning_experiments.py frozen_frames.json search_space.json result.json
Never starts a scheduler, sends alerts or updates production parameters.
"""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frames", type=Path)
    parser.add_argument("space", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--budget", type=int, default=100)
    parser.add_argument("--finalists", type=int, default=3)
    parser.add_argument("--embargo-days", type=int, default=90)
    parser.add_argument("--memory-mb", type=int, default=768)
    args = parser.parse_args()
    import os
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    import resource
    # Independent process cap; never applied to the web service/cron process.
    cap = max(256, min(args.memory_mb, 2048)) * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    from learning_experiments import run_search
    if (args.frames.is_file() and args.frames.stat().st_size > 64 * 1024 * 1024) or args.space.stat().st_size > 1024 * 1024:
        raise ValueError("Input exceeds experiment budget")
    if args.frames.is_dir():
        from learning_dataset import FrameDataset
        dataset = FrameDataset(args.frames)
    else:
        dataset = json.loads(args.frames.read_text())
    result = run_search(dataset, json.loads(args.space.read_text()),
                        budget=args.budget, finalists=args.finalists, embargo_days=args.embargo_days)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    temporary.replace(args.output)
    print(json.dumps({"status": result["status"], "trials": result["trial_count"],
                      "production_changed": False, "output": str(args.output)}))

if __name__ == "__main__":
    main()
