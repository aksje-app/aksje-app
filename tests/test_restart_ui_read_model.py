"""Menu reads cannot deserialize journals or eagerly generate financial exports."""
import json
import time
from copy import deepcopy
from unittest.mock import MagicMock
import pytest
from test_production_restart import ready,activate
from test_revision_trade_postgres import pg
from test_simulation_restart import sources,certificate
from services import restart_ui_snapshot as ui, production_restart as control, simulation_restart as restart


def test_ui_projection_preserves_verified_figures_and_navigation_avoids_bundle(ready,monkeypatch):
    r=ready
    for family in restart.CAPITALS:activate(r,family)
    before=r['pg'].read_json(restart._key(r['bundle']['period_id']))
    assert ui.publish(storage=r['pg'])['families']==list(restart.CAPITALS)
    assert r['pg'].read_json(restart._key(r['bundle']['period_id']))==before
    original=r['pg'].read_json
    def small_only(key,*args,**kwargs):
        assert not key.endswith('/bundle.json'), 'menu deserialized the financial journal'
        return original(key,*args,**kwargs)
    monkeypatch.setattr(r['pg'],'read_json',small_only)
    for family in restart.CAPITALS:
        model=ui.read(family,storage=r['pg'],refresh=False)
        assert model['data']['account']['new_period']['cash_nok']==restart.CAPITALS[family]
        assert model['projection']['portfolio_value']==restart.CAPITALS[family]
        assert len(json.dumps(model))<100_000
        from ui.simulation_restart import render_active
        st=MagicMock();st.text_input.return_value=r['bundle']['period_id'];st.checkbox.return_value=False
        monkeypatch.setattr(ui,'get_storage_service',lambda:r['pg'])
        started=time.monotonic()
        assert render_active(st,family)
        assert time.monotonic()-started<2
        assert st.error.call_count==0
        assert st.download_button.call_count==6
        assert all(callable(c.args[1]) for c in st.download_button.call_args_list)
    # Export is deferred until invoked and still includes the entire journal.
    monkeypatch.setattr(r['pg'],'read_json',original)
    from ui.simulation_restart import _full_export
    exported=json.loads(_full_export(r['bundle']['period_id'],'autonomy','json')())
    assert exported['account']['new_period']['journal']==before['accounts']['autonomy']['events']
    # Corrupt UI cache stays pending rather than exposing forged balances.
    model=original(ui.key('paper'));model['projection']['cash']=-123
    r['pg'].write_json(ui.key('paper'),model)
    assert ui.read('paper',storage=r['pg'],refresh=False)['loading']
    # A route switch cannot show the old period.
    ptr=original(control.route_key('autonomy'));ptr['period_id']='different'
    r['pg'].write_json(control.route_key('autonomy'),ptr)
    assert ui.read('autonomy',storage=r['pg'],refresh=False)['loading']


def test_ui_publisher_rejects_corrupt_authoritative_journal(ready):
    r=ready;activate(r)
    name=restart._key(r['bundle']['period_id'])
    bundle=r['pg'].read_json(name);bundle['accounts']['paper']['account']['cash']+=1
    r['pg'].write_json(name,bundle)
    with pytest.raises(ValueError):ui.publish(storage=r['pg'])
    assert r['pg'].read_json(ui.key('paper'),None) is None
