"""Explicit decisions and history in the authoritative parameter document.

Parameters, proposal status and history commit together. No portfolio data is
written here. Rejected variants share a cooldown per parameter and dataset.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import uuid

KEY = 'autonomous_portfolio/parameters.json'
META = '_governance'
LABELS = {'maximum_position_pct': 'Maks posisjon i Autonomi'}
STATUSES = {'PENDING': 'VENTER PÅ GODKJENNING', 'DEFERRED': 'UTSATT',
            'APPLIED': 'IVERKSATT', 'REJECTED': 'AVVIST', 'BLOCKED': 'BLOKKERT',
            'STALE': 'UTDATERT', 'ROLLED_BACK': 'TILBAKERULLERT'}
COOLDOWN_DAYS = 7
NEW_TRADES = 25
NEW_OBSERVATIONS = 20


def now():
    return datetime.now(timezone.utc)


def _storage():
    from services.storage_service import get_storage_service
    return get_storage_service()


def _metadata(doc):
    return doc.setdefault(META, {'proposals': [], 'history': [], 'blocked_parameters': []})


def snapshot():
    from autonomous_portfolio import load_parameters
    params = asdict(load_parameters())  # preserves legacy bootstrap/migration
    doc = _storage().read_json(KEY, params)
    return deepcopy({**params, **doc})


def _mutate(callback):
    initial = snapshot()
    def transform(raw):
        doc = deepcopy({**initial, **raw} if isinstance(raw, dict) else initial)
        callback(doc, _metadata(doc))
        return doc
    return _storage().mutate_json(KEY, transform, default=initial)


def evidence_snapshot(trades, observations, stats, drawdown):
    ids = sorted({str(t.get('trade_id') or hashlib.sha256(json.dumps(t, sort_keys=True, default=str).encode()).hexdigest()) for t in trades})
    mature = sorted({str(o.get('observation_id') or hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest())
                     for o in observations if any(int(m.get('horizon_days') or 0) in {20, 60} for m in o.get('outcome_measurements', []))})
    return {'trade_ids': ids, 'observation_ids': mature, 'closed_trades': len(ids),
            'mature_observations': len(mature), 'profit_factor': stats.get('profit_factor'),
            'expectancy': stats.get('expectancy'), 'drawdown_pct': drawdown,
            'dataset': 'Autonomi-produksjon + separate læringshandler (uten Paper)'}


def renewal_allowed(prior, evidence):
    """Variants must meet both cooldown and genuinely new evidence requirements."""
    if not prior:
        return True, ''
    old = prior.get('decision_evidence') or prior.get('evidence') or {}
    added_trades = len(set(evidence.get('trade_ids', [])) - set(old.get('trade_ids', [])))
    added_observations = len(set(evidence.get('observation_ids', [])) - set(old.get('observation_ids', [])))
    timestamp = prior.get('resolved_at') or prior.get('created_at')
    try:
        recorded = datetime.fromisoformat(timestamp)
        if recorded.tzinfo is None:
            recorded = recorded.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return False, ''
    elapsed = now() - recorded
    if elapsed < timedelta(days=COOLDOWN_DAYS) or (added_trades < NEW_TRADES and added_observations < NEW_OBSERVATIONS):
        return False, ''
    return True, (f"Tidligere avvist/tilbakerullet {timestamp[:10]}. "
                  f"Nå {added_trades} nye handler og {added_observations} nye modne observasjoner; "
                  f"PF {old.get('profit_factor')} → {evidence.get('profit_factor')}.")


def queue_proposal(parameter, before, after, reason, evidence):
    # Currently the risk engine authorizes proposals only for position sizing.
    if parameter != 'maximum_position_pct' or not math.isfinite(float(after)) or not 0.1 <= after <= 25 or after == before:
        raise ValueError('Ugyldig parameterforslag')
    result = {}
    def change(doc, meta):
        if parameter in meta['blocked_parameters']:
            return
        if float(doc.get(parameter, before)) != float(before):
            return
        for item in meta['proposals']:
            if item['parameter'] == parameter and item['status'] in {'PENDING', 'DEFERRED'}:
                if item['before'] == before:
                    if item['status'] == 'DEFERRED' and now() >= datetime.fromisoformat(item['deferred_until']):
                        item['status'] = 'PENDING'
                    result.update(item)
                    return
                item['status'] = 'STALE'
        prior = next((p for p in reversed(meta['proposals']) if p['parameter'] == parameter and p['status'] in {'REJECTED', 'ROLLED_BACK'}), None)
        allowed, renewed = renewal_allowed(prior, evidence)
        if not allowed:
            return
        item = {'proposal_id': 'AP-' + uuid.uuid4().hex[:12], 'parameter': parameter,
                'before': before, 'after': after, 'reason': reason, 'evidence': deepcopy(evidence),
                'renewed_reason': renewed, 'status': 'PENDING', 'created_at': now().isoformat(),
                'engine': 'AUTONOMI_PRODUKSJON', 'source': 'LEARNING_RISK_PROTECTION'}
        meta['proposals'].append(item)
        result.update(item)
    _mutate(change)
    return result or None


def _record(doc, meta, changes, actor, source, proposal_id=''):
    before = {key: doc.get(key) for key in changes}
    changes = {key: value for key, value in changes.items() if before[key] != value}
    if not changes:
        return
    doc.update(changes)
    from autonomous_portfolio import AutonomousParameters
    meta['approved_parameters'] = {k: doc[k] for k in AutonomousParameters.__dataclass_fields__}
    meta['approved_by'] = actor
    meta['history'].append({'change_id': 'PC-' + uuid.uuid4().hex[:12], 'timestamp': now().isoformat(),
                            'actor': actor, 'source': source, 'proposal_id': proposal_id,
                            'before': {k: before[k] for k in changes}, 'after': changes,
                            'status': 'APPLIED'})
    for item in meta['proposals']:
        if item['status'] in {'PENDING', 'DEFERRED'} and item['parameter'] in changes and item['proposal_id'] != proposal_id:
            item['status'] = 'STALE'


def save_manual(params, *, actor='USER', expected=None, source='MANUAL'):
    if not actor:
        raise PermissionError('Brukeridentitet mangler')
    values = asdict(params.normalized())
    def change(doc, meta):
        if expected is not None and any(doc.get(k, expected[k]) != expected[k] for k in expected):
            raise ValueError('Parameterne er endret siden siden ble åpnet. Oppdater før du lagrer.')
        _record(doc, meta, values, actor, source)
    result = _mutate(change)
    return result


def decide(proposal_id, decision, *, actor, confirmed=False):
    if not actor:
        raise PermissionError('Brukeridentitet mangler')
    if decision not in {'APPROVE', 'REJECT', 'DEFER', 'BLOCK'}:
        raise ValueError('Ukjent beslutning')
    if decision == 'APPROVE' and not confirmed:
        raise PermissionError('Bekreft den konkrete endringen før lagring')
    selected = {}
    def change(doc, meta):
        item = next((p for p in meta['proposals'] if p['proposal_id'] == proposal_id), None)
        if not item or item['status'] not in {'PENDING', 'DEFERRED'}:
            raise ValueError('Forslaget finnes ikke eller er allerede behandlet')
        if decision == 'APPROVE':
            if doc.get(item['parameter']) != item['before']:
                raise ValueError('Forslaget er utdatert. Parameteren er endret; oppdater siden.')
            _record(doc, meta, {item['parameter']: item['after']}, actor, 'LEARNING_APPROVAL', proposal_id)
            item['status'] = 'APPLIED'
        elif decision == 'DEFER':
            item['status'] = 'DEFERRED'
            item['deferred_until'] = (now() + timedelta(days=COOLDOWN_DAYS)).isoformat()
        else:
            item['status'] = 'REJECTED' if decision == 'REJECT' else 'BLOCKED'
            if decision == 'BLOCK' and item['parameter'] not in meta['blocked_parameters']:
                meta['blocked_parameters'].append(item['parameter'])
        item.update(resolved_by=actor, resolved_at=now().isoformat())
        selected.update(item)
    _mutate(change)
    return selected


def rollback(*, actor, confirmed=False, change_id=None):
    if not actor:
        raise PermissionError('Brukeridentitet mangler')
    if not confirmed:
        raise PermissionError('Bekreft rollback før lagring')
    result = {}
    def change(doc, meta):
        item = next((h for h in reversed(meta['history']) if h['status'] == 'APPLIED' and h['source'] != 'ROLLBACK'), None)
        if not item or (change_id and item['change_id'] != change_id):
            raise ValueError('Siste endring er endret eller mangler. Oppdater siden.')
        if any(doc.get(k) != v for k, v in item['after'].items()):
            raise ValueError('Nyere verdier finnes. Rollback ville overskrive dem.')
        _record(doc, meta, item['before'], actor, 'ROLLBACK')
        item['status'] = 'ROLLED_BACK'
        item['rolled_back_by'] = actor
        item['rolled_back_at'] = now().isoformat()
        for p in meta['proposals']:
            if p['proposal_id'] == item.get('proposal_id'):
                p.update(status='ROLLED_BACK', resolved_at=now().isoformat(), resolved_by=actor)
        result.update(item)
    _mutate(change)
    return result


def unblock(parameter, *, actor):
    if not actor:
        raise PermissionError('Brukeridentitet mangler')
    def change(doc, meta):
        meta['blocked_parameters'] = [p for p in meta['blocked_parameters'] if p != parameter]
        meta.setdefault('decisions', []).append({'parameter': parameter, 'decision': 'UNBLOCK', 'actor': actor, 'at': now().isoformat()})
    _mutate(change)


def actor_from_ui(st):
    user = st.session_state.get('auth_user') or {}
    return str(user.get('username') or user.get('email') or user.get('id') or 'USER')


def decide_from_ui(st, proposal_id, decision, confirmation_key):
    """Commit in Streamlit's callback, before costly page reads/rendering.

    The transaction remains authoritative; success is shown only after commit.
    Streamlit reruns automatically after a callback, so no nested rerun is needed.
    """
    try:
        result = decide(proposal_id, decision, actor=actor_from_ui(st),
                        confirmed=bool(st.session_state.get(confirmation_key)))
        st.session_state['autonomy_decision_feedback'] = ('success',
            f"{STATUSES[result['status']]} · {LABELS.get(result['parameter'], result['parameter'])}: "
            f"{result['before']:g} % → {result['after']:g} %")
    except (ValueError, PermissionError, RuntimeError) as exc:
        st.session_state['autonomy_decision_feedback'] = ('error', str(exc))


def render_decisions(st, namespace='autonomy_params'):
    feedback = st.session_state.pop('autonomy_decision_feedback', None)
    if feedback:
        getattr(st, feedback[0])(feedback[1])
    doc = snapshot()
    meta = _metadata(doc)
    pending = [p for p in meta['proposals'] if p['status'] in {'PENDING', 'DEFERRED'}]
    from controlled_parameter_learning import _read, APPROVALS_PATH
    champion_approvals = [p for p in _read(APPROVALS_PATH, []) if p.get('status') == 'PENDING']
    if not pending and not champion_approvals:
        return
    st.markdown('##### Krever beslutning')
    st.caption('Forslag endrer ingen verdier før du godkjenner. Gjelder Autonomi-produksjon.')
    for p in pending:
        key = namespace + p['proposal_id']
        label = LABELS.get(p['parameter'], p['parameter'])
        fmt = lambda n: f'{n:g}'.replace('.', ',') + ' %'
        st.warning(f"{STATUSES[p['status']]} · {label}: {fmt(p['before'])} → forslag {fmt(p['after'])} · "
                   f"kilde: {p['reason']} / PF {p['evidence'].get('profit_factor', '–')}")
        st.caption(p['evidence']['dataset'])
        if p.get('renewed_reason'):
            st.caption(p['renewed_reason'])
        deferred = p['status'] == 'DEFERRED' and now() < datetime.fromisoformat(p['deferred_until'])
        if deferred:
            st.caption('Utsettelse varer til ' + p['deferred_until'][:10] + '. Du kan fortsatt godkjenne eller avvise nå.')
        confirmed = st.checkbox(f"Bekreft: {label} endres fra {fmt(p['before'])} til {fmt(p['after'])}", key=key+'confirm')
        for decision, title in [('APPROVE', 'Godkjenn'), ('REJECT', 'Avvis nå'), ('DEFER', 'Utsett 7 dager')]:
            st.button(title, key=key+decision,
                      disabled=(decision == 'APPROVE' and not confirmed) or (decision == 'DEFER' and deferred),
                      on_click=decide_from_ui, args=(st, p['proposal_id'], decision, key+'confirm'))
        with st.expander('Ikke foreslå denne parameterendringen igjen'):
            block = st.checkbox('Blokker nye risikoforslag for maks posisjon i Autonomi', key=key+'block_confirm')
            if st.button('Blokker forslag', key=key+'BLOCK', disabled=not block):
                decide(p['proposal_id'], 'BLOCK', actor=actor_from_ui(st))
                st.rerun()

    if champion_approvals:
        from approval_governance_ui import render_approval_card
        for item in champion_approvals:
            st.warning('VENTER PÅ GODKJENNING · Champion-endring i Autonomi')
            render_approval_card({**item, 'approval_source': 'LEARNING'}, key_prefix=namespace+'_champion', compact=False)


def render_history(st):
    meta = _metadata(snapshot())
    st.markdown('##### Endringshistorikk og rollback – Autonomi')
    for parameter in meta['blocked_parameters']:
        if st.button('Tillat forslag igjen: ' + LABELS.get(parameter, parameter), key='unblock_'+parameter):
            unblock(parameter, actor=actor_from_ui(st)); st.rerun()
    for h in reversed(meta['history'][-20:]):
        changes = ' · '.join(f"{LABELS.get(k, k)}: {h['before'][k]} → {v}" for k, v in h['after'].items())
        st.write(f"{h['timestamp']} · {h['actor']} · {h['source']} · {STATUSES[h['status']]} · {changes}")
    latest = next((h for h in reversed(meta['history']) if h['status'] == 'APPLIED' and h['source'] != 'ROLLBACK'), None)
    if latest:
        confirmed = st.checkbox('Bekreft rollback av siste godkjente endring', key='rollback_confirm_'+latest['change_id'])
        if st.button('Rull tilbake siste godkjente endring', disabled=not confirmed, key='rollback_'+latest['change_id']):
            try:
                rollback(actor=actor_from_ui(st), confirmed=confirmed, change_id=latest['change_id']); st.rerun()
            except (ValueError, PermissionError, RuntimeError) as exc:
                st.error(str(exc))
    with st.expander('Forslagshistorikk'):
        for p in reversed(meta['proposals'][-30:]):
            st.write(f"{p['created_at']} · {LABELS.get(p['parameter'], p['parameter'])}: {p['before']} → {p['after']} · {STATUSES[p['status']]} · {p.get('resolved_by', '–')}")
