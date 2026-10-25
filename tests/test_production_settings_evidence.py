"""Stored strategy evidence is required before requests or market-data previews."""
from copy import deepcopy
import pytest
from services import production_routing as routing, simulation_restart as restart


class Snapshot:
    def __init__(self, documents):
        self.documents = deepcopy(documents)
    def using_postgres(self):
        return False
    def read_json(self, name, default=None):
        return deepcopy(self.documents.get(name, default))


@pytest.mark.parametrize('family', list(restart.CAPITALS))
@pytest.mark.parametrize('unrecognized', [False, True])
def test_missing_stored_configuration_cannot_fall_back_to_defaults(family, unrecognized):
    documents = {'settings/trading_rules.json': {'unknown':1},
        'autonomous_portfolio/parameters.json': {'unknown':1},
        'super_portfolio/state.json': {'config': {'unknown':1}}} if unrecognized else {}
    snapshot = Snapshot(documents)
    with pytest.raises(ValueError, match='Stored .* settings required'):
        routing.strategy_settings(family, storage=snapshot, require_stored=True)
    assert snapshot.documents == documents


@pytest.mark.parametrize('family,key,value,field,expected', [
    ('paper','settings/trading_rules.json',{'max_open_positions':3},'max_open_positions',3),
    ('autonomy','autonomous_portfolio/parameters.json',{'maximum_open_positions':13},'maximum_open_positions',13),
    ('super_portfolio','super_portfolio/state.json',{'config':{'transaction_cost_bps':17}},'transaction_cost_bps',17),
])
def test_stored_overrides_and_existing_runtime_normalization_are_preserved(family,key,value,field,expected):
    snapshot = Snapshot({key:value})
    before = deepcopy(snapshot.documents)
    normal = routing.strategy_settings(family,storage=snapshot)
    strict = routing.strategy_settings(family,storage=snapshot,require_stored=True)
    assert strict == normal
    assert strict[field] == expected
    assert snapshot.documents == before
