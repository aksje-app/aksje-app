import ast
from pathlib import Path
from app_version import APP_VERSION, PREVIOUS_APP_VERSION

root = Path(__file__).resolve().parents[1]
assert APP_VERSION == 'v19.22.0-rc16.34f'
assert PREVIOUS_APP_VERSION == 'v19.22.0-rc16.34e'
for name in ('repositories/application.py', 'services/storage_service.py', 'services/autonomy_activation_service.py'):
    ast.parse((root / name).read_text())
source = (root / 'services/autonomy_activation_service.py').read_text()
assert 'self.analyses.list(limit=1)' in source
assert 'self.analyses.list(limit=limit, offset=offset)' in source
print('rc16.34f Activation history memory gate OK')
