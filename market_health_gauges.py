"""Safe, transparent display-only scale for market indicator mini-gauges."""
from __future__ import annotations
from math import isfinite

# VIX display bands are a provisional convention, not a validated trade signal.
DISPLAY_SCALES = {
                  "cape": {"low": 10.0, "high": 60.0, "boundaries": (20.0, 30.0, 40.0),
                           "method": "Foreløpige CAPE-verdsettelsessoner under 20, 20–29,99, 30–39,99 og fra 40. Langsiktig nivå, ikke tidsbestemt børsfall."},
                  "equity_yield": {"low": 0.5, "high": 7.0, "boundaries": (1.5, 2.5, 4.0),
                                   "reverse_risk": True,
                                   "method": "Årlig S&P500 aksjonærutbetalingsyield fra utbytter og tilbakekjøp relativt til indeksnivå; veiledende soner. Lav yield kan indikere høy verdsettelse, ikke handelssignal."},
                  "breadth": {"low": 0.0, "high": 100.0, "boundaries": (30.0, 45.0, 60.0),
                              "reverse_risk": True,
                              "method": "S&P500-andel over 200-dagers snitt; foreløpige soner under 30 %, 30–44,99 %, 45–59,99 %, fra 60 %. Ikke validert risikomodell."},
                  "ttf": {"low": 0.0, "high": 160.0, "boundaries": (40.0, 70.0, 100.0),
                          "method": "Foreløpige TTF-prisnivåsoner EUR/MWh: under 40, 40–69,99, 70–99,99, fra 100. Kontrakt/terminmåned påvirker prisen. Ikke handelsregel."},
                  "us10y": {"low": 3.0, "high": 6.0, "boundaries": (4.0, 4.75, 5.30),
                            "method": "Foreløpige rente-NIVÅsoner: under 4,00 %, 4,00–4,74 %, 4,75–5,29 %, fra 5,30 %. Ikke dokumentert aksjerisiko eller handelssignal."},
                  "us30y": {"low": 3.5, "high": 6.5, "boundaries": (4.5, 5.0, 5.5),
                            "method": "Foreløpige rente-NIVÅsoner: under 4,50 %, 4,50–4,99 %, 5,00–5,49 %, fra 5,50 %. Egen skala for 30 år; ikke handelssignal."},
                  "dxy": {"low": 90.0, "high": 115.0, "boundaries": (98.0, 103.0, 108.0),
                          "method": "Foreløpig dollarnivå: under 98, 98–102,99, 103–107,99, fra 108. Sterk dollar er ikke alltid negativt for aksjer."},
                  "brent": {"low": 60.0, "high": 160.0, "boundaries": (85.0, 105.0, 125.0),
                            "method": "Foreløpig oljenivå USD/fat: under 85, 85–104,99, 105–124,99, fra 125. Ikke kalibrert risiko; effekten varierer mellom sektorer."},
                  "gold": {"low": 3000.0, "high": 5500.0, "boundaries": (3800.0, 4300.0, 4800.0),
                           "method": "Foreløpig gullPRISnivå USD/oz: under 3800, 3800–4299, 4300–4799, fra 4800. Farge beskriver prisnivå, IKKE markedsrisiko."},
                  "eurusd": {"low": 0.95, "high": 1.30, "boundaries": (1.05, 1.12, 1.20),
                             "method": "Foreløpig kursnivå EUR/USD: under 1,05, 1,05–1,1199, 1,12–1,1999, fra 1,20. Farger viser kursnivå, IKKE risiko; DXY vektes ikke dobbelt."},
                  "vix": {"low": 10.0, "high": 40.0,
                          "boundaries": (15.0, 20.0, 30.0),
                          "method": "Veiledende VIX-soner: under 15, 15–20, 20–30, over 30; ikke handelssignal."},
                  "trend": {"low": -20.0, "high": 20.0,
                            "boundaries": (-10.0, -3.0, 0.0),
                            "method": "Veiledende trendsoner: under -10 %, -10 til -3 %, -3 til 0 %, over 0 %. Negativ avstand til 200-dagers snitt angir svakere trend, ikke automatisk salgsgrunnlag.",
                            "reverse_risk": True},
                  "credit": {"low": 2.0, "high": 10.0, "boundaries": (3.5, 5.0, 7.0),
                             "method": "Foreløpige HY-spreadsoner i prosentpoeng: under 3,5; 3,5–5; 5–7; over 7. Kun informativ visning, ikke validert varselsignal."},
                  "curve": {"low": -2.0, "high": 2.0, "boundaries": (-1.0, -0.25, 0.0),
                            "method": "Foreløpige kurvesoner i prosentpoeng. Inversjon alene sier ikke når en resesjon starter.",
                            "reverse_risk": True}}


def display_gauge(key, value, *, scale=None):
    spec = scale if isinstance(scale, dict) else DISPLAY_SCALES.get(key)
    if not spec:
        return {"status": "UNRATED", "label": "Skala ikke kalibrert", "percent": None}
    try:
        x = float(value)
        lo, hi = float(spec["low"]), float(spec["high"])
        boundaries = tuple(float(v) for v in spec["boundaries"])
        if not (isfinite(x) and isfinite(lo) and isfinite(hi) and lo < hi and
                len(boundaries) == 3 and lo < boundaries[0] < boundaries[1] < boundaries[2] < hi):
            raise ValueError("invalid scale")
    except (ValueError, TypeError, KeyError):
        return {"status": "UNRATED", "label": "Skala ikke kalibrert", "percent": None}
    zone = sum(x >= bound for bound in boundaries)
    if spec.get("reverse_risk"):
        zone = 3 - zone
    descriptive = key in ("dxy", "brent", "gold", "eurusd")
    labels = ("Lavt nivå", "Middels nivå", "Høyt nivå", "Svært høyt nivå") if descriptive else ("Lav", "Moderat", "Høy", "Svært høy")
    return {"status": "DISPLAY_ONLY", "label": labels[zone],
            "percent": round(max(0.0, min(100.0, 100*(x-lo)/(hi-lo))), 2),
            "method": str(spec.get("method") or "Veiledende visningsskala"),
            "reverse_risk": bool(spec.get("reverse_risk"))}
