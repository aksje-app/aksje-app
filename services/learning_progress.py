"""Read-only progress across persisted learning streams; never promotes a strategy."""
from datetime import datetime, timezone
from services.learning_evidence_report import summarize_learning_evidence

KEYS = {
    'baseline': 'controlled_learning/historical_baseline.json',
    'acceptance': 'controlled_learning/acceptance_latest.json',
    'maintenance': 'controlled_learning/observation_engine_state.json',
    'history': 'controlled_learning/history/index.json',
}


def snapshot(read_json, *, now=None, acceptance=None):
    now = now or datetime.now(timezone.utc)
    documents = {name: (acceptance if name == 'acceptance' and acceptance is not None else read_json(key))
                 for name, key in KEYS.items()}
    documents = {name: value if isinstance(value, dict) else {} for name, value in documents.items()}
    baseline, accepted = documents['baseline'], documents['acceptance']
    evidence = summarize_learning_evidence(baseline, accepted, [])
    engine = documents['maintenance']
    archive = documents['history']
    records = [r for r in archive.get('records', []) if isinstance(r, dict)]
    streams = {}
    for name in ('AUTONOMY', 'SUPER_PORTFOLIO', 'AUTONOMY_UNIVERSE'):
        ready = [r for r in records if r.get('engine') == name and r.get('status') == 'READY']
        streams[name] = {'frames': len(ready), 'first_at': min((r.get('at') or '' for r in ready), default=None),
                         'last_at': max((r.get('at') or '' for r in ready), default=None),
                         'whole_universe_frames': sum(r.get('complete_universe') is True for r in ready)}
    age = None
    try:
        recorded = datetime.fromisoformat(str(accepted['evaluated_at']).replace('Z', '+00:00'))
        age = (now - recorded).total_seconds() / 3600
    except (KeyError, TypeError, ValueError):
        pass
    return {**evidence, 'acceptance_at': accepted.get('evaluated_at'),
            'acceptance_age_hours': round(age, 1) if age is not None else None,
            'acceptance_fresh': age is not None and 0 <= age <= 48,
            'open_learning_positions': accepted.get('open_learning_positions'),
            'closed_learning_positions': accepted.get('closed_learning_positions'),
            'daily_observations': engine.get('daily', {}),
            'weekly_report': engine.get('weekly', {}), 'replay_streams': streams,
            'archive_status': archive.get('status', 'UNKNOWN'),
            'reported_archive_gaps': archive.get('gaps'),
            'historical_completeness': 'UNPROVEN_NO_RETROACTIVE_RECONSTRUCTION',
            'production_changed': False}
