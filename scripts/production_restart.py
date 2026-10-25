#!/usr/bin/env python3
"""Private operator CLI. No command runs automatically at startup/deploy.

Every output/config/approval/key stays outside Git. Mutating operations require
explicit action; production activation additionally requires a signed exact grant.
"""
import argparse
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services import production_restart as control,simulation_archive as archive,simulation_restart as restart
from services.economic_opening import digest


def private_path(value):
    path=Path(value).resolve()
    if path==ROOT or ROOT in path.parents:raise ValueError('Private operator files must stay outside Git')
    return path


def load(value):return json.loads(private_path(value).read_text())


def check_inventory(config):
    from services.production_inventory import discover
    found=discover(extra_roots=config.get('extra_roots'))
    if config.get('inventory_ack_sha256')!=found['inventory_sha256'] or config.get('external_stores_reviewed') is not True:
        raise ValueError('Review current inventory and attest external stores before archiving/activation')
    included=[Path(p).resolve() for p in config['runtime_roots'].values()]
    for source in found['runtime_roots'].values():
        source=Path(source).resolve()
        if not any(source==root or root in source.parents for root in included):raise ValueError('Discovered runtime source omitted')
    if not set(found['database_environment_variables'])<=set(config['database_environment_variables'].values()):
        raise ValueError('Configured database source omitted')
    if config.get('coverage_confirmed') is not True:raise ValueError('Complete archive coverage must be reviewed')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['inventory','account-config','archive','restore','prepare','request','sign','activate','stop','resume','status','dry-run','dry-run-live','provider-check','economic-event'])
    parser.add_argument('--config',required=True);parser.add_argument('--output')
    parser.add_argument('--period');parser.add_argument('--family',choices=list(restart.CAPITALS));parser.add_argument('--archive-id')
    parser.add_argument('--actor');parser.add_argument('--approval-ref');parser.add_argument('--start-at');parser.add_argument('--at')
    parser.add_argument('--input');parser.add_argument('--confirmation');parser.add_argument('--private-key-file');parser.add_argument('--reason')
    parser.add_argument('--sources-quiesced',action='store_true')
    args=parser.parse_args();config=load(args.config)
    if not args.output:raise ValueError('Private --output path required')
    output=private_path(args.output)
    if output.exists():raise ValueError('Output must be new; never overwrite an operator receipt')
    if not output.parent.is_dir():raise ValueError('Prepare private output directory first')
    if args.action=='inventory':
        from services.production_inventory import discover
        result=discover(extra_roots=config.get('extra_roots'))
    elif args.action=='account-config':
        from services.production_routing import strategy_settings
        result={family:dict(capital_nok=capital,settings=strategy_settings(family,require_stored=True),cost_policy=None) for family,capital in restart.CAPITALS.items()}
    elif args.action=='archive':
        check_inventory(config)
        import psycopg2
        connections={}
        try:
            for name,variable in config['database_environment_variables'].items():
                connections[name]=psycopg2.connect(os.environ[variable],connect_timeout=10)
            result=archive.create_archive(config['archive_root'],runtime_roots=config['runtime_roots'],databases=connections,
                certificate=config['certificate'],coverage=config['coverage'],source_quiesced=args.sources_quiesced,
                coverage_confirmed=True,pg_dump_program=config.get('pg_dump_program','pg_dump'))
        finally:
            for conn in connections.values():conn.close()
    elif args.action=='restore':
        result=archive.restore_drill(config['archive_root'],args.archive_id,certificate=config['certificate'],
            private_key=private_path(args.private_key_file),destination=config['restore_destination'],
            database_targets={k:os.environ[v] for k,v in config['restore_database_environment_variables'].items()},
            pg_restore_program=config.get('pg_restore_program','pg_restore'))
    elif args.action=='prepare':
        result=restart.prepare(args.period,start_at=args.start_at,prepared_by=args.actor,
            archive_root=config['archive_root'],archive_id=args.archive_id,certificate=config['certificate'],private_key=private_path(args.private_key_file))
    elif args.action=='request':
        check_inventory(config)
        review=load(str(Path(config['restore_destination'])/'restore-review.json'))
        archive.verify_restore_destination(config['restore_destination'],review)
        result=control.request(args.period,args.family,actor=args.actor,approval_ref=args.approval_ref,at=args.at,
            restore_review=review,settings=config['accounts'][args.family]['settings'],cost_policy=config['accounts'][args.family]['cost_policy'])
    elif args.action=='sign':
        payload=load(args.input)
        if args.confirmation!=digest(payload):raise ValueError('Review and confirm the exact approval fingerprint before signing')
        result=control.sign(payload,private_path(args.private_key_file))
    elif args.action=='activate':
        check_inventory(config)
        result=control.activate(load(args.input),confirmation=args.confirmation,archive_root=config['archive_root'],
            certificate=config['certificate'],private_key=private_path(args.private_key_file),restore_destination=config['restore_destination'],
            database_dsns={name:os.environ[variable] for name,variable in config['database_environment_variables'].items()})
    elif args.action in {'stop','resume'}:
        result={'status':control.stop(args.period,args.family,actor=args.actor,reason=args.reason,confirmation=args.confirmation,resume=args.action=='resume')}
    elif args.action=='status':
        chosen=control.selected(args.family,require_running=False)
        result={'status':'NO_SELECTED_NOK_ACCOUNT'} if chosen is None else dict(pointer=chosen['pointer'],status=chosen['bundle']['production_controls'][args.family]['status'])
    elif args.action=='economic-event':
        result=control.economic_event(args.period,args.family,load(args.input),actor=args.actor,confirmation=args.confirmation)
    elif args.action=='dry-run-live':
        from services.production_routing import live_preview
        result=live_preview(args.period,args.family,strategy_input=load(args.input),cost_policy=config['accounts'][args.family]['cost_policy'])
    else:
        job=load(args.input)
        if args.action=='provider-check':
            from services.production_routing import market_evidence
            from datetime import datetime,timezone
            at=datetime.now(timezone.utc).isoformat();checks={}
            for ticker,currency in job['instruments'].items():
                try:checks[ticker]=dict(status='BESTÅTT',evidence=market_evidence(ticker,currency=currency,at=at,cost_policy=job['cost_policy']))
                except Exception as exc:checks[ticker]=dict(status='IKKE VERIFISERT',error_type=type(exc).__name__,reason=str(exc)[:500])
            result=dict(at=at,checks=checks,ok=all(c['status']=='BESTÅTT' for c in checks.values()) and bool(checks),orders_executed=False)
        else:
            from services.restart_trading import preview
            result=preview(period_id=args.period,family=args.family,**job)
    if not args.output:raise ValueError('Private --output path required; no financial data printed')
    output=private_path(args.output)
    descriptor=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print('Completed '+args.action+'; private output written. SHA256: '+digest(result))
    if args.action=='provider-check' and not result['ok']:raise SystemExit(2)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('Operation stopped ('+type(exc).__name__+'); inspect private inputs. No automatic fallback.',file=sys.stderr)
        raise SystemExit(1)
