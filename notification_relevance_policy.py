"""Structured notification relevance policy for opt-in Pushover senders."""

def classify(event):
    kind = str(event.get('category') or '').lower()
    if kind == 'currency':
        return 'exempt'
    if kind in ('candidate', 'ranking', 'observation', 'routine'):
        return 'in_app'
    if kind in ('buy_signal', 'sell_signal'):
        required = ('verified', 'requires_action', 'threshold_met')
        if all(event.get(key) is True for key in required) and event.get('ticker') and event.get('signal_id'):
            return 'send'
        return 'in_app'
    return 'legacy'
