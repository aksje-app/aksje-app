"""Exercise the private session's pure mutations with real journal validation."""
from copy import deepcopy
import hashlib
import json

import pytest
from test_restart_trading import active
from test_simulation_restart import certificate, sources, dump_program, sealed, storage, prepare
from services import portfolio_accounting as ledger, restart_trading as trading
from services.economic_opening import digest


def test_canonical_digest_matches_historical_bytes():
    values = [None, {'æ': ['🟢', 1.25, -0.0, True, None], 'a': {'z': 2}}, list(range(10000))]
    for value in values:
        encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
        assert digest(value) == hashlib.sha256(encoded).hexdigest()
    with pytest.raises(ValueError):
        digest({'bad': float('nan')})


def test_private_marks_share_immutable_history_and_leave_source_unchanged(active):
    storage, bundle, public = active
    original = storage.read_json(trading.restart._key(bundle['period_id']))
    before = deepcopy(original)
    memory = trading.Memory(original, trading.restart._key(bundle['period_id']))
    scoped = trading._SessionStorage(bundle['period_id'], memory)
    previous = memory.bundle['accounts']['autonomy']
    result = ledger.mark('autonomy', {}, at=bundle['start_at'], storage=scoped)
    ledger.verify(result)
    assert original == before
    assert result['events'] is not previous['events']
    assert result['events'][0] is previous['events'][0]
    # Public reads still detach nested historical data.
    detached = public.read_json(ledger.key('autonomy'))
    detached['events'][0]['payload']['prepared_by'] = 'tamper'
    assert storage.read_json(trading.restart._key(bundle['period_id'])) == before


def test_private_transaction_rejects_history_tampering(active):
    storage, bundle, _ = active
    memory = trading.Memory(storage.read_json(trading.restart._key(bundle['period_id'])), trading.restart._key(bundle['period_id']))
    scoped = trading._SessionStorage(bundle['period_id'], memory)
    def corrupt(doc):
        changed = deepcopy(doc)
        changed['events'][0]['payload']['prepared_by'] = 'tamper'
        return changed
    with pytest.raises(ValueError, match='journal|integrity'):
        scoped.mutate_json(ledger.key('autonomy'), corrupt)
