"""Restart codec must not allocate a second full decoded journal."""
import json
import pytest
from services import restart_payload_codec as codec
from test_revision_trade_postgres import pg


def test_decoder_does_not_pass_the_complete_history_to_json_loads(monkeypatch):
    value={'accounts':{'autonomy':{'events':[{'text':'historikk – 📈'*2000,'i':i} for i in range(100)]}},'status':'ok'}
    record=json.loads(codec.encode_payload(json.dumps(value,ensure_ascii=True)))
    original=json.loads
    def bounded(text,*a,**kw):
        assert len(text)<100000,'whole decoded history materialized'
        return original(text,*a,**kw)
    monkeypatch.setattr(json,'loads',bounded)
    assert codec.decode_document(record)==value


@pytest.mark.parametrize('write_flag',[True,False])
def test_mutation_streams_encoding_without_whole_document_dumps(pg,monkeypatch,write_flag):
    monkeypatch.setenv('RESTART_BUNDLE_COMPRESSION_ENABLED','1')
    key='simulation_restarts/stream/bundle.json'
    value={'events':[{'text':'history'*2000,'i':i} for i in range(100)],'counter':0}
    pg.write_json(key,value)
    if not write_flag:monkeypatch.delenv('RESTART_BUNDLE_COMPRESSION_ENABLED')
    original=json.dumps
    def bounded(obj,*a,**kw):
        assert not (isinstance(obj,dict) and 'events' in obj),'whole plain journal serialized'
        return original(obj,*a,**kw)
    monkeypatch.setattr(json,'dumps',bounded)
    result=pg.mutate_json(key,lambda doc:{**doc,'counter':1})
    assert result=={**value,'counter':1}
    assert pg.read_json(key)==result


def test_large_event_does_not_reparse_every_small_input_chunk(monkeypatch):
    from services import restart_json_stream as stream
    text=json.dumps({'accounts':{'autonomy':{'events':[{'text':'x'*(3*1024**2)}]}}})
    original=json.JSONDecoder.raw_decode;work=[]
    def measured(self,document,idx=0):
        work.append(len(document)-idx)
        return original(self,document,idx)
    monkeypatch.setattr(json.JSONDecoder,'raw_decode',measured)
    value=stream.load(text[i:i+65536] for i in range(0,len(text),65536))
    assert len(value['accounts']['autonomy']['events'][0]['text'])==3*1024**2
    assert sum(work)<8*len(text),'large event repeatedly reparsed from its beginning'


@pytest.mark.parametrize('width',[1,2,3,7,64])
@pytest.mark.parametrize('text',[
    '{"accounts":{"a":{"events":[1e+20,-0.0,true,null,{"a":"\\u00e6\\ud83d\\udcc8"}]}}}',
    '{"events":[{},[],{"quote":"\\\"\\\\"}],"dup":1,"dup":2}',
    '{"accounts":null,"value":123456789012345678901234567890}',
    '{"events":[NaN,Infinity,-Infinity],"tail":"æøå 📈"}',
])
def test_small_chunks_preserve_standard_json_semantics(width,text):
    from services.restart_json_stream import load
    result=load(text[i:i+width] for i in range(0,len(text),width))
    assert json.dumps(result,ensure_ascii=True)==json.dumps(json.loads(text),ensure_ascii=True)


@pytest.mark.parametrize('text',['{"events":[1,]}','{"a":1,}','{"a":1e}','{"a":true false}',
                                  '{"accounts":{"a":{"events":[{}]}}} trailing','{"a":"unfinished'])
def test_malformed_input_never_returns_a_partial_journal(text):
    from services.restart_json_stream import load
    with pytest.raises(ValueError):load(text[i:i+3] for i in range(0,len(text),3))


def test_streamed_encoder_preserves_existing_wire_bytes():
    from datetime import datetime,timezone
    import base64,hashlib,zlib
    value={'text':'æøå 📈 \\ \"'*20000,'events':[None,True,False,-0.0,1e100,12345678901234567890],
           'default_str':datetime(2026,11,16,tzinfo=timezone.utc)}
    raw=json.dumps(value,ensure_ascii=True,default=str).encode('ascii')
    expected=json.dumps({'__restart_storage__':codec.MARKER,'uncompressed_bytes':len(raw),
                         'sha256':hashlib.sha256(raw).hexdigest(),
                         'data':base64.b64encode(zlib.compress(raw,6)).decode('ascii')},separators=(',',':'))
    actual,size=codec.encode_document(value)
    assert actual==expected
    assert codec.encode_payload(raw.decode('ascii'))==expected
    assert size==json.loads(actual)['uncompressed_bytes']


def test_compressed_input_is_also_decoded_in_bounded_chunks(monkeypatch):
    import random
    value={'events':[{'text':random.Random(1).randbytes(1024**2).hex()}]}
    record=json.loads(codec.encode_payload(json.dumps(value)))
    original=codec.base64.b64decode
    def bounded(text,*a,**kw):
        assert len(text)<=1024**2,'entire compressed history decoded at once'
        return original(text,*a,**kw)
    monkeypatch.setattr(codec.base64,'b64decode',bounded)
    assert codec.decode_document(record)==value
