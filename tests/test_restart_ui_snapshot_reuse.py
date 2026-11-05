"""Selected-account UI exports reuse the same verified journal snapshot."""
from unittest.mock import MagicMock
from test_restart_trading import active
from test_simulation_restart import certificate, sources, dump_program, sealed, storage, prepare
from services import production_restart as control, simulation_restart as restart
from ui import simulation_restart as ui


def test_restart_ui_does_not_load_selected_bundle_again(active, monkeypatch):
    backend, initial, _ = active
    bundle = backend.read_json(restart._key(initial['period_id']))
    bundle['production_controls'] = {'autonomy': {'status': 'RUNNING'}}
    chosen = {'pointer': {'family': 'autonomy', 'period_id': bundle['period_id']}, 'bundle': bundle}
    st = MagicMock()
    st.text_input.return_value = bundle['period_id']
    def duplicate(*args, **kw):
        raise AssertionError('UI loaded an already verified selection again')
    monkeypatch.setattr(control, 'selected', duplicate)
    ui.render(st, 'autonomy', chosen=chosen)
    assert st.error.call_count == 0
    # CSV/XLSX/PDF/ZIP plus JSON; actual export transformations run.
    assert st.download_button.call_count == 5
    for call in st.download_button.call_args_list:
        assert call.args[1]
