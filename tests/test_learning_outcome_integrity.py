from copy import deepcopy
from datetime import datetime, timezone

from test_revision_trade_postgres import pg


def observation(*, broken=False):
    return {'observation_id': 'source-A', 'ticker': 'A', 'group': 'STRICT',
            'status': 'ACTIVE', 'entry_price': 100., 'entry_market_date': '2026-09-01',
            'entry_at': '2026-09-01T12:00:00+00:00', 'benchmark_entry_price': 100.,
            'benchmark_ticker': '^GSPC', 'decision_snapshot': {'original': True},
            'daily_marks': [{'market_date': '2026-09-08', 'price': 95}],
            'horizon_measurements': {
                '1': {'horizon_days': 1, 'market_date': '2026-09-02', 'price': 110.,
                      'return_pct': 10., 'benchmark_price': 100., 'benchmark_return_pct': 0.,
                      'excess_return_pct': 10., 'maximum_gain_pct': 10., 'maximum_drawdown_pct': 10.},
                '5': {'horizon_days': 5, 'market_date': '2026-09-08', 'price': 95.,
                      'return_pct': -5., 'benchmark_price': 100., 'benchmark_return_pct': 0.,
                      'excess_return_pct': -5., 'maximum_gain_pct': 2. if broken else 10.,
                      'maximum_drawdown_pct': -5.}}}


def test_weekly_report_excludes_internally_inconsistent_outcome_sets():
    from learning_observation_engine import build_weekly_analysis
    report = build_weekly_analysis([observation(broken=True)])
    assert report['horizons'][0]['return']['count'] == 0
    assert report['data_quality']['excluded_observations'] == 1


def test_negative_returns_are_preserved_when_consistent():
    from services.learning_outcome_integrity import issues
    assert issues(observation()) == []


def test_stored_benchmark_denominator_must_reproduce_the_return():
    from services.learning_outcome_integrity import issues
    row = observation()
    row['horizon_measurements']['1']['benchmark_return_pct'] = 1.
    assert 'BENCHMARK_ARITHMETIC_MISMATCH' in issues(row)


def test_daily_and_horizon_returns_on_the_same_date_must_agree():
    from services.learning_outcome_integrity import issues
    row = observation()
    row['daily_marks'] = [{'market_date':'2026-09-02','return_pct':9.}]
    assert 'DAILY_HORIZON_ENDPOINT_MISMATCH' in issues(row)


def test_unfinished_us_session_is_not_a_daily_outcome(monkeypatch):
    import learning_observation_engine as engine
    row = observation(); row['horizon_measurements'] = {}; row['daily_marks'] = []
    saved = []
    monkeypatch.setattr(engine, 'load_observations', lambda: [row])
    monkeypatch.setattr(engine, 'save_observations', lambda rows: saved.extend(deepcopy(rows)))
    monkeypatch.setattr(engine, 'load_engine_state', lambda: {})
    monkeypatch.setattr(engine, 'write_json', lambda *a: None)
    monkeypatch.setattr(engine, '_audit', lambda *a, **k: None)
    loader = lambda *a: {'A':[{'date':'2026-09-02','close':110.}],
                         '^GSPC':[{'date':'2026-08-31','close':100.},{'date':'2026-09-02','close':101.}]}
    engine.evaluate_observations(loader, now=datetime(2026,9,2,15,tzinfo=timezone.utc))
    assert saved[0]['horizon_measurements'] == {}
    assert saved[0]['daily_marks'] == []


def test_preview_is_read_only_and_apply_backs_up_before_removing_outcomes(pg):
    from services.learning_outcome_integrity import SOURCE, apply_manifest, digest, restore, unpack
    bad = observation(broken=True)
    good = {**observation(), 'observation_id': 'source-B'}
    pg.write_json(SOURCE, [bad, good])
    pg.write_json('strategy_history/optimization_progress.json', {'processed': 1009})
    manifest = {'source-A': digest(bad)}
    preview = apply_manifest(storage=pg, manifest=manifest, apply=False)
    assert preview['state'] == 'DRY_RUN' and pg.read_json(SOURCE) == [bad, good]
    result = apply_manifest(storage=pg, manifest=manifest, apply=True)
    assert result['state'] == 'COMPLETED' and result['isolated'] == 1
    saved = pg.read_json(SOURCE)
    assert saved[0]['status'] == 'QUARANTINED'
    assert saved[0]['decision_snapshot'] == bad['decision_snapshot']
    assert saved[0]['horizon_measurements'] == {} and saved[0]['daily_marks'] == []
    assert saved[1] == good
    backup = pg.read_json(result['backup_key'])
    assert unpack(backup) == [bad]
    assert apply_manifest(storage=pg, manifest=manifest, apply=True)['state'] == 'ALREADY_APPLIED'
    assert pg.read_json('strategy_history/optimization_progress.json') == {'processed': 1009}
    restore(storage=pg, backup_key=result['backup_key'], apply=True)
    assert pg.read_json(SOURCE) == [bad, good]


