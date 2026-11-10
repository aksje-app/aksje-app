"""Lossless bounded restart persistence, including corrupted-backup failure modes."""
import base64,hashlib,json,zlib
import pytest
from test_revision_trade_postgres import pg
from services.storage_service import StorageUnavailableError

MARKER='ZLIB_BASE64_JSON_V1'
FLAG='RESTART_BUNDLE_COMPRESSION_ENABLED'


def envelope(value):
    raw=json.dumps(value,ensure_ascii=True).encode('ascii')
    return {'__restart_storage__':MARKER,'uncompressed_bytes':len(raw),
            'sha256':hashlib.sha256(raw).hexdigest(),'data':base64.b64encode(zlib.compress(raw)).decode()}


def raw_put(pg,key,value):
    conn=pg._conn()
    try:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO app_kv_store(name,payload,updated_at) VALUES(%s,%s,NOW()::text) ON CONFLICT(name) DO UPDATE SET payload=EXCLUDED.payload',(key,json.dumps(value,separators=(',',':'))))
        conn.commit()
    finally:conn.close()


def raw_get(pg,key):
    conn=pg._conn()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT payload FROM app_kv_store WHERE name=%s',(key,));return cur.fetchone()[0]
    finally:conn.close()


def test_reader_accepts_legacy_and_encoded_restart_independent_of_write_flag(pg,monkeypatch):
    monkeypatch.delenv(FLAG,raising=False)
    key='simulation_restarts/codec/bundle.json';value={'text':'historikk – 📈','events':[1,2],'opaque_hash':'00ab'}
    pg.write_json(key,value);assert pg.read_json(key)==value
    raw_put(pg,key,envelope(value))
    assert pg.read_json(key)==value


def test_opt_in_write_is_small_lossless_stable_and_stays_encoded(pg,monkeypatch):
    monkeypatch.setenv(FLAG,'1')
    key='simulation_restarts/compressed/bundle.json'
    value={'text':'historikk – 📈 \\ \"'*100000,'counter':0,'opaque_hash':'abc123','amount':12.3456789}
    pg.write_json(key,value)
    stored=raw_get(pg,key);assert json.loads(stored).get('__restart_storage__')==MARKER
    assert len(stored)<len(json.dumps(value))/5
    assert pg.read_json(key)==value
    revision=pg.json_row_versions([key]);pg.write_json(key,value);assert pg.json_row_versions([key])==revision
    monkeypatch.delenv(FLAG)
    pg.mutate_json(key,lambda doc:{**doc,'counter':1})
    assert json.loads(raw_get(pg,key)).get('__restart_storage__')==MARKER
    assert pg.read_json(key)=={**value,'counter':1}


@pytest.mark.parametrize('damage',['checksum','length','truncated','extra_stream','version'])
def test_corrupt_restart_never_reaches_financial_callback(pg,damage):
    key='simulation_restarts/corrupt/bundle.json';record=envelope({'cash':500000,'events':[]})
    if damage=='checksum':record['sha256']='0'*64
    elif damage=='length':record['uncompressed_bytes']+=1
    elif damage=='truncated':record['data']=record['data'][:-4]
    elif damage=='extra_stream':record['data']=base64.b64encode(base64.b64decode(record['data'])+zlib.compress(b'{}')).decode()
    else:record['__restart_storage__']='UNKNOWN_VERSION'
    raw_put(pg,key,record);before=raw_get(pg,key);calls=[]
    with pytest.raises(StorageUnavailableError):pg.read_json(key)
    with pytest.raises(ValueError):pg.mutate_json(key,lambda doc:calls.append(doc))
    assert calls==[] and raw_get(pg,key)==before


def test_other_document_names_do_not_decode_or_encode_restart_envelopes(pg,monkeypatch):
    monkeypatch.setenv(FLAG,'1');key='ordinary/codec.json';value=envelope({'legitimate':'ordinary data'})
    pg.write_json(key,value);assert pg.read_json(key)==value


def test_immutable_restart_returns_existing_decoded_record(pg,monkeypatch):
    monkeypatch.setenv(FLAG,'1');key='simulation_restarts/immutable/bundle.json';value={'text':'x'*1100000}
    assert pg.write_json_immutable(key,value)==value
    assert json.loads(raw_get(pg,key)).get('__restart_storage__')==MARKER
    assert pg.write_json_immutable(key,{'conflict':True})==value


def test_corrupt_encoded_database_cannot_fall_back_to_stale_local_financial_state(pg):
    key='simulation_restarts/no-fallback/bundle.json';record=envelope({'cash':500000})
    record['sha256']='0'*64;raw_put(pg,key,record)
    path=pg.base_dir/key;path.parent.mkdir(parents=True);path.write_text('{"cash":999}')
    pg.allow_local_fallback=True
    with pytest.raises(StorageUnavailableError):pg.read_json(key)


