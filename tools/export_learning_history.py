"""Export verified point-in-time archives for offline search, one frame at a time.

No historical price reconstruction or current-news enrichment is permitted.
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('engine', choices=['AUTONOMY', 'SUPER_PORTFOLIO', 'AUTONOMY_UNIVERSE'])
    parser.add_argument('output', type=Path)
    parser.add_argument('--bundle', action='store_true', help='Stream frames to compressed, disk-backed directory')
    args = parser.parse_args()
    from learning_runtime import storage, INDEX, load_frame, coverage
    index = storage().read_json(INDEX, {}) or {}
    records = sorted([r for r in index.get('records', []) if r['engine'] == args.engine and r['status'] == 'READY'], key=lambda r:r['at'])
    if args.bundle:
        import gzip
        from learning_experiments import checksum
        args.output.mkdir(parents=True, exist_ok=True)
        manifest = []
        for record in records:
            frame = load_frame(record)
            filename = record['sha256'] + '.json.gz'
            target = args.output / filename
            with gzip.open(target, 'wt') as handle:
                json.dump(frame, handle, ensure_ascii=False)
            manifest.append({'file': filename, 'sha256': frame['sha256'], 'at': frame['at']})
        temporary = args.output / 'manifest.tmp'
        temporary.write_text(json.dumps({'frames': manifest, 'sha256': checksum(manifest), 'coverage': coverage()}, indent=2))
        temporary.replace(args.output / 'manifest.json')
        print(json.dumps({'frames': len(records), 'production_changed': False}))
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(args.output.suffix + '.tmp')
    with temp.open('w') as handle:
        handle.write('[')
        for i, record in enumerate(records):
            if i:
                handle.write(',\n')
            json.dump(load_frame(record), handle, ensure_ascii=False)
        handle.write(']')
    temp.replace(args.output)
    args.output.with_suffix('.coverage.json').write_text(json.dumps(coverage(), indent=2))
    print(json.dumps({'frames': len(records), 'production_changed': False}))

if __name__ == '__main__':
    main()
