"""Bounded read-only cost evidence. No initialization, migration or activation.

Run inline in the existing Render SSH session; only stdout is returned. No app
loaders are called: several of those migrate or initialize their stores.
"""
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone

SERVICE = 'srv-d7obt5e47okc739susgg'
PERIOD = 'nok-20261025T012118Z'
ARCHIVE = '20261024T232608Z-4df389aad81c4186949d7133e32c0649'
REVIEW_SHA = '3118134d55f84c0935ab4d22704117db160bd730f46636ab5488547290f1e90a'
CAPITALS = {'paper': 100000.0, 'autonomy': 500000.0, 'super_portfolio': 1000000.0}
ROOT = Path('/opt/render/project/src')
WORK = Path('/tmp/nok-job-20261024T165039Z')
MAX_RAW = 160 * 1024**2
MAX_FIELD = 1024**2
# Replaced by build_audit_runner.py from the reviewed source checkout.
SOURCE_HASHES = {'backtesting_engine.py': '5f0033e8e7a2506a6c3f00016b8c716f9f6db968f7162bc96df48d65f8b8a200', 'backtest_strategy.py': 'c1e22d21d187b017ccc386b702bc85f714cfb3d8190cf9daf1a72e4f233ccc0b', 'trading_engine.py': '82b318c6d2b7c4ddcefe6181788ff24feb85316a65628299a60dc64a2f3dd920', 'trading_settings.py': '1a71be2e8c9100516703f31e299df365d3bb49c5a4411a7b31bd8e365018ec7a', 'paper_store.py': '9b1b3900cffe687880d48d8df6eb459e9a770c11f8bc1b8513417facb00fa301', 'autonomous_portfolio.py': '1dbed01393c280a34f2139d3e33b62f387a8c732f93031943636c40ea4d056f5', 'learning_runtime.py': '0b64e582550a06a84137b84f592693ca9ee02899d0d8d8edab569608efb6acdb', 'exit_policy.py': '5aa786e7f75a7262ff924b108595ae160ca23334cd56f225963fe9ef57657041', 'super_portfolio.py': 'c4e4adaee25e9ca6ced762693052337c39fb912bbb127e56441954d28400a4d2', 'superfund_engine.py': 'eb29bd8ad3c317bb66f6a28ba15bd50ab6f9107d986e3c90b67da8c2e04d0a4f', 'services/super_portfolio_accounting.py': '34bea4f8bde803c3854954bbd67d9a6d924b60cb6f02a882adc96e5d093a68e0', 'services/super_portfolio_store.py': '6974876b8280d6a66d145142049da7065a00ec024d00f5b96345ab1c109524e0', 'services/production_routing.py': '0760edce56eda264189a44bfd83898ee1792216781608c58b83c2e0019b9e3b3', 'services/production_restart.py': '12a2583dfdda5a4f7ea72a275b44e0abf68cfc7d4a5ab242ef3c25148bb7e59e', 'services/restart_trading.py': '20e3f5944cb3f01cb431a784fd4f8701ff55e5ee3b019074c7ca54316aeff96e', 'services/simulation_restart.py': 'a041629703c7c3df8146681a4584b025c3b44959bb388227c514ead3257ee98b', 'services/simulation_archive.py': '6248b8371cb362c8fe98db14f8ec53ce14ad9fc7413686adb279e6fae1fb0949', 'services/portfolio_accounting.py': '908fc52b65eb40c654184cb240453130a76da0e420133b00ce51e257e76145e4', 'services/economic_opening.py': '94b4d7e085e667ccd97d8eb35c4f8b76643baf9e1b3a88a9790c9cf466daf5ca', 'services/economic_ledger.py': '0139e84a9d11a67d196c4d3a251a2f08603844a9eccfe06017fc99fa8fd044de', 'services/economic_events.py': 'dd3903fa599146514d5ebf7dde5a3f071221ba841e2ff03959201da0eca47d1b', 'services/economic_accounting_audit.py': '638cee3dd713ad199b59bdd3c16cf00781626fd28c60d2c5503dae50c5d800ea', 'services/storage_service.py': 'c5fd2843d6ccd298dc92df0b719966b23014a38a3aa092e853b066f6159badbd', 'services/simulated_execution_service.py': 'b619edc2bc52e7aa10dbb3fefab99b13d260bb4b80addf4e98955fc05dc631ae'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def file_sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024**2), b''):
            value.update(chunk)
    return value.hexdigest()


