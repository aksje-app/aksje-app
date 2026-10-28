"""Bounded, checksummed, resumable streams over the authenticated SSH channel."""
import hashlib
import json
import os
from pathlib import Path

LIMIT = 16 * 1024**3


def emit(stream, value):
    stream.write(json.dumps(value, ensure_ascii=True).encode()+b'\n'); stream.flush()


def line(stream):
    raw=stream.readline(1024*1024)
    if not raw or not raw.endswith(b'\n'):
        raise ValueError('SSH connection ended; activation status may be unknown. Resume the same signed package, never create replacement accounts')
    return json.loads(raw)


def sha(path, *, start=0, length=None):
    value=hashlib.sha256()
    with Path(path).open('rb') as source:
        source.seek(start)
        left=length
        while left is None or left:
            block=source.read(1024**2 if left is None else min(left,1024**2))
            if not block:break
            value.update(block)
            if left is not None:left-=len(block)
    return value.hexdigest()


def send_file(stream, path, *, offset=0, prefix_sha256=None, **metadata):
    path=Path(path);total=path.stat().st_size
    if type(offset) is not int or not 0<=offset<=total:raise ValueError('Invalid resume offset')
    if offset and sha(path,length=offset)!=prefix_sha256:raise ValueError('Partial ciphertext differs; no append')
    emit(stream,dict(size=total-offset,sha256=sha(path,start=offset),offset=offset,total_size=total,total_sha256=sha(path),**metadata))
    with path.open('rb') as source:
        source.seek(offset)
        for block in iter(lambda:source.read(1024**2),b''):stream.write(block)
    stream.flush()


def receive_file(stream, path, header=None, limit=LIMIT, *, offset=0, expected_sha256=None):
    header=header or line(stream);length=header.get('size')
    if type(length) is not int or not 0<=length<=limit or header.get('offset',0)!=offset:
        raise ValueError('Invalid transfer size or resume offset')
    path=Path(path);part=path.with_name(path.name+'.part')
    if path.exists():raise ValueError('Destination already exists; no overwrite')
    if offset:
        if not part.is_file() or part.is_symlink() or part.stat().st_size!=offset:raise ValueError('Resume file changed')
    elif part.exists():
        # Preserve uncertain partial bytes; a new full transfer has its own file.
        part.rename(part.with_name(part.name+'.preserved-'+os.urandom(6).hex()))
    value=hashlib.sha256()
    with part.open('ab' if offset else 'xb') as target:
        part.chmod(0o600);left=length
        while left:
            block=stream.read(min(left,1024**2))
            if not block:raise ValueError('Incomplete SSH transfer; partial ciphertext retained for checked resume')
            left-=len(block);value.update(block);target.write(block)
        target.flush();os.fsync(target.fileno())
    if value.hexdigest()!=header.get('sha256'):raise ValueError('SSH transfer checksum mismatch')
    if header.get('total_size',offset+length)!=part.stat().st_size or part.stat().st_size>limit:
        raise ValueError('Full transfer size mismatch')
    full=expected_sha256 or header.get('total_sha256')
    if full and sha(part)!=full:raise ValueError('Full transfer checksum mismatch')
    os.replace(part,path)
    return header
