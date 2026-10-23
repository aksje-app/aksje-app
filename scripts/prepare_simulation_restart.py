#!/usr/bin/env python3
"""Operator tool: encrypted archive, restore review and three INACTIVE drafts.

Config contains paths and environment-variable NAMES, never database passwords.
No reset, strategy changes, production activation, merge or deploy command.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.simulation_archive import create_archive,verify_archive
from services.simulation_restart import plan,prepare


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['plan','archive','review','prepare'])
    parser.add_argument('--config',required=True,help='Private operator JSON configuration outside Git')
    parser.add_argument('--archive-id')
    parser.add_argument('--period-id')
    parser.add_argument('--start-at')
    parser.add_argument('--actor')
    parser.add_argument('--private-key-file')
    parser.add_argument('--sources-quiesced',action='store_true')
    args=parser.parse_args();config_path=Path(args.config).resolve()
    if config_path==ROOT or ROOT in config_path.parents:parser.error('Operator config must stay outside Git')
    config=json.loads(config_path.read_text())
    if args.action=='plan':
        if not all((args.period_id,args.start_at,args.actor)):parser.error('Plan requires period ID, explicit start time and actor')
        result=plan(args.period_id,start_at=args.start_at,prepared_by=args.actor)
        print(json.dumps(result,ensure_ascii=False,indent=2));return
    if args.action=='archive':
        import psycopg2
        connections={}
        try:
            for name,variable in config['database_environment_variables'].items():
                value=os.getenv(variable)
                if not value:raise ValueError('Declared database environment variable is not configured')
                connections[name]=psycopg2.connect(value,connect_timeout=10)
            result=create_archive(config['archive_root'],runtime_roots=config['runtime_roots'],databases=connections,
                certificate=config['certificate'],coverage=config['coverage'],
                source_quiesced=args.sources_quiesced,coverage_confirmed=config.get('coverage_confirmed') is True,
                pg_dump_program=config.get('pg_dump_program','pg_dump'))
            print('Sealed private archive created: '+result['archive_id'])
        finally:
            for connection in connections.values():connection.close()
        return
    if not args.archive_id or not args.private_key_file:parser.error('Archive ID and offline private-key file required')
    if args.action=='review':
        result=verify_archive(config['archive_root'],args.archive_id,certificate=config['certificate'],private_key=args.private_key_file)
        print('Restore review verified: '+result['archive_id']);return
    if not all((args.period_id,args.start_at,args.actor)):parser.error('Preparation requires period ID, explicit start time and actor')
    result=prepare(args.period_id,start_at=args.start_at,prepared_by=args.actor,
        archive_root=config['archive_root'],archive_id=args.archive_id,certificate=config['certificate'],private_key=args.private_key_file)
    print('Three inactive simulation accounts prepared: '+result['period_id'])


if __name__=='__main__':
    try:main()
    except Exception as exc:
        # No traceback containing connection details, source values or secrets.
        print('Operation stopped ('+type(exc).__name__+'). Review private inputs; no activation performed.',file=sys.stderr)
        raise SystemExit(1)
