from pathlib import Path
import ast
from app_version import APP_VERSION, PREVIOUS_APP_VERSION
root=Path(__file__).resolve().parents[1]
assert APP_VERSION == 'v19.22.0-rc16.34e'
assert PREVIOUS_APP_VERSION == 'v19.22.0-rc16.34d'
for name in ('autonomous_portfolio.py','controlled_parameter_learning.py','autonomy_parameter_governance.py','parameter_integrity.py','services/storage_service.py'):
    ast.parse((root/name).read_text())
s=(root/'autonomous_portfolio.py').read_text().split('def render_autonomous_portfolio',1)[1]
assert s.index('render_decisions(st)') < s.index('Produksjonsparametre – Autonomi') < s.index('_render_activation_analysis_v1980(st, pd)')
s=(root/'controlled_parameter_learning.py').read_text()
assert all(x in s for x in ('queue_proposal(', 'pending_parameter_proposals', 'statistics_basis', 'PAPER', 'PRODUKSJON', 'LÆRING'))
print('rc16.34e Parameter & Learning UX gate OK')