def test_corrupt_immutable_restart_never_retries_or_falls_back(pg,monkeypatch):
    key='simulation_restarts/immutable-corrupt/bundle.json';record=envelope({'cash':500000})
    record['sha256']='0'*64;raw_put(pg,key,record);before=raw_get(pg,key)
    path=pg.base_dir/key;path.parent.mkdir(parents=True);path.write_text('{"cash":999}')
    pg.allow_local_fallback=True;retries=[]
    monkeypatch.setattr('services.storage_service.time.sleep',lambda seconds:retries.append(seconds))
    with pytest.raises(StorageUnavailableError):pg.write_json_immutable(key,{'cash':123})
    assert retries==[] and raw_get(pg,key)==before and path.read_text()=='{"cash":999}'


def test_immutable_size_guard_never_falls_back(pg,monkeypatch):
    from services import restart_payload_codec as codec
    key='simulation_restarts/immutable-oversize/bundle.json'
    monkeypatch.setenv(FLAG,'1');monkeypatch.setattr(codec,'MAX_STORED_BYTES',200)
    pg.allow_local_fallback=True
    with pytest.raises(StorageUnavailableError):pg.write_json_immutable(key,{'text':'x'*1100000})
    assert not (pg.base_dir/key).exists() and pg.read_json(key,None) is None


def test_mutable_size_guard_never_falls_back(pg,monkeypatch):
    from services import restart_payload_codec as codec
    key='simulation_restarts/mutable-oversize/bundle.json'
    monkeypatch.setenv(FLAG,'1');monkeypatch.setattr(codec,'MAX_STORED_BYTES',200)
    pg.allow_local_fallback=True
    with pytest.raises(StorageUnavailableError):pg.write_json(key,{'text':'x'*1100000})
    assert not (pg.base_dir/key).exists() and pg.read_json(key,None) is None


def test_truncated_outer_restart_json_never_falls_back(pg):
    key='simulation_restarts/truncated-outer/bundle.json'
    conn=pg._conn()
    try:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO app_kv_store(name,payload,updated_at) VALUES(%s,%s,NOW()::text)',(key,'{"__restart_storage__":"ZLIB_BASE64_JSON_V1"'))
        conn.commit()
    finally:conn.close()
    path=pg.base_dir/key;path.parent.mkdir(parents=True);path.write_text('{"cash":999}')
    pg.allow_local_fallback=True
    with pytest.raises(StorageUnavailableError):pg.read_json(key)


@pytest.mark.parametrize('enabled',['0','1'])
def test_database_size_guard_preserves_old_document(pg,monkeypatch,enabled):
    from services import restart_payload_codec as codec
    monkeypatch.delenv(FLAG,raising=False)
    key='simulation_restarts/size-guard/bundle.json';value={'text':'x'*1100000,'counter':0}
    pg.write_json(key,value);before=raw_get(pg,key)
    monkeypatch.setenv(FLAG,enabled);monkeypatch.setattr(codec,'MAX_STORED_BYTES',200)
    with pytest.raises(ValueError,match='limit|exceeds'):
        pg.mutate_json(key,lambda doc:{**doc,'counter':1})
    assert raw_get(pg,key)==before and pg.read_json(key)==value


def test_decoded_size_is_bounded_before_json_parsing():
    from services.restart_payload_codec import decode_document,RestartPayloadError
    record=envelope({'text':'x'*1100000});record['uncompressed_bytes']=4
    with pytest.raises(RestartPayloadError,match='length|termination'):decode_document(record)


def test_codec_preserves_legacy_utf8_serialization():
    from services.restart_payload_codec import encode_payload,decode_document
    value={'text':'æøå – 📈','opaque_hash':'00ff'};raw=json.dumps(value,ensure_ascii=False)
    stored=json.loads(encode_payload(raw))
    assert stored['uncompressed_bytes']==len(raw.encode('utf8'))
    assert stored['sha256']==hashlib.sha256(raw.encode('utf8')).hexdigest()
    assert decode_document(stored)==value


def test_encoding_maintenance_changes_only_storage_and_is_idempotent(pg,monkeypatch):
    key='simulation_restarts/migrate/bundle.json';value={'text':'historikk – 📈'*100000,'counter':0}
    monkeypatch.delenv(FLAG,raising=False);pg.write_json(key,value)
    before=raw_get(pg,key);revision=pg.json_row_versions([key])
    monkeypatch.setenv(FLAG,'1')
    assert pg.read_json(key)==value and pg.json_row_versions([key])==revision
    result=pg.ensure_restart_encoding(key)
    assert result['state']=='ENCODED' and result['source_sha256']==hashlib.sha256(before.encode()).hexdigest()
    assert result['financial_state_changed'] is False
    assert pg.read_json(key)==value
    revision=pg.json_row_versions([key])
    assert pg.ensure_restart_encoding(key)['state']=='ALREADY_ENCODED'
    assert pg.json_row_versions([key])==revision


def test_encoding_maintenance_and_financial_mutations_serialize_without_lost_updates(pg,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    key='simulation_restarts/migrate-concurrently/bundle.json';value={'text':'x'*1100000,'counter':0}
    monkeypatch.delenv(FLAG,raising=False);pg.write_json(key,value);monkeypatch.setenv(FLAG,'1')
    def operation(i):
        if i<2:return pg.ensure_restart_encoding(key)
        return pg.mutate_json(key,lambda doc:{**doc,'counter':doc['counter']+1})
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(operation,range(5)))
    assert pg.read_json(key)=={**value,'counter':3}