def metadata(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4*1024**2:
        raise ValueError('Expected bounded regular metadata file')
    return json.loads(path.read_text(encoding='utf-8-sig'))


# Skip unneeded JSON subtrees without deserializing positions/history/models.
# The caller holds one bounded native UTF8 byte value, never row_to_json/JSONB.
STRING_MARK = re.compile(rb'["\\]')
TOKEN = re.compile(rb'["\[\]{}]')
WS = b' \r\n\t'


def space(raw, offset):
    while offset < len(raw) and raw[offset] in WS:
        offset += 1
    return offset


def string_end(raw, offset):
    position = offset+1
    while True:
        m = STRING_MARK.search(raw, position)
        if not m: raise ValueError('Invalid JSON string')
        if m.group() == b'"': return m.end()
        position = m.end()+1  # escaped character cannot terminate this string


def end_value(raw, offset):
    offset = space(raw, offset)
    if offset >= len(raw):
        raise ValueError('Truncated JSON')
    if raw[offset] == 34:
        return string_end(raw, offset)
    if raw[offset] not in (91, 123):
        match = re.match(rb'[^,}\]\s]+', raw[offset:offset+128])
        if not match: raise ValueError('Invalid JSON scalar')
        return offset + match.end()
    depth, position = 1, offset+1
    while depth:
        m = TOKEN.search(raw, position)
        if not m: raise ValueError('Truncated JSON container')
        if m.group() == b'"':
            position = string_end(raw, m.start())
        else:
            depth += 1 if m.group() in (b'[', b'{') else -1
            if depth > 256: raise ValueError('Unexpected JSON depth')
            position = m.end()
    return position


def fields(raw):
    position = space(raw, 0)
    if raw[position:position+1] != b'{': raise ValueError('Expected object')
    position += 1
    found = set()
    for _ in range(4096):
        position = space(raw, position)
        if raw[position:position+1] == b'}':
            if space(raw, position+1) != len(raw): raise ValueError('Trailing JSON')
            return
        key_end = end_value(raw, position)
        if key_end-position > 4096: raise ValueError('Unexpected key length')
        key = json.loads(raw[position:key_end])
        if not isinstance(key, str) or key in found: raise ValueError('Duplicate/invalid key')
        found.add(key)
        position = space(raw, key_end)
        if raw[position:position+1] != b':': raise ValueError('Missing colon')
        start = space(raw, position+1)
        end = end_value(raw, start)
        yield key, start, end
        position = space(raw, end)
        if raw[position:position+1] == b',': position += 1
        elif raw[position:position+1] != b'}': raise ValueError('Missing separator')
    raise ValueError('Unexpected object field count')


def selected_fields(raw, names):
    result = {}
    for key, start, end in fields(raw):
        if key in names:
            if end-start > MAX_FIELD: raise ValueError('Selected field exceeds bounded JSON budget')
            result[key] = json.loads(raw[start:end])
    return result


def cost_fields(value):
    if not isinstance(value, dict): return {}
    return {str(k): v for k, v in value.items() if
            any(word in str(k).lower() for word in ('cost', 'fee', 'commission', 'slippage', 'brokerage', 'fx_bps'))
            and (v is None or isinstance(v, (str, int, float, bool)))}


def raw_document(q, key):
    # Transaction snapshot is stable between the size check and native read.
    q.execute('SELECT octet_length(payload) FROM public.app_kv_store WHERE name=%s', (key,))
    row = q.fetchone()
    if row is None: return None
    if row[0] > MAX_RAW: raise ValueError('Document exceeds native read capacity')
    q.execute('SELECT payload FROM public.app_kv_store WHERE name=%s AND octet_length(payload)<=%s', (key, MAX_RAW))
    value = q.fetchone()[0]
    if not isinstance(value, bytes): raise ValueError('Native UTF8 bytes required')
    return value


def file_document(relative):
    base = Path(os.getenv('APP_RUNTIME_ROOT', '.app_runtime'))
    if not base.is_absolute(): base = ROOT/base
    target = base/'data'/relative
    # Inspect a configured runtime source only; do not create a fallback tree.
    if not target.exists(): return None
    if target.is_symlink() or not target.is_file() or target.stat().st_size > MAX_RAW:
        raise ValueError('Unexpected runtime source')
    if not target.resolve().is_relative_to(base.resolve()): raise ValueError('Unexpected runtime path')
    return target.read_bytes()


def cost_config(q, key, relative, wanted):
    raw = raw_document(q, key)
    source = 'PostgreSQL:app_kv_store:'+key
    if raw is None and relative is not None:
        raw = file_document(relative)
        source = 'RUNTIME_FILE:'+relative
    if raw is None: return dict(source='ABSENT', stored=False)
    selected = selected_fields(raw, wanted)
    config = selected.get('config', {})
    if isinstance(config, dict):
        # Export only actual dataclass strategy fields, never arbitrary settings.
        tree = ast.parse((ROOT/'super_portfolio.py').read_text())
        klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SuperPortfolioConfig')
        allowed = {n.target.id for n in klass.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
        config = {k: v for k, v in config.items() if k in allowed}
        if 'config' in selected: selected['config'] = config
    return dict(source=source, stored=True, native_bytes=len(raw), document_sha256=hashlib.sha256(raw).hexdigest(),
                selected_fields=selected, config_cost_fields=cost_fields(config))


def verified_drafts(bundle):
    # Import only the unchanged pure verification routines, not store instances.
    from services.simulation_restart import verify_bundle
    verify_bundle(bundle)
    if (bundle['period_id'] != PERIOD or bundle.get('production_controls') or
        bundle['status'] != 'PREPARED_NOT_ACTIVE' or bundle['archive']['archive_id'] != ARCHIVE):
        raise ValueError('Unexpected period or authorization state')
    accounts = {}
    for family, capital in CAPITALS.items():
        document = bundle['accounts'][family]
        account = document['account']
        if (document['status'] != 'DRAFT' or document.get('approval') is not None or
            account['positions'] or account['trades'] or account['cash'] != capital or
            account['initial_cash'] != capital or account['fees_paid'] != 0 or
            account['realized_pnl'] != 0 or len(document['events']) != 1 or
            document['events'][0]['kind'] != 'PREPARED'):
            raise ValueError('Current account differs from unapproved opening')
        accounts[family] = dict(status='DRAFT', cash_nok=capital, opening_nav_nok=capital,
                               positions=0, trades=0, fees_paid_nok=0, approval=None,
                               opening_sha256=document['opening_sha256'])
    return accounts


def file_receipts(bundle):
    if WORK.is_symlink() or WORK.stat().st_uid != os.geteuid() or WORK.stat().st_mode & 0o077:
        raise ValueError('Private original operator job required')
    receipt = metadata(WORK/'archive-receipt.json')
    final = metadata(WORK/'final-result.json')
    review = metadata(WORK/'local-restore-review.json')
    copy = metadata(WORK/'windows-copy-proof.json')
    decrypt = metadata(WORK/'windows-decryption-proof.json')
    body = {k: v for k, v in review.items() if k != 'review_sha256'}
    if (receipt['archive_id'] != ARCHIVE or review.get('review_sha256') != REVIEW_SHA or
        digest(body) != REVIEW_SHA or final.get('restore_review_sha256') != REVIEW_SHA or
        final.get('period_id') != PERIOD or final.get('accounts_activated') is not False or
        review.get('status') != 'RESTORED_AND_VERIFIED' or
        review.get('restore_execution_host') != 'WINDOWS_LOCAL_POSTGRESQL_18' or
        any(bundle['archive'].get(k) != receipt.get(k) for k in bundle['archive']) or
        any(review['archive'].get(k) != receipt.get(k) for k in bundle['archive']) or
        copy.get('archive_id') != ARCHIVE or copy.get('cipher_sha256') != receipt['cipher_sha256'] or
        copy.get('verified_windows_copy') is not True or copy.get('local_decryption_verified') is not True or
        decrypt.get('local_openssl_decryption_verified') is not True or
        decrypt.get('archive_id') != ARCHIVE or decrypt.get('cipher_sha256') != receipt['cipher_sha256']):
        raise ValueError('Archive/physical restore receipts do not match actual period')
    sealed = WORK/'archives'/ARCHIVE
    stored = metadata(sealed/'receipt.json')
    if stored != receipt or (sealed/'archive.cms').is_symlink() or file_sha(sealed/'archive.cms') != receipt['cipher_sha256']:
        raise ValueError('Existing sealed ciphertext does not match receipt')
    from services.simulation_archive import _inventory
    restored_review = metadata(WORK/'restore/restore-review.json')
    restored_result = metadata(WORK/'restore-result.json')
    payload = WORK/'restore/payload'
    if (restored_review != review or restored_result != review or payload.is_symlink() or
        _inventory(payload) != review['files'] or file_sha(payload/'manifest.json') != receipt['manifest_sha256']):
        raise ValueError('Retained restored files differ from original physical restore evidence')
    manifest = metadata(payload/'manifest.json')
    fingerprints = manifest['database_model_fingerprints']
    if set(fingerprints) != set(review['databases']): raise ValueError('Restored database coverage differs')
    tables = {}
    for alias, proof in review['databases'].items():
        expected = fingerprints[alias]
        if (proof.get('status') != 'RESTORED' or proof.get('model_fingerprint_sha256') != digest(expected) or
            proof.get('tables') != {table: value['rows'] for table, value in expected.items()}):
            raise ValueError('Physical database restore/fingerprint proof differs from archive manifest')
        tables[alias] = dict(table_count=len(expected), model_fingerprint_sha256=digest(expected))
    return dict(archive_id=ARCHIVE, cipher_sha256=receipt['cipher_sha256'],
                manifest_sha256=receipt['manifest_sha256'], sealed_cipher_sha256_rechecked=True,
                retained_restore_files_sha256_rechecked=True, database_restore_proofs=tables,
                physical_restore_status=review['status'], restore_execution_host=review['restore_execution_host'],
                restore_review_sha256=REVIEW_SHA, restore_review_digest_rechecked=True,
                windows_copy_receipt_present=bool(copy), windows_decryption_receipt_present=bool(decrypt),
                final_receipt_sha256=file_sha(WORK/'final-result.json'),
                note='Reconciles original physical restore receipts; does not rerun restore or claim a new restore test')


def summarize_cost_rows(rows, source):
    result = dict(source=source, rows=0, explicit_cost_rows=0, missing_cost_rows=0,
                  unavailable_or_oversized_rows=0, rates_bps=[], cost_units=[], totals_by_unit={},
                  explicit_fx_cost_rows=0, explicit_slippage_rows=0,
                  cost_components_nok_totals={k:None for k in ('brokerage_nok','fx_cost_nok','other_nok')},
                  component_present_rows={k:0 for k in ('brokerage_nok','fx_cost_nok','other_nok')})
    rates, units = set(), set()
    for raw in rows:
        result['rows'] += 1
        if raw is None:
            result['unavailable_or_oversized_rows'] += 1
            continue
        item = json.loads(raw)
        if not isinstance(item, dict): raise ValueError('Journal record must be an object')
        fee = item.get('transaction_cost', item.get('fee'))
        if isinstance(fee, (int, float)) and not isinstance(fee, bool) and math.isfinite(fee):
            result['explicit_cost_rows'] += 1
            unit = item.get('cost_currency') or item.get('portfolio_currency') or 'UNSPECIFIED_MODEL_UNIT'
            units.add(unit)
            result['totals_by_unit'][unit] = result['totals_by_unit'].get(unit, 0) + fee
        else: result['missing_cost_rows'] += 1
        rate = item.get('cost_bps')
        if isinstance(rate, (int, float)) and not isinstance(rate, bool) and math.isfinite(rate): rates.add(rate)
        components = item.get('cost_components') or {}
        if not isinstance(components, dict): raise ValueError('Invalid cost components')
        for key in result['cost_components_nok_totals']:
            if key in components:
                value = components[key]
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
                    raise ValueError('Invalid explicit cost component')
                result['component_present_rows'][key] += 1
                result['cost_components_nok_totals'][key] = (result['cost_components_nok_totals'][key] or 0)+value
        result['explicit_fx_cost_rows'] += int('fx_cost_nok' in components)
        result['explicit_slippage_rows'] += int('slippage_value' in item or 'slippage_bps' in item)
        if len(rates) > 128: raise ValueError('Unexpected cost rate variants')
    result.update(rates_bps=sorted(rates), cost_units=sorted(units))
    return result


def array_rows(raw):
    position = space(raw, 0)
    if raw[position:position+1] != b'[': raise ValueError('Expected trade array')
    position += 1
    while True:
        position = space(raw, position)
        if raw[position:position+1] == b']': return
        end = end_value(raw, position)
        yield raw[position:end] if end-position <= MAX_FIELD else None
        position = space(raw, end)
        if raw[position:position+1] == b',': position += 1
        elif raw[position:position+1] != b']': raise ValueError('Invalid trade array')


def autonomy_costs(q):
    key = 'autonomous_portfolio/trades.json'
    raw = raw_document(q, key)
    source = 'PostgreSQL:app_kv_store:'+key
    if raw is None:
        raw = file_document(key)
        source = 'RUNTIME_FILE:'+key
    return summarize_cost_rows(array_rows(raw), source) if raw is not None else dict(source='ABSENT', missing=True)


def paper_costs(q):
    # Includes every trade's metadata but no prices, instruments or model payloads in output.
    with q.connection.cursor(name='paper_cost_metadata') as stream:
        from psycopg2 import extensions
        extensions.register_type(extensions.BYTES, stream)
        stream.itersize = 25
        stream.execute('SELECT CASE WHEN octet_length(evidence_metadata)<=1048576 THEN evidence_metadata ELSE NULL END FROM public.paper_trades ORDER BY id')
        return summarize_cost_rows((row[0] for row in stream), 'PostgreSQL:paper_trades:evidence_metadata')


def journal_costs(q, key):
    # Enumerate the actual native JSONL ledger; never use whole-row JSON casting.
    q.execute('SELECT to_regclass(%s)', ('public.app_jsonl_store',))
    if q.fetchone()[0] is None: return dict(source=key, table_absent=True)
    with q.connection.cursor(name='cost_journal') as stream:
        from psycopg2 import extensions
        extensions.register_type(extensions.BYTES, stream)
        stream.itersize = 25
        stream.execute('SELECT CASE WHEN octet_length(payload)<=1048576 THEN payload ELSE NULL END FROM public.app_jsonl_store WHERE name=%s ORDER BY id', (key,))
        return summarize_cost_rows((row[0] for row in stream), 'PostgreSQL:app_jsonl_store:'+key)


def main():
    sys.dont_write_bytecode = True
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    sys.path.insert(0, str(ROOT))
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (768*1024**2, 768*1024**2))
    if os.getenv('APP_ENVIRONMENT') != 'production' or os.getenv('STORAGE_MODE') != 'postgres':
        raise ValueError('Actual production PostgreSQL environment required')
    if os.getenv('RENDER_SERVICE_ID') != SERVICE: raise ValueError('Wrong Render service')
    matched = {name: file_sha(ROOT/name) == sha for name, sha in SOURCE_HASHES.items()}
    if not matched or not all(matched.values()): raise ValueError('Reviewed deployed cost/verification sources differ')
    # Independent of user data; verify the exact host has enough native read budget.
    group = Path('/sys/fs/cgroup')
    limit, used = int((group/'memory.max').read_text()), int((group/'memory.current').read_text())
    stats = dict(line.split() for line in (group/'memory.stat').read_text().splitlines())
    if limit-used+min(used,int(stats.get('inactive_file',0))) < 768*1024**2:
        raise ValueError('Insufficient read-only audit memory headroom')
    import psycopg2
    from psycopg2 import extensions
    connection = psycopg2.connect(os.environ['DATABASE_URL'], connect_timeout=15,
        application_name='aksje_readonly_cost_audit',
        options='-c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=2000 -c work_mem=1MB')
    try:
        connection.set_session(readonly=True, isolation_level='REPEATABLE READ', autocommit=False)
        with connection.cursor() as q:
            q.execute("SELECT current_setting('transaction_read_only'),current_database(),current_setting('server_version'),inet_server_addr()::text")
            readonly, database, version, address = q.fetchone()
            if readonly != 'on': raise ValueError('Read-only transaction required')
            environment = dict(app_environment=os.environ['APP_ENVIRONMENT'], storage_mode=os.environ['STORAGE_MODE'],
                               render_service_id=os.environ['RENDER_SERVICE_ID'], deployment_id=os.getenv('NOK_DEPLOYMENT_ID'),
                               git_commit=os.getenv('RENDER_GIT_COMMIT'), database=database, server_version=version,
                               server_identity_sha256=digest(dict(database=database, address=address)), transaction_read_only=readonly)
            extensions.register_type(extensions.BYTES, q)
            raw = raw_document(q, 'simulation_restarts/'+PERIOD+'/bundle.json')
            if raw is None or len(raw) > 1024**2: raise ValueError('Expected bounded prepared account bundle')
            bundle = json.loads(raw)
            accounts = verified_drafts(bundle)
            routes = {}
            for family in CAPITALS:
                route = raw_document(q, 'simulation_restarts/routes/'+family+'.json')
                routes[family] = route is not None
            if any(routes.values()): raise ValueError('A production route exists; do not claim all accounts inactive')
            receipts = file_receipts(bundle)
            settings = {}
            q.execute('SELECT CASE WHEN octet_length(rules)<=1048576 THEN rules ELSE NULL END FROM public.trading_rules WHERE id=1')
            row = q.fetchone()
            if row and row[0] is None: raise ValueError('Trading rules exceed bounded budget')
            settings['paper_trading_rules'] = dict(source='PostgreSQL:trading_rules:id=1', stored=bool(row),
                cost_fields=cost_fields(json.loads(row[0])) if row else {})
            local_rules = ROOT/'trading_rules.json'
            if local_rules.exists():
                settings['paper_legacy_rules'] = dict(source='LEGACY_ROOT_FILE:trading_rules.json',
                    cost_fields=cost_fields(metadata(local_rules)))
            else: settings['paper_legacy_rules'] = dict(stored=False)
            settings['paper_kv_rules'] = cost_config(q, 'settings/trading_rules.json', None, {'commission_pct','slippage_pct','fee_pct','transaction_cost_pct'})
            settings['autonomy_parameters'] = cost_config(q, 'autonomous_portfolio/parameters.json', 'autonomous_portfolio/parameters.json', {'transaction_cost_pct','fee_pct','commission_pct','fx_bps'})
            settings['autonomy_portfolio'] = cost_config(q, 'autonomous_portfolio/portfolio.json', 'autonomous_portfolio/portfolio.json', {'transaction_cost_pct','fee_pct','commission_pct','fx_bps'})
            settings['super_portfolio'] = cost_config(q, 'super_portfolio/state.json', 'super_portfolio/state.json', {'config','turnover_costs','last_portfolio_transaction_cost'})
            journal = journal_costs(q, 'super_portfolio/transactions.jsonl')
            # Bounded individual Paper trade records: no history changes or inferred zero fees.
            q.execute('SELECT count(*),count(*) FILTER (WHERE evidence_metadata IS NOT NULL) FROM public.paper_trades')
            paper_counts = q.fetchone()
            paper_journal = paper_costs(q)
            autonomy_journal = autonomy_costs(q)
            q.execute("SELECT name FROM public.app_kv_store WHERE name LIKE 'superfund/%' ORDER BY name LIMIT 50")
            fund_keys = [v[0].decode('utf-8') for v in q.fetchall()]
            result = dict(status='READ_ONLY_COST_AND_DRAFT_EVIDENCE_COMPLETE', at=datetime.now(timezone.utc).isoformat(),
                environment=environment, source_hashes_matched=matched, period_id=PERIOD,
                all_three_drafts_verified=True, accounts=accounts, selected_routes_present=routes,
                archive_restore=receipts, stored_settings=settings, super_portfolio_journal=journal,
                paper_journal=paper_journal, autonomy_journal=autonomy_journal,
                paper_trade_metadata=dict(rows=paper_counts[0], with_evidence_metadata=paper_counts[1],
                                         note='Presence is not proof of any fee; no absent fee is converted to zero'),
                superfund=dict(namespace_keys_observed=len(fund_keys), examined_for_migration=False, changed=False),
                production_actions_performed=False, accounts_activated=False, histories_changed=False,
                learning_changed=False, approval_B_ready=False)
            result['evidence_sha256'] = digest(result)
            return result
    finally:
        try: connection.rollback()
        finally: connection.close()


if __name__ == '__main__':
    try: print(json.dumps(main(), ensure_ascii=False, indent=2, allow_nan=False))
    except Exception as error:
        print(json.dumps(dict(status='READ_ONLY_COST_AUDIT_STOPPED', error_type=type(error).__name__,
                              sqlstate=getattr(error, 'pgcode', None),
                              reason=str(error) if type(error) is ValueError else 'Private diagnostic details withheld',
                              accounts_activated=False, production_actions_performed=False)))
        raise SystemExit(1)
