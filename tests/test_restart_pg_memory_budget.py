"""Run the real large upsert on a disposable PostgreSQL capped at 1 GiB."""
import hashlib,json,os,subprocess,time,uuid
import pytest

pytestmark=pytest.mark.skipif(os.getenv('RUN_RESTART_PG_MEMORY')!='1',reason='Explicit isolated PostgreSQL memory acceptance')


def test_large_restart_write_fits_database_budget():
    import psycopg2
    from services.large_json_write import write_restart_payload
    name='restart-copy-memory-'+uuid.uuid4().hex[:12]
    subprocess.run(['docker','run','-d','--name',name,'--memory=1g','--memory-swap=1g',
        '-e','POSTGRES_USER=test','-e','POSTGRES_PASSWORD=test','-e','POSTGRES_DB=isolated',
        '-p','127.0.0.1::5432','postgres:16'],check=True,capture_output=True)
    try:
        port=json.loads(subprocess.check_output(['docker','inspect','--format','{{json .NetworkSettings.Ports}}',name]))['5432/tcp'][0]['HostPort']
        for _ in range(60):
            try:
                conn=psycopg2.connect(f'postgresql://test:test@127.0.0.1:{port}/isolated',connect_timeout=2)
                break
            except psycopg2.OperationalError:time.sleep(0.5)
        else:pytest.fail('Disposable PostgreSQL did not become ready')
        try:
            payload=json.dumps({'events':[{'text':'NOK \\ \" historikk – 📈 '+('x'*14970),'id':i} for i in range(10450)]},ensure_ascii=True)
            with conn.cursor() as cur:
                cur.execute('CREATE TABLE app_kv_store(name text primary key,payload text,updated_at text)')
                write_restart_payload(cur,'simulation_restarts/isolated/bundle.json',payload)
            conn.commit()
            with conn.cursor() as cur:
                cur.execute('SELECT md5(payload),octet_length(payload) FROM app_kv_store')
                assert cur.fetchone()==(hashlib.md5(payload.encode()).hexdigest(),len(payload))
            peak=int(subprocess.check_output(['docker','exec',name,'cat','/sys/fs/cgroup/memory.peak']))
            events=dict(line.split() for line in subprocess.check_output(['docker','exec',name,'cat','/sys/fs/cgroup/memory.events'],text=True).splitlines())
            assert peak<1024**3 and events['oom_kill']=='0' and events['oom']=='0'
            print(json.dumps({'synthetic_json_bytes':len(payload),'database_peak_mib':round(peak/1024**2,1),'memory_events':events}))
        finally:conn.close()
    finally:
        subprocess.run(['docker','rm','-f',name],check=True,capture_output=True)
