"""One small immutable census per report, independent of outcome sampling quotas."""
from copy import deepcopy
import hashlib
import json
import math

PREFIX = 'controlled_learning/signal_reports/'
MAX_SIGNALS = 500
MAX_BYTES = 256 * 1024
GROUPS = {'KJØPSKANDIDAT':'STRICT','MODERAT_KJØPSANBEFALING':'MODERATE'}


def reference(candidate):
    """Keep documented reference fields; these are never executable fill evidence."""
    ticker = str(candidate.get('ticker') or '').upper()
    result = {}
    node = candidate
    for _ in range(10):
        if not isinstance(node, dict):
            break
        identity = str(node.get('ticker') or node.get('symbol') or ticker).upper()
        if identity != ticker:
            raise ValueError('Signal reference instrument identity mismatch')
        for field in ('current_price','price','last_price','regularMarketPrice','close'):
            value = node.get(field)
            if value is not None and 'reference_price' not in result:
                try:
                    price = float(value)
                    if not isinstance(value,bool) and math.isfinite(price) and price>0:
                        result['reference_price'] = price
                except (ValueError,TypeError):
                    pass
        for source,target in (('currency','reference_currency'),('latest_trade_timestamp','reference_price_at'),
                              ('data_source','reference_source')):
            if source=='currency' and node.get(source) and result.get(target) and str(node[source])!=result[target]:
                raise ValueError('Conflicting signal reference currencies')
            if node.get(source) and target not in result:
                result[target] = str(node[source])
        node = node.get('raw')
    return result


def capture(run, *, commit=False, storage=None):
    report_id = str(run.get('run_id') or run.get('report_id') or '').strip()
    if not report_id:
        raise ValueError('Missing signal report identity')
    available = run.get('signal_available_at')
    if available:
        from services.learning_position_outcomes import stamp
        if stamp(available)<stamp(run['created_at']):
            raise ValueError('Signal availability precedes report creation')
    elif commit:
        raise ValueError('Missing signal availability after final release gate')
    signals = {}
    for candidate in run.get('candidates') or []:
        group = GROUPS.get(str(candidate.get('autonomy_outcome_code') or '').upper())
        if not group:
            continue
        ticker = str(candidate.get('ticker') or '').strip().upper()
        if not ticker:
            raise ValueError('Buy recommendation has no instrument identity')
        try:
            fields = reference(candidate)
        except ValueError:
            fields = {'reference_status':'UNVERIFIED_IDENTITY_OR_CURRENCY'}
        signal = {'ticker':ticker,'group':group,'market':str(candidate.get('market') or ''),
                  'candidate_snapshot_id':candidate.get('candidate_snapshot_id'),
                  'signal_at':available,'is_executed_trade':False,
                  **fields}
        if ticker in signals and signals[ticker] != signal:
            raise ValueError('Conflicting signal identity within report')
        signals[ticker] = signal
    if len(signals)>MAX_SIGNALS:
        raise ValueError('Signal census exceeds explicit report budget; no truncation permitted')
    payload = {'schema':1,'source_report_id':report_id,'source_created_at':str(run.get('created_at') or ''),
               'scope':'ALL_BUY_RECOMMENDATION_OCCURRENCES_NOT_TRADES',
               'signals':[signals[k] for k in sorted(signals)]}
    encoded = json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if len(encoded)>MAX_BYTES:
        raise ValueError('Signal census exceeds byte budget; no truncation permitted')
    checksum = hashlib.sha256(encoded).hexdigest()
    key = PREFIX+hashlib.sha256(report_id.encode()).hexdigest()+'.json'
    result = {'state':'PLANNED','key':key,'sha256':checksum,'signal_count':len(signals),
              'strict_count':sum(r['group']=='STRICT' for r in signals.values()),
              'moderate_count':sum(r['group']=='MODERATE' for r in signals.values()),
              'scope':payload['scope'],'sampling_is_complete_census':False}
    if commit:
        if storage is None:
            from services.storage_service import get_storage_service
            storage = get_storage_service()
        saved = storage.write_json_immutable(key,deepcopy(payload))
        if saved != payload:
            raise ValueError('Signal report identity conflict; original receipt preserved')
        result['state'] = 'RECORDED'
    return result
