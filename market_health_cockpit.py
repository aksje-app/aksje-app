"""Accessible, responsive, read-only SVG dashboard cards."""
from html import escape
from math import cos, sin, pi
from market_health_gauges import display_gauge

COLORS = ("#29bb85", "#e8bc36", "#f29a3f", "#ed5561")

def _polar(angle, radius=70):
    theta = pi * (1 - angle)
    return (90 + radius * cos(theta), 91 - radius * sin(theta))

def _arc(start, end):
    a = _polar(start)
    b = _polar(end)
    return f"M {a[0]:.2f} {a[1]:.2f} A 70 70 0 0 1 {b[0]:.2f} {b[1]:.2f}"

def historical_position(value, observations):
    """Relative historical position, not a risk judgement."""
    from math import isfinite
    try:
        x = float(value)
        values = [float(row["value"]) for row in (observations or []) if isinstance(row, dict)]
        values = [v for v in values if isfinite(v)]
        if not isfinite(x) or len(values) < 12 or max(values) <= min(values):
            return None
        return sum(v <= x for v in values) / len(values)
    except (ValueError, TypeError, KeyError):
        return None


def dial_svg(key, value, observations=None):
    gauge = display_gauge(key, value)
    rated = gauge["percent"] is not None
    # The neutral gauge is deliberately not a risk rating.
    if rated:
        segments = [(0, 1/6), (1/6, 1/3), (1/3, 2/3), (2/3, 1)]
        if gauge.get("reverse_risk"):
            segments = [(0, .25), (.25, .425), (.425, .5), (.5, 1)]
            palette = COLORS[::-1]
        else:
            palette = COLORS
        pos = gauge["percent"] / 100
        active = next((i for i, (a,b) in enumerate(segments) if a <= pos < b), 3)
        arcs = "".join(
            f'<path d="{_arc(a,b)}" stroke="{palette[i]}" stroke-width="{14 if i == active else 11}" '
            f'opacity="{1 if i == active else .42}" fill="none"/>'
            for i,(a,b) in enumerate(segments)
        )
        a,b = _polar(pos, 55)
        needle = f'<path d="M90 91 L{a:.2f} {b:.2f}" stroke="#f4fafc" stroke-width="3.5" stroke-linecap="round"/><circle cx="90" cy="91" r="4" fill="#f4fafc"/>'
    elif (position := historical_position(value, observations)) is not None:
        arcs = (f'<path d="{_arc(0,1)}" stroke="#527589" stroke-width="11" opacity=".46" fill="none"/>'
                f'<path d="{_arc(0,position)}" stroke="#5ac6da" stroke-width="13" fill="none"/>')
        a,b = _polar(position, 55)
        needle = f'<path d="M90 91 L{a:.2f} {b:.2f}" stroke="#f4fafc" stroke-width="3.5" stroke-linecap="round"/><circle cx="90" cy="91" r="4" fill="#f4fafc"/>'
    else:
        arcs = f'<path d="{_arc(0,1)}" stroke="#718899" opacity=".58" stroke-width="12" fill="none"/>'
        needle = ""
    label = escape(gauge["label"])
    return (f'<svg viewBox="0 0 180 100" role="img" aria-label="{label}" style="display:block;width:100%;max-width:154px;height:auto;margin:0 auto">'
            + arcs + needle + "</svg>")

def market_cards(cards):
    blocks=[]
    for card in cards:
        key=card["key"]
        name=escape(str(card["name"]))
        valid=bool(card.get("valid"))
        value=escape(str(card.get("label", "Mangler data")))
        gauge=display_gauge(key, card.get("value")) if valid else {"label":"Mangler data","percent":None}
        hist = historical_position(card.get("value"), card.get("observations")) if valid and gauge["percent"] is None else None
        svg=dial_svg(key, card.get("value"), card.get("observations")) if valid else dial_svg(key, None)
        status=escape("Historisk nivå – ikke risikoskår" if hist is not None else gauge["label"] if valid else card.get("status","Mangler data"))
        observed=escape(str(card.get("observed") or "Ingen kursobservasjon"))
        blocks.append(
            '<div class="mh-instrument" role="group" aria-label="'+name+'">'
            '<div class="mh-instrument-name">'+name+'</div>'
            +svg+
            '<div class="mh-instrument-value">'+value+'</div>'
            '<div class="mh-instrument-status">'+status+'</div>'
            '<div class="mh-instrument-time">'+observed+'</div>'
            '</div>'
        )
    css = """<style>
    .mh-cockpit-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:8px 0 16px}
    @media(min-width:900px){.mh-cockpit-grid{grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}
    .mh-instrument{min-width:0;box-sizing:border-box;border:1px solid #34536d;border-radius:13px;padding:11px 7px 10px;background:linear-gradient(155deg,#102d40,#081c30);text-align:center;color:#edf7fc;overflow:hidden}
    .mh-instrument-name{font-size:clamp(11px,1.4vw,14px);font-weight:700;line-height:1.25;min-height:2.5em;overflow-wrap:anywhere}
    .mh-instrument-value{font-size:clamp(14px,2.4vw,20px);font-weight:750;line-height:1.25;overflow-wrap:anywhere;margin-top:-2px}
    .mh-instrument-status{font-size:clamp(10px,1.3vw,12px);line-height:1.3;color:#c4d5df;margin-top:5px;min-height:1.3em}
    .mh-instrument-time{font-size:10px;color:#a1b6c4;line-height:1.3;margin-top:6px;overflow-wrap:anywhere}
    .mh-instrument svg{max-height:86px}
    @media(max-width:440px){.mh-instrument{padding:9px 5px}.mh-instrument svg{max-height:74px}}
    </style>"""
    return css+'<div class="mh-cockpit-grid">'+"".join(blocks)+'</div>'
