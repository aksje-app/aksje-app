from __future__ import annotations

import json
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

_METRICS_PATH = Path('storage/performance_metrics_v18676.json')
_SESSION: Dict[str, Any] = {'render_times': [], 'api_calls': {}, 'cache': {'hit': 0, 'miss': 0}, 'reruns': 0}


def _load_persisted() -> Dict[str, Any]:
    try:
        if _METRICS_PATH.exists():
            data = json.loads(_METRICS_PATH.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _persist() -> None:
    try:
        _METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {'updated_at': datetime.now().isoformat(timespec='seconds'), **_SESSION}
        _METRICS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass


def mark_rerun() -> None:
    _SESSION['reruns'] = int(_SESSION.get('reruns', 0) or 0) + 1


def record_api_call(source: str, elapsed_ms: float | None = None, ok: bool = True) -> None:
    source = str(source or 'unknown')
    row = _SESSION.setdefault('api_calls', {}).setdefault(source, {'count': 0, 'errors': 0, 'total_ms': 0.0})
    row['count'] += 1
    row['errors'] += 0 if ok else 1
    row['total_ms'] += float(elapsed_ms or 0.0)


def record_cache(hit: bool) -> None:
    key = 'hit' if hit else 'miss'
    _SESSION.setdefault('cache', {}).setdefault(key, 0)
    _SESSION['cache'][key] += 1


def record_render(name: str, elapsed_ms: float, detail: Dict[str, Any] | None = None) -> None:
    rows: List[Dict[str, Any]] = _SESSION.setdefault('render_times', [])
    rows.append({
        'timestamp': datetime.now().isoformat(timespec='seconds'),
        'panel': str(name or 'unknown'),
        'elapsed_ms': round(float(elapsed_ms or 0.0), 2),
        'detail': detail or {},
    })
    if len(rows) > 500:
        del rows[:-500]
    _persist()


@contextmanager
def measure(name: str, detail: Dict[str, Any] | None = None):
    started = time.perf_counter()
    try:
        yield
    finally:
        record_render(name, (time.perf_counter() - started) * 1000.0, detail=detail)


def snapshot() -> Dict[str, Any]:
    persisted = _load_persisted()
    rows = list(_SESSION.get('render_times') or persisted.get('render_times') or [])
    api = dict(_SESSION.get('api_calls') or persisted.get('api_calls') or {})
    cache = dict(_SESSION.get('cache') or persisted.get('cache') or {'hit': 0, 'miss': 0})
    total_cache = int(cache.get('hit', 0) or 0) + int(cache.get('miss', 0) or 0)
    by_panel: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        name = str(row.get('panel') or 'unknown')
        bucket = by_panel.setdefault(name, {'panel': name, 'runs': 0, 'total_ms': 0.0, 'max_ms': 0.0})
        ms = float(row.get('elapsed_ms') or 0.0)
        bucket['runs'] += 1
        bucket['total_ms'] += ms
        bucket['max_ms'] = max(bucket['max_ms'], ms)
    summary = []
    for bucket in by_panel.values():
        runs = max(1, int(bucket['runs']))
        summary.append({
            'Panel': bucket['panel'], 'Kjøringer': runs,
            'Snitt ms': round(bucket['total_ms'] / runs, 1),
            'Maks ms': round(bucket['max_ms'], 1),
        })
    summary.sort(key=lambda x: x['Snitt ms'], reverse=True)
    return {
        'render_times': rows,
        'panel_summary': summary,
        'api_calls': api,
        'cache': cache,
        'cache_hit_rate': round(100.0 * int(cache.get('hit', 0) or 0) / total_cache, 1) if total_cache else 0.0,
        'reruns': int(_SESSION.get('reruns', 0) or persisted.get('reruns', 0) or 0),
    }


def render_performance_dashboard() -> None:
    import streamlit as st
    data = snapshot()
    st.subheader('Performance Dashboard')
    st.caption('Måler render-tider, API-kall, cache og reruns. Profileringen endrer ikke tradinglogikk.')
    rows = data.get('panel_summary') or []
    slowest = rows[0] if rows else {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Målte renders', len(data.get('render_times') or []))
    c2.metric('Reruns', data.get('reruns', 0))
    c3.metric('Cache hit-rate', f"{data.get('cache_hit_rate', 0):.1f}%")
    c4.metric('Tregeste panel', slowest.get('Panel', '-'), f"{slowest.get('Snitt ms', 0)} ms" if slowest else None)
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info('Ingen render-målinger ennå. Åpne noen paneler og kom tilbake.')
    api_rows = []
    for source, row in (data.get('api_calls') or {}).items():
        count = int(row.get('count', 0) or 0)
        api_rows.append({'Kilde': source, 'Kall': count, 'Feil': row.get('errors', 0), 'Snitt ms': round(float(row.get('total_ms', 0) or 0) / max(1, count), 1)})
    if api_rows:
        st.markdown('#### API-kall')
        st.dataframe(api_rows, use_container_width=True, hide_index=True)
    with st.expander('Siste render-målinger', expanded=False):
        st.dataframe(list(reversed((data.get('render_times') or [])[-100:])), use_container_width=True, hide_index=True)
