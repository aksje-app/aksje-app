"""Faster canonical hashing must preserve every existing signature and event hash."""
import hashlib
import json
import random
import pytest
from services import economic_opening as opening


def expected(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def test_native_and_streaming_hashes_match_historical_canonical_bytes(monkeypatch):
    rng=random.Random(20261105)
    values=[None,True,False,0,-1,10**300,1e-308,1e308,-0.0,{'ø':['💹','\n\t\x00','e\u0301','é',1.25]},
            {3:'integer keys',1:'still supported'},[{'shared':[]}]*3]
    for _ in range(200):
        values.append({'nested':[{'value':rng.uniform(-1e12,1e12),'count':rng.randrange(-10000,10000),
                                'text':rng.choice(['NOK','Årsrapport','💹','', '\\ud83d'])} for _ in range(rng.randrange(30))]})
    original_budget=opening._NATIVE_CANONICAL_BYTES
    for value in values:
        wanted=expected(value)
        assert opening.digest(value)==wanted
        monkeypatch.setattr(opening,'_NATIVE_CANONICAL_BYTES',0)
        assert opening.digest(value)==wanted
        monkeypatch.setattr(opening,'_NATIVE_CANONICAL_BYTES',original_budget)


def test_large_history_keeps_streaming_all_records_and_same_hash(monkeypatch):
    value={'historical':[{'sequence':i,'text':'ø'*200,'amount':i/37} for i in range(20000)]}
    wanted=expected(value)
    # Values beyond the budget must never build a whole native JSON string.
    original = json.dumps
    def bounded(item, **kwargs):
        assert item is not value
        assert opening._native_canonical_fits(item)
        return original(item, **kwargs)
    monkeypatch.setattr(opening.json, 'dumps', bounded)
    assert opening.digest(value)==wanted


@pytest.mark.parametrize('value',[float('nan'),float('inf'),float('-inf'),{1:'mixed','x':'keys'}, {'bytes':b'bad'}])
def test_invalid_values_remain_rejected(value):
    with pytest.raises((ValueError,TypeError)): opening.digest(value)


def test_circular_history_remains_rejected():
    value=[];value.append(value)
    with pytest.raises(ValueError,match='Circular'): opening.digest(value)
