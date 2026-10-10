#!/usr/bin/env python3
"""Bounded offline experiment from immutable recorded Superfond frames."""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import resource
import sys
from collections.abc import Sequence
from tempfile import TemporaryDirectory

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


class DiskFrames(Sequence):
    """Load one verified frame at a time, including repeated strategy passes."""
    def __init__(self,paths):self.paths=paths
    def __len__(self):return len(self.paths)
    def __getitem__(self,index):
        if isinstance(index,slice):raise TypeError('Bruk strømmet iterasjon')
        return json.loads(self.paths[index].read_bytes())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(45,45))
    from superfund_runtime import read,storage
    from superfund_learning import historical_experiment
    index=read('learning_index.json',{'frames':[]})
    with TemporaryDirectory(prefix='superfund-experiment-') as scratch:
        paths=[]
        for entry in sorted(index['frames'],key=lambda r:r['day']):
            doc=storage().read_json(entry['key'],{})
            packed=base64.b64decode(doc['gzip_base64'],validate=True)
            if hashlib.sha256(packed).hexdigest()!=entry['sha256']:raise ValueError('Historikksjekksum feilet')
            from io import BytesIO
            with gzip.GzipFile(fileobj=BytesIO(packed)) as handle:
                raw=handle.read(12*1024*1024+1)
            if len(raw)>12*1024*1024:raise ValueError('Historikkramme for stor')
            path=Path(scratch)/(entry['day']+'.json');path.write_bytes(raw);paths.append(path)
        # CPU/memory hard limits protect the caller even when an archive is large.
        result=historical_experiment(DiskFrames(paths))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'state':result['state'],'output':str(args.output)}))


if __name__=='__main__':main()
