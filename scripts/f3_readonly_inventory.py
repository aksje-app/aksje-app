#!/usr/bin/env python3
"""Explicit read-only source collection. Raw data MUST stay outside the checkout.

No StorageService import, initialization, migrations, portfolio writes or logs
of database URLs/payloads. Requires a separately supplied read-only connection.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile

REPO=Path(__file__).resolve().parents[1]
KEYS=['paper_trading/portfolio.json','autonomous_portfolio/portfolio.json',
      'autonomous_portfolio/trades.json','super_portfolio/state.json',
      'super_portfolio/transactions.jsonl','superfund/snapshot.json','superfund/parameters.json']
STREAMS=['super_portfolio/transactions.jsonl','super_portfolio/audit.jsonl','autonomous_portfolio/audit.jsonl']
TABLES=('paper_state','paper_positions','paper_trades')
MAX_BYTES=64*1024*1024


def private_destination(path):
    target=Path(path).resolve()
    if target==REPO or REPO in target.parents:
        raise ValueError('Production evidence must remain outside the Git checkout')
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if target.exists():raise ValueError('Do not overwrite an existing evidence export')
    return target


def export_postgres(connection, *, max_rows=10000):
    """An actual repeatable-read, read-only transaction. Never initialize tables."""
    from psycopg2 import sql
    connection.set_session(readonly=True,isolation_level='REPEATABLE READ',autocommit=False)
    result={'source_kind':'READ_ONLY_POSTGRES_EXPORT','documents':{},'streams':{},'tables':{},'absent_tables':[]}
    with connection.cursor() as cur:
        cur.execute('SHOW transaction_read_only')
        if cur.fetchone()[0]!='on':raise ValueError('Read-only transaction required')
        cur.execute("SET LOCAL statement_timeout = '15000ms'")
        cur.execute('SELECT transaction_timestamp()::text')
        result['as_of']=cur.fetchone()[0]
        for table in ('app_kv_store','app_jsonl_store',*TABLES):
            cur.execute('SELECT to_regclass(%s)',(table,))
            if cur.fetchone()[0] is None:
                result['absent_tables'].append(table);continue
            if table=='app_kv_store':
                cur.execute('SELECT name,payload,updated_at FROM app_kv_store WHERE name=ANY(%s) ORDER BY name LIMIT %s',(KEYS,max_rows+1))
                rows=cur.fetchall()
                result['documents']={n:{'payload':json.loads(p),'updated_at':at} for n,p,at in rows}
            elif table=='app_jsonl_store':
                cur.execute('SELECT name,payload,id,created_at FROM app_jsonl_store WHERE name=ANY(%s) ORDER BY id LIMIT %s',(STREAMS,max_rows+1))
                rows=cur.fetchall()
                for name,payload,identity,at in rows:
                    result['streams'].setdefault(name,[]).append({'id':identity,'created_at':at,'payload':json.loads(payload)})
            else:
                # Identifiers are from the closed whitelist, never user SQL.
                cur.execute(sql.SQL('SELECT * FROM {} LIMIT %s').format(sql.Identifier(table)),(max_rows+1,))
                fields=[d[0] for d in cur.description];rows=cur.fetchall()
                result['tables'][table]=[dict(zip(fields,row)) for row in rows]
            if len(rows)>max_rows:raise ValueError('Evidence row budget exceeded; refusing a silently truncated export')
            if len(json.dumps(result,default=str).encode())>MAX_BYTES:raise ValueError('Evidence byte budget exceeded')
    connection.rollback()  # End the read-only snapshot; never commit production.
    return result


def inspect_archive(path):
    """Keep raw original bytes private; inventory without extracting any paths."""
    source=Path(path)
    if source.stat().st_size>MAX_BYTES:raise ValueError('Archive size budget exceeded')
    raw=source.read_bytes()
    with zipfile.ZipFile(source) as archive:
        entries=archive.infolist()
        if len(entries)>5000 or sum(i.file_size for i in entries)>MAX_BYTES:
            raise ValueError('Uncompressed evidence budget exceeded')
        result={'source_kind':'SUPPLIED_MODEL_DIAGNOSTIC_ARCHIVE','sha256':hashlib.sha256(raw).hexdigest(),'files':[]}
        for entry in entries:
            if entry.filename.startswith('/') or '..' in Path(entry.filename).parts:
                raise ValueError('Unsafe archive path')
            payload=archive.read(entry)
            result['files'].append({'name':entry.filename,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()})
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--archive')
    args=parser.parse_args();destination=private_destination(args.output)
    if args.archive:
        result=inspect_archive(args.archive)
    else:
        url=os.getenv('F3_READONLY_DATABASE_URL')
        if not url:parser.error('F3_READONLY_DATABASE_URL is not configured; no production query attempted')
        import psycopg2
        connection=psycopg2.connect(url,connect_timeout=10)
        try:result=export_postgres(connection)
        finally:connection.close()
    raw=json.dumps(result,ensure_ascii=False,default=str,indent=2).encode()
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw)
    print('Private read-only evidence written outside Git; no payload printed.')


if __name__=='__main__':main()
