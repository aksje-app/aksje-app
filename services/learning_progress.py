"""Read-only progress across persisted learning streams; never promotes a strategy."""
from datetime import datetime, timezone
from services.learning_evidence_report import summarize_learning_evidence, summarize_measured_observation_horizons

KEYS = {
    'baseline': 'controlled_learning/historical_baseline.json',
    'acceptance': 'controlled_learning/acceptance_latest.json',
    'maintenance': 'controlled_learning/observation_engine_state.json',
    'history': 'controlled_learning/history/index.json',
    'observations': 'controlled_learning/observation_cohorts.json',
    'autonomy_forward': 'controlled_learning/forward/AUTONOMY.json',
    'super_forward': 'controlled_learning/forward/SUPER_PORTFOLIO.json',
}


def snapshot(read_json, *, now=None, acceptance=None):
    now = now or datetime.now(timezone.utc)
    documents = {name: (acceptance if name == 'acceptance' and acceptance is not None else read_json(key))
                 for name, key in KEYS.items()}
    observations = documents.pop('observations', [])
    observations = [r for r in observations if isinstance(r, dict)] if isinstance(observations, list) else []
    documents = {name: value if isinstance(value, dict) else {} for name, value in documents.items()}
    baseline, accepted = documents['baseline'], documents['acceptance']
    evidence = summarize_learning_evidence(baseline, accepted, observations)
    engine = documents['maintenance']
    archive = documents['history']
    records = [r for r in archive.get('records', []) if isinstance(r, dict)]
    streams = {}
    for name in ('AUTONOMY', 'SUPER_PORTFOLIO', 'AUTONOMY_UNIVERSE'):
        ready = [r for r in records if r.get('engine') == name and r.get('status') == 'READY']
        streams[name] = {'frames': len(ready), 'first_at': min((r.get('at') or '' for r in ready), default=None),
                         'last_at': max((r.get('at') or '' for r in ready), default=None),
                         'whole_universe_frames': sum(r.get('complete_universe') is True for r in ready)}
        forward = documents.get('autonomy_forward' if name == 'AUTONOMY' else 'super_forward', {}) if name != 'AUTONOMY_UNIVERSE' else {}
        streams[name].update(forward_status=forward.get('status', 'CAPTURE_ONLY' if name == 'AUTONOMY_UNIVERSE' else 'NOT_STARTED'),
            forward_last_at=forward.get('last_at'), forward_trading_dates=forward.get('observed_trading_dates'),
            independent_strategy_test=name != 'AUTONOMY_UNIVERSE',
            forward_variants=[{k:row.get(k) for k in ('parameters','net_return_pct','maximum_drawdown_pct','trade_count','costs')}
                              for row in (forward.get('accounts') or [])[:3] if isinstance(row,dict)])
    age = None
    try:
        recorded = datetime.fromisoformat(str(accepted['evaluated_at']).replace('Z', '+00:00'))
        age = (now - recorded).total_seconds() / 3600
    except (KeyError, TypeError, ValueError):
        pass
    from learning_runtime import MAX_ARCHIVE_BYTES, MAX_RECORDS
    archive_status = archive.get('status', 'UNKNOWN')
    if archive_status == 'STORAGE_BUDGET_REACHED' and isinstance(archive.get('bytes'), int) and archive['bytes']<MAX_ARCHIVE_BYTES and len(records)<MAX_RECORDS:
        archive_status = 'CAPACITY_RESTORED_AWAITING_NEW_FRAME'
    return {**evidence, 'measured_shadow_horizons': summarize_measured_observation_horizons(observations),
            'newest_observation_entry': max((str(r.get('entry_at') or '') for r in observations if isinstance(r, dict)),default=None),
            'acceptance_at': accepted.get('evaluated_at'),
            'acceptance_age_hours': round(age, 1) if age is not None else None,
            'acceptance_fresh': age is not None and 0 <= age <= 48,
            'open_learning_positions': accepted.get('open_learning_positions'),
            'closed_learning_positions': accepted.get('closed_learning_positions'),
            'daily_observations': engine.get('daily', {}),
            'weekly_report': engine.get('weekly', {}), 'replay_streams': streams,
            'archive_status': archive_status,
            'archive_recorded_status': archive.get('status'),
            'archive_bytes': archive.get('bytes'),
            'archive_budget_bytes': MAX_ARCHIVE_BYTES,
            'archive_remaining_bytes': max(0,MAX_ARCHIVE_BYTES-int(archive.get('bytes') or 0)),
            'reported_archive_gaps': archive.get('gaps'),
            'historical_completeness': 'UNPROVEN_NO_RETROACTIVE_RECONSTRUCTION',
            'production_changed': False}
