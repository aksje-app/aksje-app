"""Shared bounded reads, approved cost rules and market evidence barriers.
No activation CLI, reset, account creation or scheduler action.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

PERIOD = 'nok-20261025T012118Z'
CIPHER_SHA = '5e98f9c9d7f43ed477099f17f459ea7680ec61fb04d49f9f504191694b4ce158'
ARCHIVE = '20261024T232608Z-4df389aad81c4186949d7133e32c0649'
REVIEW_SHA = '3118134d55f84c0935ab4d22704117db160bd730f46636ab5488547290f1e90a'
SERVICE = 'srv-d7obt5e47okc739susgg'
DEPLOYMENT = 'aksje-app-production-nok-v1'
FAMILIES = ('paper', 'autonomy', 'super_portfolio')
APPROVAL = 'USER_APPROVED_SIMULATION_MODEL:SHA256:d36bd7ed61f898c93403910a50b32971595504581f73baf37a190faee4b0a131:section_3'


def load(path):
    path = Path(path)
    if path.stat().st_size > 32*1024**2:
        raise ValueError('Metadata file exceeds the bounded read limit')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def save(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def file_sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            result.update(block)
    return result.hexdigest()


class ReadOnlyStorage:
    """Real PostgreSQL reads. No schema initialization, fallback or write API."""
    allow_local_fallback = False
    def using_postgres(self):
        return True
    def _conn(self):
        import psycopg2
        from psycopg2.extensions import parse_dsn
        existing = parse_dsn(os.environ['DATABASE_URL']).get('options', os.getenv('PGOPTIONS',''))
        conn = psycopg2.connect(os.environ['DATABASE_URL'], connect_timeout=10,
            options=existing+' -c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=3000')
        conn.set_session(readonly=True, isolation_level='REPEATABLE READ')
        return conn
    def read_json(self, name, default=None):
        conn = self._conn()
        try:
            with conn.cursor() as cursor:
                cursor.execute('SELECT octet_length(payload) FROM app_kv_store WHERE name=%s', (name,))
                row = cursor.fetchone()
                if row is None:
                    return deepcopy(default)
                if row[0] is None or row[0] > 32*1024**2:
                    raise ValueError('Stored document exceeds bounded read limit: '+name)
                cursor.execute('SELECT payload FROM app_kv_store WHERE name=%s', (name,))
                return json.loads(cursor.fetchone()[0])
        finally:
            conn.rollback()
            conn.close()


def policies():
    result = {}
    for family, bps in zip(FAMILIES, (5, 20, 10)):
        ref = APPROVAL+':'+family
        policy = dict(schema='NOK_COST_POLICY_V2', source_ref=ref, components={
            'model_transaction_cost_nok': dict(rate_bps=bps, source_ref=ref+':base_model_cost'),
            'fx_cost_nok': dict(rate_bps=25, source_ref=ref+':additional_fx_on_actual_conversion')})
        if family == 'paper':
            policy['slippage'] = dict(rate_bps=10, source_ref=ref+':execution_price_only')
        result[family] = policy
    return result

