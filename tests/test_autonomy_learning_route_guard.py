"""Legacy migration prohibitions must never decode the selected NOK journal."""
from copy import deepcopy
import pytest
from services import production_restart as control
import autonomous_portfolio as ap


@pytest.mark.parametrize('pointer',[
    {'family':'autonomy','period_id':'selected','deployment_id':'test'},
    {}, {'status':'PAUSED'}, {'deployment_id':'FOREIGN'},
])
def test_existing_route_blocks_legacy_migration_without_loading_journal(pointer,monkeypatch):
    monkeypatch.setenv('APP_ENVIRONMENT','test')
    monkeypatch.setenv('NOK_DEPLOYMENT_ID','test')
    reads=[]
    class Storage:
        def read_json(self,name,default=None):
            reads.append(name)
            assert name==control.route_key('autonomy'), 'Learning must not deserialize the large financial journal'
            return deepcopy(pointer)
    monkeypatch.setattr(control,'get_storage_service',lambda:Storage())
    monkeypatch.setattr(ap,'_read',lambda *a,**kw:pytest.fail('A published NOK route prohibits legacy migration'))
    monkeypatch.setattr(ap,'_write',lambda *a,**kw:pytest.fail('No legacy financial writes'))
    assert ap.ensure_portfolio_separation()=={'positions_moved':0,'cash_restored':0}
    assert reads==[control.route_key('autonomy')]


def test_unreadable_route_never_falls_back_to_legacy_migration(monkeypatch):
    monkeypatch.setenv('APP_ENVIRONMENT','test')
    class Storage:
        def read_json(self,*a,**kw):raise ConnectionError('unavailable')
    monkeypatch.setattr(control,'get_storage_service',lambda:Storage())
    monkeypatch.setattr(ap,'_write',lambda *a,**kw:pytest.fail('Unknown route must not permit migration'))
    with pytest.raises(ConnectionError):ap.ensure_portfolio_separation()


def test_missing_route_preserves_existing_legacy_separation_path(monkeypatch):
    monkeypatch.setenv('APP_ENVIRONMENT','test')
    class Storage:
        def read_json(self,name,default=None):
            assert name==control.route_key('autonomy')
            return None
    monkeypatch.setattr(control,'get_storage_service',lambda:Storage())
    reads=[]
    def legacy(path,default=None):
        reads.append(path)
        return {'positions':{}}
    monkeypatch.setattr(ap,'_read',legacy)
    monkeypatch.setattr(ap,'load_parameters',lambda:ap.AutonomousParameters())
    monkeypatch.setattr(ap,'_write',lambda *a,**kw:pytest.fail('Existing separated accounts need no writes'))
    assert ap.ensure_portfolio_separation()=={'positions_moved':0,'cash_restored':0}
    assert ap.PORTFOLIO_PATH in reads and ap.LEARNING_PORTFOLIO_PATH in reads
