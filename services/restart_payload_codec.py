"""Versioned lossless storage encoding; financial callers always receive JSON values."""
import base64
import hashlib
import json
import os
import re
import zlib

MARKER='ZLIB_BASE64_JSON_V1'
PREFIX='{"__restart_storage__":"'+MARKER+'"'
FLAG='RESTART_BUNDLE_COMPRESSION_ENABLED'
MAX_RAW_BYTES=512*1024**2
MAX_STORED_BYTES=64*1024**2
CHUNK_BYTES=65536


class RestartPayloadError(ValueError):
    """A corrupt, unsupported or oversized restart value must fail closed."""


def enabled():
    return os.getenv(FLAG,'').strip().lower() in {'1','true','yes','on'}


def encode_payload(payload):
    if not isinstance(payload,str):
        raise RestartPayloadError('Restart encoding requires serialized JSON text')
    if len(payload)>MAX_RAW_BYTES:
        raise RestartPayloadError('Restart JSON exceeds the 512 MiB decoded-size limit; partition history before writing')
    chunks=(payload[offset:offset+CHUNK_BYTES].encode('utf8') for offset in range(0,len(payload),CHUNK_BYTES))
    return _encode_chunks(chunks)[0]


def encode_document(document):
    """Same JSON bytes as dumps(...ensure_ascii=True, default=str), streamed."""
    def chunks():
        parts=[];size=0
        for piece in json.JSONEncoder(ensure_ascii=True,default=str).iterencode(document):
            if size+len(piece)>CHUNK_BYTES and parts:
                yield ''.join(parts).encode('ascii');parts=[];size=0
            if len(piece)>CHUNK_BYTES:
                for start in range(0,len(piece),CHUNK_BYTES):
                    yield piece[start:start+CHUNK_BYTES].encode('ascii')
            else:parts.append(piece);size+=len(piece)
        if parts:yield ''.join(parts).encode('ascii')
    return _encode_chunks(chunks())


def _encode_chunks(chunks, *, max_raw_bytes=None, max_stored_bytes=None):
    raw_limit = MAX_RAW_BYTES if max_raw_bytes is None else min(MAX_RAW_BYTES, max_raw_bytes)
    stored_limit = MAX_STORED_BYTES if max_stored_bytes is None else min(MAX_STORED_BYTES, max_stored_bytes)
    compressor=zlib.compressobj(6);checksum=hashlib.sha256();parts=[];size=0;compressed_size=0
    def append(piece):
        nonlocal compressed_size
        compressed_size+=len(piece)
        if 4*((compressed_size+2)//3)+512>stored_limit:
            raise RestartPayloadError('Encoded restart JSON exceeds the 64 MiB database-write limit; partition history before writing')
        parts.append(piece)
    for chunk in chunks:
        size+=len(chunk)
        if size>raw_limit:raise RestartPayloadError('Restart JSON exceeds the 512 MiB decoded-size limit')
        checksum.update(chunk);append(compressor.compress(chunk))
    append(compressor.flush())
    packed=b''.join(parts);parts.clear()
    encoded=base64.b64encode(packed);del packed
    data=encoded.decode('ascii');del encoded
    header=json.dumps({'__restart_storage__':MARKER,'uncompressed_bytes':size,
                       'sha256':checksum.hexdigest()},separators=(',',':'),ensure_ascii=True)
    # Base64 contains no JSON escapes. Join once rather than copying the large
    # data string through JSONEncoder's temporary chunk list.
    result=''.join((header[:-1],',"data":"',data,'"}'))
    if len(result)>stored_limit:
        raise RestartPayloadError('Encoded restart JSON exceeds the 64 MiB database-write limit; partition history before writing')
    return result,size


def decode_document(value, payload_loader=None):
    if not isinstance(value,dict) or '__restart_storage__' not in value:
        return value
    from services.restart_payload_archive import MARKER as ARCHIVED_MARKER
    archived = value.get('__restart_storage__') == ARCHIVED_MARKER
    if archived:
        value = {**value, '__restart_storage__': MARKER}
    if set(value)!={'__restart_storage__','uncompressed_bytes','sha256','data'} or value['__restart_storage__']!=MARKER:
        raise RestartPayloadError('Unsupported restart storage encoding')
    size=value['uncompressed_bytes'];checksum=value['sha256'];encoded=value['data']
    if type(size) is not int or not 0<=size<=MAX_RAW_BYTES:
        raise RestartPayloadError('Invalid restart decoded-size bound')
    if not isinstance(checksum,str) or not re.fullmatch('[0-9a-f]{64}',checksum):
        raise RestartPayloadError('Invalid restart checksum metadata')
    if not isinstance(encoded,str) or len(encoded)>MAX_STORED_BYTES:
        raise RestartPayloadError('Invalid restart encoded-size bound')
    def chunks():
        import codecs
        decoder=zlib.decompressobj();hasher=hashlib.sha256();count=0
        utf8=codecs.getincrementaldecoder('utf8')('strict')
        for offset in range(0,len(encoded),CHUNK_BYTES):
            part=encoded[offset:offset+CHUNK_BYTES]
            if offset+len(part)<len(encoded) and '=' in part:
                raise RestartPayloadError('Invalid restart base64 padding')
            pending=base64.b64decode(part,validate=True)
            while pending:
                raw=decoder.decompress(pending,min(CHUNK_BYTES,size-count+1))
                pending=decoder.unconsumed_tail;count+=len(raw)
                if count>size:raise RestartPayloadError('Restart stream length mismatch')
                hasher.update(raw)
                yield utf8.decode(raw,final=False)
        if count!=size or not decoder.eof or decoder.unused_data:
            raise RestartPayloadError('Restart stream length or termination mismatch')
        if hasher.hexdigest()!=checksum:raise RestartPayloadError('Restart checksum mismatch')
        yield utf8.decode(b'',final=True)
    try:
        from services.restart_json_stream import load
        result = load(chunks())
        if archived:
            from services.restart_payload_archive import hydrate
            return hydrate(result, payload_loader)
        return result
    except RestartPayloadError:
        raise
    except (ValueError,zlib.error) as exc:
        raise RestartPayloadError('Invalid decoded restart JSON') from exc