def test_stale_manifest_does_not_delete_changed_source(pg):
    from services.learning_outcome_integrity import SOURCE, apply_manifest, digest
    bad = observation(broken=True)
    manifest = {'source-A': digest(bad)}
    changed = deepcopy(bad); changed['entry_price'] = 101.
    pg.write_json(SOURCE, [changed])
    result = apply_manifest(storage=pg, manifest=manifest, apply=True)
    assert result['state'] == 'SOURCE_CHANGED'
    assert pg.read_json(SOURCE) == [changed]


def test_stale_observation_writer_cannot_resurrect_quarantined_results(pg, monkeypatch):
    import learning_observation_engine as engine
    import services.storage_service as stores
    import durable_runtime
    from services.learning_outcome_integrity import SOURCE, apply_manifest, digest
    stale = observation(broken=True)
    pg.write_json(SOURCE, [stale])
    apply_manifest(storage=pg, manifest={'source-A': digest(stale)}, apply=True)
    isolated = pg.read_json(SOURCE)
    monkeypatch.setattr(stores, 'get_storage_service', lambda: pg)
    monkeypatch.setattr(durable_runtime, 'get_storage_service', lambda: pg)
    engine.save_observations([stale])
    assert pg.read_json(SOURCE) == isolated


def test_backup_failure_rolls_back_all_changes(pg):
    import pytest
    from services.learning_outcome_integrity import SOURCE, apply_manifest, digest
    bad = observation(broken=True)
    pg.write_json(SOURCE, [bad])
    conn = pg._conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute("""CREATE FUNCTION reject_backup() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN IF NEW.name LIKE 'controlled_learning/quarantine/%' THEN
                RAISE EXCEPTION 'injected backup failure'; END IF; RETURN NEW; END $$""")
            cur.execute('CREATE TRIGGER fail_backup BEFORE INSERT ON app_kv_store FOR EACH ROW EXECUTE FUNCTION reject_backup()')
    conn.close()
    with pytest.raises(Exception, match='injected backup failure'):
        apply_manifest(storage=pg, manifest={'source-A': digest(bad)}, apply=True)
    assert pg.read_json(SOURCE) == [bad]


def test_restore_refuses_to_overwrite_corrected_decision_metadata(pg):
    import pytest
    from services.learning_outcome_integrity import SOURCE, apply_manifest, digest, restore
    bad = observation(broken=True)
    pg.write_json(SOURCE, [bad])
    result = apply_manifest(storage=pg, manifest={'source-A': digest(bad)}, apply=True)
    modified = pg.read_json(SOURCE)
    modified[0]['decision_snapshot']['correction'] = 'preserve me'
    pg.write_json(SOURCE, modified)
    with pytest.raises(ValueError, match='changed observation'):
        restore(storage=pg, backup_key=result['backup_key'], apply=True)
    assert pg.read_json(SOURCE) == modified


def test_restored_data_can_be_requarantined_and_restored_again(pg):
    from services.learning_outcome_integrity import SOURCE, apply_manifest, digest, restore
    original = observation(broken=True)
    pg.write_json(SOURCE, [original])
    manifest = {'source-A': digest(original)}
    first = apply_manifest(storage=pg, manifest=manifest, apply=True,
                           now=datetime(2026,11,9,tzinfo=timezone.utc))
    restore(storage=pg, backup_key=first['backup_key'], apply=True)
    second = apply_manifest(storage=pg, manifest=manifest, apply=True,
                            now=datetime(2026,11,10,tzinfo=timezone.utc))
    restore(storage=pg, backup_key=second['backup_key'], apply=True)
    assert pg.read_json(SOURCE) == [original]


def test_fresh_download_cannot_attach_a_contradictory_longer_horizon(monkeypatch):
    import learning_observation_engine as engine
    row = observation(); row['horizon_measurements'].pop('5')
    saved = []
    monkeypatch.setattr(engine, 'load_observations', lambda: [row])
    monkeypatch.setattr(engine, 'save_observations', lambda rows: saved.extend(deepcopy(rows)))
    monkeypatch.setattr(engine, 'load_engine_state', lambda: {})
    monkeypatch.setattr(engine, 'write_json', lambda *a: None)
    monkeypatch.setattr(engine, '_audit', lambda *a, **k: None)
    stock = [{'date': '2026-09-01', 'close': 100.}] + [
        {'date': d, 'close': p} for d,p in [('2026-09-02',102.),('2026-09-03',101.),
        ('2026-09-04',100.),('2026-09-07',99.),('2026-09-08',95.)]]
    bench = [{'date': '2026-08-31', 'close': 100.}] + [dict(r, close=100.) for r in stock]
    engine.evaluate_observations(lambda *a: {'A':stock, '^GSPC':bench}, now=datetime(2026,9,9,tzinfo=timezone.utc))
    assert saved[0]['horizon_measurements'] == row['horizon_measurements']
    assert '5' not in saved[0]['horizon_measurements']
    assert saved[0]['source_health']['status'] == 'OUTCOME_WINDOW_INCONSISTENT'
