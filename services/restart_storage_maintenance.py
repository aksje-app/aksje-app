"""Bounded storage-only migration within the existing scheduler invocation."""
import re
from services.restart_payload_codec import enabled


def run_restart_storage_maintenance(*,storage=None):
    result={'status':'NOT_ENABLED','records':[],'storage_encoding_changed':False,'financial_state_changed':False}
    if not enabled():return result
    if storage is None:
        from services.storage_service import get_storage_service
        storage=get_storage_service()
    if not storage.using_postgres() or storage.allow_local_fallback:
        return {**result,'status':'SKIPPED','reason':'AUTHORITATIVE_POSTGRES_REQUIRED'}
    periods=set()
    for family in ('paper','autonomy','super_portfolio'):
        route=storage.read_json('simulation_restarts/routes/'+family+'.json',None)
        if not route:continue
        period=route.get('period_id')
        if route.get('family')!=family or not isinstance(period,str) or not re.fullmatch('[A-Za-z0-9_-]{1,96}',period):
            raise ValueError('Invalid explicit restart route for encoding maintenance')
        periods.add(period)
    result['status']='COMPLETED';migrated=0
    for period in sorted(periods):
        key='simulation_restarts/'+period+'/bundle.json'
        if migrated:
            result['records'].append({'key':key,'state':'DEFERRED_ONE_BUNDLE_PER_RUN'});continue
        record=storage.ensure_restart_encoding(key)
        result['records'].append({'key':key,**record})
        if record['state']=='MISSING':result['status']='FAILED'
        if record['state']=='ENCODED':migrated+=1;result['storage_encoding_changed']=True
    return result
