"""Normal maintenance may migrate storage, never execute financial callbacks."""
from test_revision_trade_postgres import pg


def test_ordinary_maintenance_encodes_only_selected_period_once(pg,monkeypatch):
    from services.restart_storage_maintenance import run_restart_storage_maintenance
    flag='RESTART_BUNDLE_COMPRESSION_ENABLED';key='simulation_restarts/selected/bundle.json'
    monkeypatch.delenv(flag,raising=False)
    value={'text':'x'*1100000,'financial_events':['untouched']};pg.write_json(key,value)
    pg.write_json('simulation_restarts/routes/autonomy.json',{'family':'autonomy','period_id':'selected'})
    assert run_restart_storage_maintenance(storage=pg)['status']=='NOT_ENABLED'
    monkeypatch.setenv(flag,'1');result=run_restart_storage_maintenance(storage=pg)
    assert result['status']=='COMPLETED' and result['records'][0]['state']=='ENCODED'
    assert result['financial_state_changed'] is False and pg.read_json(key)==value
    revision=pg.json_row_versions([key]);result=run_restart_storage_maintenance(storage=pg)
    assert result['records'][0]['state']=='ALREADY_ENCODED'
    assert pg.json_row_versions([key])==revision


def test_maintenance_bounds_work_to_one_new_bundle_per_run(pg,monkeypatch):
    from services.restart_storage_maintenance import run_restart_storage_maintenance
    monkeypatch.delenv('RESTART_BUNDLE_COMPRESSION_ENABLED',raising=False)
    for family,period in [('paper','one'),('autonomy','two')]:
        pg.write_json(f'simulation_restarts/{period}/bundle.json',{'text':'x'*1100000})
        pg.write_json(f'simulation_restarts/routes/{family}.json',{'family':family,'period_id':period})
    monkeypatch.setenv('RESTART_BUNDLE_COMPRESSION_ENABLED','1')
    for _ in range(2):
        result=run_restart_storage_maintenance(storage=pg)
        assert sum(r['state']=='ENCODED' for r in result['records'])==1
    assert all(r['state']=='ALREADY_ENCODED' for r in run_restart_storage_maintenance(storage=pg)['records'])
