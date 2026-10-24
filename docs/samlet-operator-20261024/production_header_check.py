"""Read-only production capacity headers. No model values, fingerprints or archive.

TEXT octet_length and pg_column_size read TOAST length/storage metadata. Never
row_to_json, to_json, COPY, pg_dump, DDL or model payload retrieval. Does not lift
the suspended production archive gate or grant any account activation.
"""
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone

NOMINAL_SOURCE_MEMORY_BYTES = 1_000_000_000  # conservative floor of reported Basic-1GB
PROPOSED_TEXT_ROW_LIMIT_BYTES = 160 * 1024**2
SERVER_RESERVE_BYTES = 128 * 1024**2


def collect_headers(connection):
    from psycopg2 import sql
    connection.set_session(readonly=True, isolation_level='REPEATABLE READ', autocommit=False)
    report = {'tables': [], 'unsupported_variable_columns': []}
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL statement_timeout='30s'")
        cursor.execute("SET LOCAL lock_timeout='3s'")
        cursor.execute("SET LOCAL max_parallel_workers_per_gather=0")
        cursor.execute("SET LOCAL jit=off")
        cursor.execute("SET LOCAL work_mem='1MB'")
        cursor.execute("SELECT current_setting('transaction_read_only'),current_setting('server_version_num')::int,current_setting('server_encoding'),pg_catalog.pg_size_bytes(current_setting('shared_buffers')),extract(epoch from (clock_timestamp()-pg_postmaster_start_time()))::bigint")
        readonly, version, encoding, shared, uptime = cursor.fetchone()
        if readonly != 'on':
            raise ValueError('READ ONLY source transaction required')
        report.update(server_version_num=version, server_encoding=encoding, shared_buffers_bytes=shared,
                      server_uptime_seconds=uptime, transaction_read_only=True)
        cursor.execute("SELECT count(*) FROM pg_catalog.pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND state IN ('active','idle in transaction','idle in transaction (aborted)')")
        report['other_active_or_open_transactions'] = cursor.fetchone()[0]
        cursor.execute("SELECT schemaname,tablename FROM pg_catalog.pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2")
        tables = cursor.fetchall()
    biggest = 0
    for index, (schema, table) in enumerate(tables, 1):
        with connection.cursor() as cursor:
            cursor.execute('''SELECT a.attname,a.atttypid,a.attlen,pg_catalog.format_type(a.atttypid,a.atttypmod)
                FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
                JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=%s AND c.relname=%s AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum''', (schema, table))
            columns = cursor.fetchall()
            if not columns:
                raise ValueError('Declared source has no visible columns; no omission permitted')
            expressions = []
            for name, oid, length, typename in columns:
                function = 'octet_length' if oid == 25 else 'pg_column_size'
                expressions.append(sql.SQL('max(pg_catalog.{}({}))').format(sql.Identifier(function), sql.Identifier(name)))
            cursor.execute(sql.SQL('SELECT {} FROM {}').format(sql.SQL(',').join(expressions), sql.Identifier(schema, table)))
            maxima = cursor.fetchone()
            for (name,oid,length,typename),maximum in zip(columns,maxima,strict=True):
                if oid != 25 and length < 0 and maximum is not None:
                    report['unsupported_variable_columns'].append(dict(table=schema+'.'+table,column=name,type=typename))
            lengths = {name: value for (name, oid, _, _), value in zip(columns, maxima, strict=True) if oid == 25}
            upper = sum(value or 0 for value in lengths.values())
            upper += sum(max(64, length*8) for _, oid, length, _ in columns if oid != 25 and length > 0)
            biggest = max(biggest, upper)
            report['tables'].append(dict(table_index=index, table=schema+'.'+table,
                                         max_text_column_octets=lengths, native_row_upper_bound_bytes=upper))
    # Conservative screening estimate, not a measured PostgreSQL RSS guarantee.
    estimate = shared + SERVER_RESERVE_BYTES + 3 * biggest
    report.update(max_native_row_upper_bound_bytes=biggest,
                  screening_peak_estimate_bytes=estimate,
                  nominal_memory_floor_bytes=NOMINAL_SOURCE_MEMORY_BYTES,
                  reserve_bytes=SERVER_RESERVE_BYTES,
                  text_row_limit_bytes=PROPOSED_TEXT_ROW_LIMIT_BYTES,
                  screening_only_not_measured_peak=True)
    reasons=[]
    if not 180000 <= version < 190000:reasons.append('major_version_not_18')
    if encoding != 'UTF8':reasons.append('source_encoding_not_UTF8')
    if report['unsupported_variable_columns']:reasons.append('variable_column_type_requires_review')
    if biggest > PROPOSED_TEXT_ROW_LIMIT_BYTES:reasons.append('row_exceeds_proposed_native_limit')
    if estimate > NOMINAL_SOURCE_MEMORY_BYTES * 95 // 100:reasons.append('estimated_memory_budget_exceeded')
    report['screening_failure_reasons']=reasons
    report['capacity_screen_passed']=not reasons
    return report


