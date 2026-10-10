"""Disk-backed immutable frames; long histories need not fit in RAM."""
from collections.abc import Sequence
import gzip
import json
from pathlib import Path
from learning_experiments import checksum


class FrameDataset(Sequence):
    def __init__(self, root, records=None):
        self.root = Path(root).resolve()
        if records is None:
            manifest_path = self.root / 'manifest.json'
            if manifest_path.stat().st_size > 8 * 1024**2:
                raise ValueError('Offline manifest exceeds budget')
            manifest = json.loads(manifest_path.read_text())
            if checksum(manifest['frames']) != manifest.get('sha256'):
                raise ValueError('Offline manifest checksum mismatch')
            records = manifest['frames']
        self.records = records
        self.dataset_identity = [r['sha256'] for r in self.records]

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return FrameDataset(self.root, self.records[index])
        record = self.records[index]
        path = (self.root / record['file']).resolve()
        if self.root not in path.parents:
            raise ValueError('Frame path outside bundle')
        from learning_runtime import MAX_FRAME_BYTES, validate
        with gzip.open(path, 'rb') as handle:
            raw = handle.read(MAX_FRAME_BYTES + 1)
        if len(raw) > MAX_FRAME_BYTES:
            raise ValueError('Offline frame exceeds memory budget')
        frame = json.loads(raw)
        if frame['sha256'] != record['sha256'] or frame['at'] != record['at']:
            raise ValueError('Offline bundle frame mismatch')
        validate(frame)
        return frame

    def select_period(self, begin=None, end=None):
        return FrameDataset(self.root, [r for r in self.records
            if (begin is None or r['at'][:10] >= begin) and (end is None or r['at'][:10] < end)])
