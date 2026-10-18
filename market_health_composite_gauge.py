"""Read-only top-of-page composite gauge.

The gauge remains neutral until externally validated calibration is available.
No calculation, guessed weights, or trading side effects.
"""
from html import escape
from math import isfinite

def composite_gauge(composite):
    model = composite if isinstance(composite, dict) else {}
    score = model.get("risk_score")
    approved = model.get("validated") is True and isinstance(score, (int, float)) and not isinstance(score, bool) and isfinite(score) and 0 <= score <= 100
    provisional = model.get("provisional") is True and isinstance(score, (int, float)) and not isinstance(score, bool) and isfinite(score) and 0 <= score <= 100 and model.get("validated") is False
    visible = approved or provisional
    value = float(score) if visible else None
    label = (f"{value:.1f} / 100 – FORELØPIG" if provisional else f"{value:.0f} / 100") if visible else "IKKE BEREGNET"
    detail = ("Likevektet oversikt over foreløpige risikosoner – IKKE historisk validert, ikke et handelssignal." if provisional else "Validert samlet risikovurdering, ikke et handelssignal." if approved else
              "14 markedsindikatorer er tilgjengelige, men samlet vektning og historisk kalibrering er ikke godkjent.")
    # Grey instrument without a pointer until the validation flag is true.
    if visible:
        from math import sin, cos, pi
        angle = pi * (1 - value / 100)
        x, y = 150 + 88 * cos(angle), 126 - 88 * sin(angle)
        pointer = f'<line x1="150" y1="126" x2="{x:.2f}" y2="{y:.2f}" stroke="#f4fafc" stroke-width="4" stroke-linecap="round"/><circle cx="150" cy="126" r="5" fill="#f4fafc"/>'
        sections = [("#21ab80",180,135),("#e5be43",135,90),("#eb9343",90,45),("#d75361",45,0)]
        def polar(deg):
            import math
            return (150+108*math.cos(math.radians(deg)),126-108*math.sin(math.radians(deg)))
        arcs = "".join(f'<path d="M {polar(a)[0]:.1f} {polar(a)[1]:.1f} A 108 108 0 0 1 {polar(b)[0]:.1f} {polar(b)[1]:.1f}" fill="none" stroke="{color}" stroke-width="17"/>' for color,a,b in sections)
    else:
        pointer = ""
        arcs = '<path d="M 42 126 A 108 108 0 0 1 258 126" fill="none" stroke="#718899" stroke-width="17"/>'
    return ('<section class="mh-composite" aria-label="Samlet markedstemperatur">'
            '<style>.mh-composite{max-width:720px;margin:14px auto;padding:17px 12px;border:1px solid #4b6b80;border-radius:17px;background:#0d293c;color:#eef6fb;text-align:center;box-sizing:border-box}'
            '.mh-composite-title{font-size:clamp(19px,4vw,25px);font-weight:750}'
            '.mh-composite-value{font-size:clamp(19px,4vw,24px);font-weight:750}'
            '.mh-composite-desc{font-size:13px;color:#ccdae5;max-width:520px;margin:8px auto;line-height:1.5}'
            '.mh-composite svg{display:block;width:100%;max-width:310px;margin:6px auto 0}</style>'
            '<div class="mh-composite-title">Samlet markedstemperatur</div>'
            '<svg viewBox="0 0 300 152" role="img" aria-label="Samlet temperatur: '+escape(label)+'">'+arcs+pointer+'</svg>'
            '<div class="mh-composite-value">'+escape(label)+'</div>'
            '<div class="mh-composite-desc">'+escape(detail)+'</div>'
            '<div class="mh-composite-desc">Grønn: lavere kalibrert risiko · Gul: moderat · Oransje: forhøyet · Rød: høy. '
            'Foreløpige soner ved foreløpig beregning; ikke dokumentert prediksjon.</div></section>')
