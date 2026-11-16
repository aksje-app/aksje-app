import copy
import hashlib
import json
import pytest
from services import restart_payload_archive as archive
from services.restart_payload_codec import decode_document, RestartPayloadError


def sample():
    return {'period_id':'unit','accounts':{'paper':{'account':{'cash':100},'events':[
        {'kind':'TEST','hash':'original','payload':{'text':'norsk æ 📈','nested':[{'n':1}]}},
        {'kind':'TEST','hash':'original2','payload':{'n':2}}]}}}


def test_externalize_roundtrip_keeps_hashes_and_lazy_working_set():
    source=sample(); before=copy.deepcopy(source); blobs={}
    compact=archive.externalize(source,'simulation_restarts/unit/bundle.json',lambda key,value:blobs.setdefault(key,value))
    assert source==before and len(blobs)==2
    assert compact['accounts']['paper']['events'][0]['hash']=='original'
    ref=compact['accounts']['paper']['events'][0]['payload']
    assert set(ref)=={'__restart_payload__','key','sha256','uncompressed_bytes'}
    calls=[]
    loader=archive.validating_loader(lambda key:(calls.append(key),blobs[key])[1])
    encoded,_=archive.encode_root(compact)
    decoded=decode_document(json.loads(encoded),payload_loader=loader)
    assert calls==[]
    assert decoded==source and calls
    assert json.loads(json.dumps(decoded,sort_keys=True))==source
    assert archive.semantic_sha256(decoded)==archive.semantic_sha256(source)
    with pytest.raises(TypeError):decoded['accounts']['paper']['events'][0]['payload']['nested'][0]['n']=9
    assert archive.is_archived(decoded)
    reused=archive.externalize(decoded,'simulation_restarts/unit/bundle.json',lambda *args:pytest.fail('rewrites immutable history'))
    assert reused==compact


def test_v2_without_loader_fails_closed():
    compact=archive.externalize(sample(),'simulation_restarts/unit/bundle.json',lambda *a:None)
    encoded,_=archive.encode_root(compact)
    with pytest.raises(RestartPayloadError):decode_document(json.loads(encoded))


@pytest.mark.parametrize('damage',['checksum','key','period','size','blob','missing'])
def test_damaged_reference_or_blob_never_becomes_payload(damage):
    blobs={}
    compact=archive.externalize(sample(),'simulation_restarts/unit/bundle.json',lambda k,v:blobs.setdefault(k,v))
    ref=compact['accounts']['paper']['events'][0]['payload']
    if damage=='checksum':ref['sha256']='0'*64
    if damage=='key':ref['key']='other/private.json'
    if damage=='period':ref['key']=ref['key'].replace('/unit/','/elsewhere/')
    if damage=='size':ref['uncompressed_bytes']=archive.MAX_PAYLOAD_RAW_BYTES+1
    if damage=='blob':blobs[ref['key']]=blobs[ref['key']].replace('data":"','data":"AAAA',1)
    if damage=='missing':blobs.clear()
    encoded,_=archive.encode_root(compact)
    with pytest.raises((RestartPayloadError,KeyError)):
        value=decode_document(json.loads(encoded),payload_loader=archive.validating_loader(blobs.__getitem__))
        json.dumps(value)


def test_encoded_cache_is_bounded_and_validates_first_read(monkeypatch):
    blobs={};compact=archive.externalize(sample(),'simulation_restarts/unit/bundle.json',lambda k,v:blobs.setdefault(k,v))
    calls=[];monkeypatch.setattr(archive,'ENCODED_CACHE_BYTES',1)
    loader=archive.validating_loader(lambda key:(calls.append(key),blobs[key])[1])
    refs=[e['payload'] for e in compact['accounts']['paper']['events']]
    assert loader(refs[0])==sample()['accounts']['paper']['events'][0]['payload']
    loader(refs[1]);loader(refs[0]);assert len(calls)==3


def test_reference_in_unarchived_native_event_cannot_be_silently_accepted():
    source=sample();source['accounts']['paper']['events'][0]['payload']={'__restart_payload__':'untrusted'}
    with pytest.raises(RestartPayloadError):archive.externalize(source,'simulation_restarts/unit/bundle.json',lambda *a:None)
