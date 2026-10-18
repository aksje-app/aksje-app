"""Transparent display-only 0-100 composite using existing provisional bands.

NOT historically calibrated; only observed fresh readings, with no trading link.
"""
from datetime import datetime, timezone
from market_health_history import normalize
from market_health_gauges import DISPLAY_SCALES

# Four standalone commodity/FX prices are intentionally excluded from risk aggregation.
RISK_KEYS=("vix","trend","breadth","cape","equity_yield","credit","curve","us10y","us30y","ttf")
MIN_COVERAGE=8

def preliminary_composite(snapshot, *, now=None):
    now=now or datetime.now(timezone.utc)
    readings=(snapshot or {}).get("indicators",{})
    readings=readings if isinstance(readings,dict) else {}
    components={}
    missing=[]
    for key in RISK_KEYS:
        observation=normalize(key,readings.get(key),now=now)
        if observation is None or observation["status"]!="CURRENT":
            missing.append(key)
            continue
        spec=DISPLAY_SCALES[key]
        value=float(observation["value"])
        band=sum(value >= float(boundary) for boundary in spec["boundaries"])
        if spec.get("reverse_risk"):
            band=3-band
        components[key]={"risk_band":band,"value":value,"observed_at":observation["observed_at"]}
    if len(components)<MIN_COVERAGE:
        return {"validated":False,"provisional":False,"risk_score":None,
                "coverage":len(components),"required":MIN_COVERAGE,"missing":missing}
    score=round(100*sum(row["risk_band"] for row in components.values())/(3*len(components)),1)
    return {"validated":False,"provisional":True,"risk_score":score,
            "coverage":len(components),"required":MIN_COVERAGE,"missing":missing,
            "components":components,"method":"Likevektede foreløpige risikosoner, ikke historisk validert",
            "trade_signals_enabled":False}
