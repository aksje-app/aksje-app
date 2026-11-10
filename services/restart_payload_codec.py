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
    compressor=zlib.compressobj(6);checksum=hashlib.sha256();parts=[];size=0;compressed_size=0
    def append(piece):
        nonlocal compressed_size
        compressed_size+=len(piece)
        if 4*((compressed_size+2)//3)+512>MAX_STORED_BYTES:
            raise RestartPayloadError('Encoded restart JSON exceeds the 64 MiB database-write limit; partition history before writing')
        parts.append(piece)
    for offset in range(0,len(payload),CHUNK_BYTES):
        chunk=payload[offset:offset+CHUNK_BYTES].encode('utf8');size+=len(chunk)
        if size>MAX_RAW_BYTES:raise RestartPayloadError('Restart JSON exceeds the 512 MiB decoded-size limit')
        checksum.update(chunk);append(compressor.compress(chunk))
    append(compressor.flush())
    record={'__restart_storage__':MARKER,'uncompressed_bytes':size,
            'sha256':checksum.hexdigest(),'data':base64.b64encode(b''.join(parts)).decode('ascii')}
    result=json.dumps(record,separators=(',',':'),ensure_ascii=True)
    if len(result)>MAX_STORED_BYTES:
        raise RestartPayloadError('Encoded restart JSON exceeds the 64 MiB database-write limit; partition history before writing')
    return result


def decode_document(value):
    if not isinstance(value,dict) or '__restart_storage__' not in value:
        return value
    if set(value)!={'__restart_storage__','uncompressed_bytes','sha256','data'} or value['__restart_storage__']!=MARKER:
        raise RestartPayloadError('Unsupported restart storage encoding')
    size=value['uncompressed_bytes'];checksum=value['sha256'];encoded=value['data']
    if type(size) is not int or not 0<=size<=MAX_RAW_BYTES:
        raise RestartPayloadError('Invalid restart decoded-size bound')
    if not isinstance(checksum,str) or not re.fullmatch('[0-9a-f]{64}',checksum):
        raise RestartPayloadError('Invalid restart checksum metadata')
    if not isinstance(encoded,str) or len(encoded)>MAX_STORED_BYTES:
        raise RestartPayloadError('Invalid restart encoded-size bound')
    try:
        compressed=base64.b64decode(encoded,validate=True)
        decoder=zlib.decompressobj();raw=decoder.decompress(compressed,size+1)
    except (ValueError,zlib.error) as exc:
        raise RestartPayloadError('Invalid restart compressed stream') from exc
    if len(raw)!=size or not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
        raise RestartPayloadError('Restart stream length or termination mismatch')
    if hashlib.sha256(raw).hexdigest()!=checksum:
        raise RestartPayloadError('Restart checksum mismatch')
    try:text=raw.decode('utf8')
    except UnicodeDecodeError as exc:raise RestartPayloadError('Invalid restart JSON encoding') from exc
    del raw,compressed
    try:return json.loads(text)
    except ValueError as exc:raise RestartPayloadError('Invalid decoded restart JSON') from exc
