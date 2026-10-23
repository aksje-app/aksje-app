"""Existing Autonomi upstream/learning, separate from the authoritative NOK book.

These are the same helpers used by ordinary legacy cycles. Per-job receipts make
normal retries idempotent. No main-account mirror, reset or strategy change.
Learning retains its existing canonical stores and independent notional model.
"""
from copy import deepcopy
from services.economic_opening import digest
from services import production_restart as control


def preparation_key(chosen,run_id):
    return 'autonomous_portfolio/nok_preparation/'+digest(dict(period=chosen['pointer']['period_id'],run_id=run_id))+'.json'


def prepare(chosen,run_id,candidates,*,storage=None):
    import autonomous_portfolio as ap
    from services.production_routing import view,strategy_settings
    storage=storage or control.get_storage_service()
    period=chosen['pointer']['period_id'];settings=strategy_settings('autonomy',storage=storage)
    source=dict(period=period,run_id=run_id,candidates=candidates,settings=settings)
    key=preparation_key(chosen,run_id)
    def mutation(current):
        if current:
            if current['source_sha256']!=digest(source):raise ValueError('Autonomy source job reused with different input')
            return current
        portfolio=view('autonomy',storage=storage)
        prepared,snapshot,parallel,technical=ap.prepare_cycle_candidates(deepcopy(candidates),portfolio,
            ap.AutonomousParameters(**settings).normalized(),run_id,lambda *a,**kw:None)
        return dict(source_sha256=digest(source),settings=settings,candidates=prepared,market_snapshot=snapshot,
            parallel_strategy_run=parallel,technical_contribution=technical,portfolio_before=portfolio)
    return storage.mutate_json(key,mutation)


def complete(chosen,run_id,prepared,portfolio,trades,decisions,*,storage=None):
    import autonomous_portfolio as ap
    from services.production_routing import strategy_settings
    storage=storage or control.get_storage_service();period=chosen['pointer']['period_id']
    key='autonomous_portfolio/nok_learning_receipts/'+digest(dict(period=period,run_id=run_id))+'.json'
    def mutation(current):
        if current:return current
        params=ap.AutonomousParameters(**prepared['settings']).normalized()
        candidates=prepared['candidates'];snapshot=prepared['market_snapshot']
        candidate_map={str(c['ticker']).upper():c for c in candidates}
        learning=ap.load_learning_portfolio()
        learning_decisions,learning_trades=ap._update_learning_positions(learning,candidate_map,run_id,params)
        exited={t['ticker'] for t in trades if t['action']=='SELL'}
        for trade in trades:
            if trade['action']=='BUY' and trade['ticker'] in learning.get('positions',{}):
                closed=ap._close_learning_position(learning,trade['ticker'],trade['price'],'Promotert til ordinær autonom portefølje',run_id)
                if closed:learning_trades.append(closed)
        if portfolio.get('status')=='ACTIVE':
            ld,lt=ap.open_learning_probes(params,portfolio,learning,candidates,trades,exited,run_id,snapshot)
            learning_decisions.extend(ld);learning_trades.extend(lt)
        learning.update(updated_at=ap._now(),last_run_id=run_id)
        ap._write(ap.LEARNING_PORTFOLIO_PATH,learning)
        observations=ap._update_candidate_observations(candidates,decisions+learning_decisions,run_id,snapshot)
        prior=ap._read(ap.LEARNING_DECISIONS_PATH,[]) or []
        existing={(r.get('run_id'),r.get('ticker'),r.get('action')) for r in prior}
        ap._record_learning_decisions([r for r in learning_decisions if (r.get('run_id'),r.get('ticker'),r.get('action')) not in existing])
        history=ap.load_learning_equity_history(2000)
        if not any(r.get('run_id')==run_id for r in history):
            ap._append_learning_equity_history(learning,run_id,trades=len(learning_trades),decisions=len(learning_decisions))
        performance=ap.learning_portfolio_performance(learning)
        ap._write(ap.LEARNING_PERFORMANCE_PATH,performance)
        # Canonical learning journal wins on a retry after an interrupted bridge.
        canonical={(t.get('run_id'),t.get('ticker'),t.get('action')):t for t in ap._read(ap.LEARNING_TRADES_PATH,[]) or []}
        learning_trades=[canonical.get((t.get('run_id'),t.get('ticker'),t.get('action')),t) for t in learning_trades]
        shared=ap.sync_learning_account(learning,learning_trades,learning_decisions,run_id)
        try:
            from learning_runtime import capture_autonomy
            capture_autonomy(candidates,parameters=__import__('dataclasses').asdict(params),run_id=run_id,portfolio_before=prepared['portfolio_before'])
        except Exception as exc:ap._append_audit('EXPERIMENT_CAPTURE_FAILED',{'run_id':run_id,'error':type(exc).__name__})
        return dict(run_id=run_id,period_id=period,learning_portfolio=learning,learning_trades=learning_trades,
            learning_decisions=learning_decisions,learning_observations=observations,learning_performance=performance,
            autonomy_learning_account=shared,primary_ledger='SELECTED_NOK_JOURNAL_NO_LEGACY_MIRROR')
    token=ap._NOK_LEARNING.set(True)
    try:return storage.mutate_json(key,mutation)
    finally:ap._NOK_LEARNING.reset(token)
