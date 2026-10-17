"""Safe, transparent display-only scale for market indicator mini-gauges."""
from __future__ import annotations
from math import isfinite

# VIX display bands are a provisional convention, not a validated trade signal.
DISPLAY_SCALES = {"vix": {"low": 10.0, "high": 40.0,
                          "boundaries": (15.0, 20.0, 30.0),
                          "method": "Veiledende VIX-soner: under 15, 15–20, 20–30, over 30; ikke handelssignal."},
                  "trend": {"low": -20.0, "high": 20.0,
                            "boundaries": (-10.0, -3.0, 0.0),
                            "method": "Veiledende trendsoner: under -10 %, -10 til -3 %, -3 til 0 %, over 0 %. Negativ avstand til 200-dagers snitt angir svakere trend, ikke automatisk salgsgrunnlag.",
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
    return {"status": "DISPLAY_ONLY", "label": ("Lav", "Moderat", "Høy", "Svært høy")[zone],
            "percent": round(max(0.0, min(100.0, 100*(x-lo)/(hi-lo))), 2),
            "method": str(spec.get("method") or "Veiledende visningsskala"),
            "reverse_risk": bool(spec.get("reverse_risk"))}