def main(work):
    import psycopg2
    work = Path(work)
    if work.parent != Path('/tmp') or not re.fullmatch(r'nok-job-[0-9]{8}T[0-9]{6}Z', work.name):
        raise ValueError('Exact existing private job required')
    if not work.is_dir() or work.is_symlink() or work.stat().st_mode & 0o077 or work.stat().st_uid != os.geteuid():
        raise ValueError('Private operator-owned job required')
    plan = json.loads((work/'plan.json').read_text(encoding='utf-8-sig'))
    if plan.get('job_id') != work.name or plan.get('activation_authorized') is not False or plan.get('approval_A_already_granted') is not True:
        raise ValueError('Existing approval A, matching job and no activation required')
    if os.getenv('APP_ENVIRONMENT') != 'production' or os.getenv('STORAGE_MODE') != 'postgres':
        raise ValueError('Actual production PostgreSQL configuration required; no test fallback')
    if os.getenv('ALLOW_LOCAL_STORAGE_FALLBACK', '').lower() not in {'false','0','no','off'}:
        raise ValueError('Local storage fallback must remain disabled')
    config = json.loads((work/'config-unconfirmed.json').read_text(encoding='utf-8-sig'))
    databases = config['database_environment_variables']
    if not databases:
        raise ValueError('No documented source database')
    configured={v for v in ('DATABASE_URL','AUTH_DATABASE_URL','POSTGRES_URL','RENDER_DATABASE_URL') if os.getenv(v)}
    if not configured.issubset(set(databases.values())):
        raise ValueError('A current database source is absent from the reviewed inventory; no omission permitted')
    report = dict(status='SOURCE_HEADER_CAPACITY_CHECK_COMPLETE', at=datetime.now(timezone.utc).isoformat(),
                  databases={}, archive_attempted=False, full_model_scan_attempted=False,
                  accounts_activated=False, portfolio_rows_modified=False, production_ready=False,
                  production_archive_remains_suspended=True,
                  web_background_workers_enabled=os.getenv('ENABLE_WEB_BACKGROUND_SERVICES','false').lower() in {'true','1','yes','on'})
    for alias, variable in databases.items():
        if not os.getenv(variable):
            raise ValueError('Documented source environment configuration missing')
        connection = psycopg2.connect(os.environ[variable], connect_timeout=15,
            application_name='aksje_header_capacity_only',
            options='-c default_transaction_read_only=on -c client_encoding=UTF8 -c statement_timeout=30000')
        try:
            report['databases'][alias] = collect_headers(connection)
        finally:
            try:
                connection.rollback()
            except Exception:
                pass
            connection.close()
    print(json.dumps(report, ensure_ascii=True, indent=2, allow_nan=False))


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('One existing job path required')
        main(sys.argv[1])
    except Exception as error:
        # PostgreSQL errors can include private connection details. Return only
        # type/state for dependency errors, never DSNs, credentials or row values.
        print(json.dumps(dict(status='SOURCE_HEADER_CHECK_STOPPED', error_type=type(error).__name__,
            reason=str(error) if type(error) is ValueError else 'Read-only capacity check failed; no archive or account action',
            sqlstate=getattr(error,'pgcode',None), accounts_activated=False)))
        raise SystemExit(1)
