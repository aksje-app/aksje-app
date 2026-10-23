"""Read-only source discovery; output belongs in a private operator directory."""
import os
import subprocess
from pathlib import Path
from storage_architecture import get_runtime_paths,PROJECT_ROOT
from services.simulation_archive import CATEGORIES,sha
from services.economic_opening import digest


def discover(*,extra_roots=None):
    paths=get_runtime_paths(create=False)
    roots={'runtime':paths.root}
    # Historical releases used repository-relative stores outside runtime.
    for name in ('data','cache','logs','storage','runtime','reports','models','config','.streamlit','learning','learning_data','exports','backups','artifacts'):
        path=PROJECT_ROOT/name
        if path.is_dir() and path.resolve()!=paths.root.resolve():roots['legacy_'+name.strip('.')]=path
    for name,path in (extra_roots or {}).items():roots[name]=Path(path)
    from services.storage_service import get_storage_service
    # The auth adapter can have an independent DB and local store.
    storage=get_storage_service()
    roots['storage_services']=storage.base_dir
    auth=Path(os.getenv('AUTH_STORAGE_ROOT') or paths.data/'auth')
    if not auth.is_absolute():auth=PROJECT_ROOT/auth
    roots['auth_local']=auth
    try:tracked=set(subprocess.check_output(['git','ls-files'],cwd=PROJECT_ROOT,text=True,stderr=subprocess.DEVNULL).splitlines())
    except (OSError,subprocess.CalledProcessError):tracked=set()
    for path in PROJECT_ROOT.iterdir():
        if path.is_file() and path.name not in tracked and (path.suffix.lower() in {'.json','.jsonl','.db','.sqlite','.sqlite3','.pkl','.pickle','.joblib','.pdf','.xlsx','.csv','.bin'} or path.name.startswith('.env') or path.name.endswith(('-wal','-shm'))):
            roots['loose_'+str(len(roots))]=path
    for name,value in os.environ.items():
        if name.startswith(('APP_','REPORT_','MODEL_','LEARNING_','AUTH_','STORAGE_')) and name.endswith(('_ROOT','_DIR','_PATH')) and value and Path(value).exists():
            roots['configured_'+name.lower()]=Path(value)
    existing={k:v.resolve() for k,v in roots.items() if v.exists()}
    # Preserve each tree once; aliases remain visible for operator review.
    included={k:v for k,v in existing.items() if not any(v!=other and other in v.parents for other in existing.values())}
    unique={};seen=set()
    for k,v in included.items():
        if v not in seen:unique[k]=str(v);seen.add(v)
    databases={name:name for name in ('DATABASE_URL','AUTH_DATABASE_URL','POSTGRES_URL','RENDER_DATABASE_URL') if os.getenv(name)}
    result=dict(runtime_roots=unique,discovered_aliases={k:str(v) for k,v in existing.items()},
        database_environment_variables=databases,coverage={c:list(unique)+list(databases) for c in sorted(CATEGORIES)},
        required_operator_review=['All Render services/disks and cron/worker runtime roots',
          'External report/model/object stores and mounts must be staged and included explicitly',
          'Retired runtime/legacy directories, auth DB, SQLite and binary learning models',
          'Quiesce every writer; databases alone are insufficient; validate exclusions and coverage'],
        coverage_confirmed=False)
    result['inventory_sha256']=digest(result)
    return result
