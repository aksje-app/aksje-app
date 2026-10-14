"""Presentation-only Superfond risk sorting and visual cues."""
from collections import Counter
from math import isfinite

PRIORITY={'STOPP':0,'NÆR STOPP':1,'ADVARSEL':2,'NORMAL':3}
COLORS={'STOPP':('#ff8189','#2c1921'),'NÆR STOPP':('#ffb07e','#302320'),
        'ADVARSEL':('#f4ce78','#302b1d'),'NORMAL':('#83d5b0','#182b29')}

def status_palette(status):
    return COLORS.get(str(status),('#c8d5e1','#202a36'))

def sorted_risk_positions(positions):
    def sort_key(item):
        try:
            drop=float(item.get('drop_from_peak_pct'))
            if not isfinite(drop): drop=-1
        except (TypeError,ValueError):
            drop=-1
        return (PRIORITY.get(item.get('stop_status'),4),-drop,str(item.get('name') or '').casefold())
    return sorted(positions,key=sort_key)

def risk_counts(positions):
    counts=Counter(p.get('stop_status') for p in positions)
    return {status:counts[status] for status in PRIORITY}
