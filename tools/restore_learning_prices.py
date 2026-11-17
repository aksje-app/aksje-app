#!/usr/bin/env python3
"""Restore selected cold prices from an isolated recovered DB; dry-run by default.

Connection strings are supplied privately in environment variables, not command
arguments or output. Never restore the full database into production for this.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.learning_price_archive import MAX_PRICE_BYTES, restore_price, validate_key
from services.storage_service import StorageService


def restore_selected(source_connection, target, keys, *, apply=False):
    keys = list(keys)
    if not 0 < len(keys) <= 128 or len(set(keys)) != len(keys):
        raise ValueError('Supply 1 to 128 unique exact price keys')
    for key in keys:
        validate_key(key)
    if source_connection.readonly is not True:
        raise ValueError('Recovery source must be read-only')
    if not target.using_postgres() or target.allow_local_fallback:
        raise ValueError('Restore target must be authoritative PostgreSQL')
    results = []
    with source_connection.cursor() as cur:
        for key in keys:
            cur.execute('SELECT payload FROM app_kv_store WHERE name=%s AND octet_length(payload)<=%s',
                        (key, MAX_PRICE_BYTES))
            row = cur.fetchone()
            if row is None:
                raise ValueError('Original source missing or exceeds the restore budget')
            results.append(restore_price(target, key, row[0], apply=apply))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key', action='append', required=True, help='Exact strategy_history/prices/<sha256>.json key; repeat up to 128 times')
    parser.add_argument('--apply', action='store_true', help='Restore verified original bytes after reviewing a dry-run')
    args = parser.parse_args()
    source_url = os.getenv('LEARNING_ARCHIVE_SOURCE_DATABASE_URL', '')
    target_url = os.getenv('DATABASE_URL', '')
    if not source_url or not target_url or urlsplit(source_url).hostname not in {'localhost', '127.0.0.1', '::1'}:
        parser.error('Set a local isolated LEARNING_ARCHIVE_SOURCE_DATABASE_URL and the intended DATABASE_URL privately')
    import psycopg2
    source = None
    try:
        source = psycopg2.connect(source_url)
        source.set_session(readonly=True, isolation_level='REPEATABLE READ')
        target = StorageService(database_url=target_url, mode='postgres', allow_local_fallback=False)
        result = restore_selected(source, target, args.key, apply=args.apply)
        print(json.dumps({'state': 'APPLIED' if args.apply else 'DRY_RUN', 'results': result}))
        return 0
    except Exception as exc:
        # Do not echo source data, URLs or credentials from driver exceptions.
        print(json.dumps({'state': 'FAILED', 'error_type': type(exc).__name__,
                          'partial_restore_possible': args.apply}), file=sys.stderr)
        return 1
    finally:
        if source is not None:
            source.close()


if __name__ == '__main__':
    raise SystemExit(main())
