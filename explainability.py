from __future__ import annotations
from typing import Any, Dict, Mapping, List


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def explain_buy_decision(item: Mapping[str, Any] | None, decision: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    item = dict(item or {})
    decision = dict(decision or {})
    factors: List[Dict[str, Any]] = []
    candidates = [
        ('Momentum', item.get('momentum_score', item.get('momentum'))),
        ('Trend', item.get('trend_score', item.get('trend'))),
        ('Volum', item.get('volume_score', item.get('volume'))),
        ('Insider', item.get('insider_score', item.get('insider'))),
        ('Eierskap', item.get('ownership_score', item.get('ownership'))),
        ('Sentiment', item.get('sentiment_score', item.get('sentiment'))),
        ('Risiko', item.get('risk_score', item.get('risk'))),
        ('Volatilitet', item.get('volatility_score', item.get('volatility'))),
    ]
    for name, raw in candidates:
        if raw is None:
            continue
        value = _num(raw)
        negative = name in {'Risiko', 'Volatilitet'}
        contribution = -abs(value) if negative else value
        factors.append({'Faktor': name, 'Bidrag': round(contribution, 2), 'Råverdi': raw})
    factors.sort(key=lambda x: abs(float(x['Bidrag'])), reverse=True)
    confidence = int(_num(decision.get('confidence', item.get('confidence', item.get('score', 0)))))
    recommendation = str(decision.get('decision') or decision.get('recommendation') or item.get('recommendation') or 'UKJENT')
    return {
        'recommendation': recommendation,
        'confidence': confidence,
        'factors': factors,
        'summary': _summary(recommendation, confidence, factors),
    }


def explain_sell_decision(reason: str = '', context: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    context = dict(context or {})
    text = str(reason or '').lower()
    checks = [
        ('Trailing stop', bool(context.get('trailing_stop_triggered')) or 'trailing' in text),
        ('Stop-loss', bool(context.get('stop_loss_triggered')) or 'stop loss' in text or 'stop-loss' in text),
        ('Take-profit', bool(context.get('take_profit_triggered')) or 'take profit' in text or 'take-profit' in text),
        ('Hard SELL-signal', bool(context.get('hard_sell')) or 'sell signal' in text),
        ('Confidence-fall', bool(context.get('confidence_drop')) or 'confidence' in text),
        ('Manuell exit', bool(context.get('manual')) or 'manuell' in text),
        ('Timeout', bool(context.get('timeout')) or 'timeout' in text),
    ]
    active = [name for name, value in checks if value]
    return {'reason': reason or 'Ukjent', 'checks': [{'Årsak': name, 'Aktiv': value} for name, value in checks], 'active_reasons': active}


def _summary(recommendation: str, confidence: int, factors: List[Dict[str, Any]]) -> str:
    positive = [f["Faktor"] for f in factors if float(f['Bidrag']) > 0][:3]
    negative = [f["Faktor"] for f in factors if float(f['Bidrag']) < 0][:2]
    text = f"{recommendation} med confidence {confidence}."
    if positive:
        text += ' Viktigste positive bidrag: ' + ', '.join(positive) + '.'
    if negative:
        text += ' Viktigste motargumenter: ' + ', '.join(negative) + '.'
    return text


def render_explanation(title: str, explanation: Mapping[str, Any]) -> None:
    import streamlit as st
    st.markdown(f'#### {title}')
    if explanation.get('summary'):
        st.info(str(explanation.get('summary')))
    rows = explanation.get('factors') or explanation.get('checks') or []
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
