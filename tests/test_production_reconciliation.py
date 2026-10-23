"""Safety contracts with synthetic inputs, never a substitute for production."""
from copy import deepcopy
import json
from pathlib import Path
import zipfile
import pytest
from test_revision_trade_postgres import pg
from services.production_reconciliation import assess,FAMILIES
from scripts.f3_readonly_inventory import export_postgres,private_destination,inspect_archive,REPO


@pytest.mark.parametrize('family',FAMILIES)
def test_missing_production_source_stops_trial(family):
    result=assess(family)
    assert result['status']=='STOPPED'
    assert result['production_data_checked'] is False
    assert result['trial_performed'] is False


def test_generated_fixtures_are_not_production_evidence():
    for family in FAMILIES:
        result=assess(family,{'source_kind':'SYNTHETIC_TEST','state':{},'source_sha256':'fixture'})
        assert result['production_data_checked'] is False
        assert result['trial_performed'] is False


def test_model_weights_do_not_become_documented_share_opening():
    # This tests handling of DECLARED provenance. It is not a real source claim.
    source={'source_kind':'SUPPLIED_MODEL_DIAGNOSTIC_ARCHIVE','source_sha256':'TEST ONLY source declaration','as_of':'2026-10-23T00:00:00Z',
        'state':{'cash':1000,'positions':{'TEST':{'quantity':300,'quantity_unit':'MODEL_PRICE_RATIO_UNITS'}}}}
    before=deepcopy(source)
    result=assess('super_portfolio',source)
    assert result['status']=='STOPPED'
    assert 'MISSING_DOCUMENTED_OPENING_BALANCE' in result['issues']
    assert result['trial_performed'] is False
    assert source==before


def test_production_export_cannot_be_written_inside_checkout(tmp_path):
    with pytest.raises(ValueError):private_destination(REPO/'private-evidence.json')
    target=tmp_path/'evidence.json';target.write_text('original')
    with pytest.raises(ValueError):private_destination(target)
    assert target.read_text()=='original'


def test_archive_inventory_never_extracts_paths(tmp_path):
    path=tmp_path/'diagnostic.zip'
    with zipfile.ZipFile(path,'w') as z:z.writestr('../portfolio.json','{}')
    with pytest.raises(ValueError):inspect_archive(path)
    assert not (tmp_path.parent/'portfolio.json').exists()


def test_pg_extractor_is_repeatable_read_readonly_and_selects_no_auth(pg):
    pg.write_json('autonomous_portfolio/portfolio.json',{'cash':1000,'source':'TEST ONLY'})
    pg.write_json('auth/users.json',{'secret':'TEST ONLY must not export'})
    connection=pg._conn()
    try:
        exported=export_postgres(connection)
        assert exported['source_kind']=='READ_ONLY_POSTGRES_EXPORT'
        assert set(exported['documents'])=={'autonomous_portfolio/portfolio.json'}
        assert exported['documents']['autonomous_portfolio/portfolio.json']['payload']['cash']==1000
        with connection.cursor() as cur:
            cur.execute('SHOW transaction_read_only');assert cur.fetchone()[0]=='on'
            cur.execute('SHOW transaction_isolation');assert cur.fetchone()[0]=='repeatable read'
            with pytest.raises(Exception):cur.execute("INSERT INTO app_kv_store(name,payload) VALUES('must-not-write','{}')")
        connection.rollback()
    finally:connection.close()
    assert pg.read_json('must-not-write') is None
    assert pg.read_json('auth/users.json')['secret'].startswith('TEST ONLY')


def test_pg_evidence_budget_stops_instead_of_silently_truncating(pg):
    pg.write_json('autonomous_portfolio/portfolio.json',{'cash':1000})
    pg.write_json('super_portfolio/state.json',{'cash':1000})
    connection=pg._conn()
    try:
        with pytest.raises(ValueError,match='row budget'):export_postgres(connection,max_rows=1)
    finally:connection.close()


def test_undated_source_stops_instead_of_raising_or_verifying():
    evidence={'source_kind':'READ_ONLY_POSTGRES_EXPORT','source_sha256':'TEST ONLY declaration','state':{}}
    for family in FAMILIES:
        result=assess(family,evidence)
        assert result['status']=='STOPPED'
        assert 'MISSING_OR_INVALID_SOURCE_TIME' in result['issues']


@pytest.mark.parametrize('bad_amount',[float('nan'),float('inf'),True,-1])
def test_invalid_documented_closing_never_certifies_trial(bad_amount):
    from test_portfolio_accounting import opening,AT
    evidence={'source_kind':'SUPPLIED_MODEL_DIAGNOSTIC_ARCHIVE','source_sha256':'TEST ONLY declaration',
        'as_of':AT,'state':{},'opening_document':opening(),'documented_fills':[],
        'history_complete':True,'documented_closing':{'source_ref':'TEST ONLY closing',
            'cash_nok':bad_amount,'positions':{},'nav_nok':100000,'valuation_marks':{}}}
    result=assess('paper',evidence)
    assert result['status']=='STOPPED'
    assert result['trial_performed'] is False
