"""Durable 15-minute Fresh Trend follow-up for RC16.31cb.

The monitor is observational.  It refreshes only the bounded Fresh Trend queue;
it cannot change investment scores, BUY/risk gates, portfolios or orders.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import os
import threading
from contextlib import contextmanager
from typing import Any, Mapping, Sequence

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path

VERSION = "v19.22.0-rc16.31cg"
STATE_KEY = "fresh_trend/monitor_state.json"
STATE_PATH = runtime_data_path("fresh_trend", "monitor_state.json")
INTERVAL_MINUTES = 15
MAX_CANDIDATES = 12
FOLLOW_UP_SESSIONS = 5
_MONITOR_LOCK_ID = 1871531
_LOCAL_MONITOR_LOCK = threading.Lock()

# Only these market fields may change a Fresh Trend decision.  Runtime fields
# (scan time, report URL, formatting) are deliberately excluded so that the
# same market snapshot cannot oscillate between statuses or be notified twice.
_DECISION_FIELDS = (
    "last_price", "return_1d_pct", "return_3d_pct", "return_5d_pct",
    "volume_ratio_20", "breakout_hold_sessions", "breakout_20d",
    "breakout_holding", "prior_20d_high", "distance_from_20d_high_pct",
    "market_rs_5d_percentile", "sector_rs_5d_percentile",
    "market_rs_universe_count_5d", "sector_rs_universe_count_5d",
    "rs_reference_scope", "rs_full_stage1_universe",
    "momentum_acceleration_3v20", "rsi", "sma20",
    "latest_volume", "average_volume_20", "volume_bar_complete", "volume_time_adjusted",
)


def _f(value: Any) -> float | None:
    try:
        value = float(value)
        return value if value == value else None
    except Exception:
        return None


def _now(value: datetime | None = None) -> datetime:
    value = value or datetime.now(timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _business_days(start: date, end: date, market: str = "NORGE") -> int:
    if end < start:
        return 0
    market_key = str(market or "NORGE").upper()
    aliases = {"NORWAY": "NORGE", "SWEDEN": "SVERIGE", "UNITED STATES": "USA", "US": "USA"}
    market_key = aliases.get(market_key, market_key)
    try:
        from market_hours import MARKETS, mcal
        cfg = MARKETS.get(market_key)
        if cfg and mcal is not None:
            return int(len(mcal.get_calendar(cfg["calendar"]).schedule(start_date=start, end_date=end)))
    except Exception:
        pass
    days = 0
    cursor = start
    from datetime import timedelta
    while cursor <= end:
        if cursor.weekday() < 5:
            days += 1
        cursor += timedelta(days=1)
    return days


def _explicit_signal_id(receipt: Mapping[str, Any]) -> str:
    fs = receipt.get("fresh_signal") if isinstance(receipt.get("fresh_signal"), Mapping) else {}
    return str(fs.get("signal_id") or receipt.get("fresh_signal_id") or "").strip()


def _stabilize_progress(receipt: Mapping[str, Any], previous: Mapping[str, Any]) -> dict[str, Any]:
    """Make counters monotonic for the same signal, retaining raw values for audit."""
    row = dict(receipt)
    fs = dict(row.get("fresh_signal") or {}) if isinstance(row.get("fresh_signal"), Mapping) else {}
    prior_fs = previous.get("fresh_signal") if isinstance(previous.get("fresh_signal"), Mapping) else {}
    current_id, prior_id = _explicit_signal_id(row), _explicit_signal_id(previous)
    same_signal = not (current_id and prior_id and current_id != prior_id)
    try:
        raw_age = max(0, int(fs.get("trend_age_sessions") or row.get("trend_age_sessions") or 0))
    except (TypeError, ValueError):
        raw_age = 0
    try:
        prior_age = max(0, int(previous.get("signal_age_sessions") or prior_fs.get("trend_age_sessions") or 0))
    except (TypeError, ValueError):
        prior_age = 0
    effective_age = max(raw_age, prior_age) if same_signal else raw_age
    fs["reported_trend_age_sessions"] = raw_age
    fs["trend_age_sessions"] = effective_age
    row["fresh_signal"] = fs
    row["signal_age_sessions"] = effective_age

    try:
        raw_hold = max(0, int(row.get("breakout_hold_sessions") or 0))
    except (TypeError, ValueError):
        raw_hold = 0
    try:
        prior_hold = max(0, int(previous.get("breakout_hold_sessions") or 0))
    except (TypeError, ValueError):
        prior_hold = 0
    effective_hold = max(raw_hold, prior_hold) if same_signal and row.get("breakout_holding") and previous.get("breakout_holding") else raw_hold
    row["reported_breakout_hold_sessions"] = raw_hold
    row["breakout_hold_sessions"] = effective_hold
    row["signal_identity"] = current_id or prior_id or "IMPLICIT_CONTINUOUS"
    return row


def _due(state: Mapping[str, Any], now: datetime) -> bool:
    if os.getenv("FRESH_TREND_MONITOR_ENABLED", "true").lower() not in {"1", "true", "yes", "on"}:
        return False
    try:
        last = datetime.fromisoformat(str(state.get("last_scan_at") or "").replace("Z", "+00:00"))
        return (now - last.astimezone(timezone.utc)).total_seconds() >= INTERVAL_MINUTES * 60
    except Exception:
        return True


@contextmanager
def _monitor_execution_lock():
    """Cross-process advisory lock; simultaneous cron wakes cannot double-send."""
    connection = None
    acquired = False
    database_url = str(os.getenv("DATABASE_URL") or "").strip()
    try:
        if database_url:
            import psycopg2
            connection = psycopg2.connect(database_url, connect_timeout=5)
            cursor = connection.cursor()
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (_MONITOR_LOCK_ID,))
            acquired = bool(cursor.fetchone()[0])
        else:
            acquired = _LOCAL_MONITOR_LOCK.acquire(blocking=False)
        yield acquired
    finally:
        if connection is not None:
            try:
                if acquired:
                    cursor = connection.cursor()
                    cursor.execute("SELECT pg_advisory_unlock(%s)", (_MONITOR_LOCK_ID,))
                connection.close()
            except Exception:
                pass
        elif acquired:
            _LOCAL_MONITOR_LOCK.release()


def _components(receipt: Mapping[str, Any], previous: Mapping[str, Any] | None = None) -> dict[str, float]:
    fs = receipt.get("fresh_signal") if isinstance(receipt.get("fresh_signal"), Mapping) else {}
    score = float(_f(fs.get("score")) or 0.0)
    raw_vr = _f(receipt.get("volume_ratio_20"))
    volume_comparable = bool(receipt.get("volume_bar_complete") or receipt.get("volume_time_adjusted"))
    vr = float(raw_vr or 0.0) if volume_comparable else 0.0
    hold = int(receipt.get("breakout_hold_sessions") or 0)
    rs_is_partial = str(receipt.get("rs_reference_scope") or "").upper() == "PARTIAL_MONITOR_QUEUE"
    rs5 = 0.0 if rs_is_partial else float(_f(receipt.get("market_rs_5d_percentile")) or 0.0)
    rs_sector = 0.0 if rs_is_partial else float(_f(receipt.get("sector_rs_5d_percentile")) or 0.0)
    acceleration = float(_f(receipt.get("momentum_acceleration_3v20")) or 0.0)
    r3 = float(_f(receipt.get("return_3d_pct")) or 0.0)
    freshness = max(0.0, 100.0 - 12.0 * float(fs.get("trend_age_sessions") or 0))
    confirmation_hold = min(50.0, 25.0 * hold)
    confirmation_volume = min(50.0, 25.0 * min(vr, 2.0))
    confirmation_rs = 0.25 * (rs5 + rs_sector)
    confirmation = min(100.0, confirmation_hold + confirmation_volume + confirmation_rs)
    velocity = min(100.0, max(0.0, 45.0 + 12.0 * acceleration + 4.0 * r3))
    risk = 0.0
    rsi = _f(receipt.get("rsi"))
    if rsi is not None:
        risk += max(0.0, rsi - 68.0) * 3.0
    if volume_comparable and raw_vr is not None and raw_vr < 0.8:
        risk += 25.0
    if receipt.get("breakout_20d") and not receipt.get("breakout_holding"):
        risk += 25.0
    prior_components = (previous or {}).get("components") if isinstance((previous or {}).get("components"), Mapping) else {}
    previous_score = _f(prior_components.get("Fresh Score"))
    if previous_score is None:
        previous_score = _f((previous or {}).get("score"))
    # Migration from <= RC16.31cd: old state has no snapshot fingerprint and
    # may already contain a contradictory status (for example 95 -> 81 shown
    # as AKSELERERER). Recover the last distinct score once so the first CE
    # evaluation repairs that state. New CE snapshots use direct scan-to-scan
    # delta and therefore cannot replay the historical drop.
    if previous and not previous.get("snapshot_fingerprint") and previous_score == score:
        for value in reversed(list(previous.get("score_path") or [])[:-1]):
            candidate = _f(value)
            if candidate is not None and candidate != score:
                previous_score = candidate
                break
    return {"Freshness": round(freshness, 1), "Confirmation": round(confirmation, 1),
            "Confirmation hold": round(confirmation_hold, 1),
            "Confirmation volume": round(confirmation_volume, 1),
            "Confirmation RS": round(confirmation_rs, 1),
            "Velocity": round(velocity, 1), "Risk": round(min(100.0, risk), 1),
            "Fresh Score": round(score, 1), "Score delta": round(score - previous_score, 1) if previous_score is not None else 0.0}


def _data_timestamp(receipt: Mapping[str, Any]) -> str:
    freshness = receipt.get("data_freshness") if isinstance(receipt.get("data_freshness"), Mapping) else {}
    for value in (
        receipt.get("data_timestamp"), receipt.get("market_data_timestamp"),
        receipt.get("price_timestamp"), freshness.get("timestamp"),
    ):
        if value:
            return str(value)
    return ""


def _snapshot_fingerprint(receipt: Mapping[str, Any]) -> str:
    fs = receipt.get("fresh_signal") if isinstance(receipt.get("fresh_signal"), Mapping) else {}
    freshness = receipt.get("data_freshness") if isinstance(receipt.get("data_freshness"), Mapping) else {}
    payload = {key: receipt.get(key) for key in _DECISION_FIELDS}
    payload["ticker"] = str(receipt.get("ticker") or "").upper()
    payload["fresh_score"] = _f(fs.get("score"))
    payload["trend_age_sessions"] = fs.get("trend_age_sessions")
    # Fetch timestamps are audit metadata, not decision inputs. Including them
    # would make unchanged prices look like a new market state every 15 minutes.
    payload["data_status"] = str(freshness.get("status") or receipt.get("data_status") or "").upper()
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _data_is_decision_valid(receipt: Mapping[str, Any]) -> tuple[bool, str]:
    freshness = receipt.get("data_freshness") if isinstance(receipt.get("data_freshness"), Mapping) else {}
    status = str(freshness.get("status") or receipt.get("data_status") or "").strip().upper()
    invalid = {"", "UKJENT", "STALE", "UGYLDIG", "INVALID", "ERROR", "FEIL", "MISSING", "MANGLER", "UNAVAILABLE", "FORSINKET", "FORELDET"}
    if status in invalid:
        return False, f"Datastatus {status} kan ikke utløse en statusovergang"
    if _f(receipt.get("last_price")) is None:
        return False, "Mangler gyldig kurs"
    fs = receipt.get("fresh_signal") if isinstance(receipt.get("fresh_signal"), Mapping) else {}
    if _f(fs.get("score")) is None:
        return False, "Mangler gyldig Fresh Score"
    if str(receipt.get("rs_reference_scope") or "").upper() == "PARTIAL_MONITOR_QUEUE":
        return False, "RS bygger bare på overvåkingskøen, ikke avtalt fullscan"
    full_count = int(receipt.get("rs_full_stage1_universe") or 0)
    market_count = int(receipt.get("market_rs_universe_count_5d") or 0)
    if full_count > MAX_CANDIDATES and market_count <= MAX_CANDIDATES:
        return False, "For få gyldige aksjer i RS-markedsgrunnlaget"
    return True, "Gyldig beslutningssnapshot"


def _status(receipt: Mapping[str, Any], comp: Mapping[str, float], previous: Mapping[str, Any] | None) -> tuple[str, str]:
    score = comp["Fresh Score"]; delta = comp["Score delta"]
    last = _f(receipt.get("last_price")); prior_high = _f(receipt.get("prior_20d_high"))
    was_breakout = bool(receipt.get("breakout_20d") or (previous or {}).get("breakout_20d") or (previous or {}).get("breakout_holding"))
    false_breakout = bool(was_breakout and not receipt.get("breakout_holding") and last and prior_high and last < prior_high)
    if false_breakout or (score < 45 and str((previous or {}).get("status") or "") in {"AKSELERERER", "STERKT BEKREFTET"}):
        return "FALSKT BREAKOUT", "🔴"
    if delta <= -10 or comp["Velocity"] < 35:
        return "MISTER MOMENT", "🟠"
    if previous and delta < 0:
        return "AVVENTER BEKREFTELSE", "⚪"
    if score >= 85 and comp["Confirmation"] >= 65:
        return "STERKT BEKREFTET", "🟢"
    if score >= 65 and (delta >= 4 or (not previous and comp["Velocity"] >= 65)):
        return "AKSELERERER", "⚡"
    return ("AVVENTER BEKREFTELSE", "⚪") if previous else ("NYTT", "🆕")


def _apply_recovery_hysteresis(status: str, emoji: str, receipt: Mapping[str, Any],
                               comp: Mapping[str, float], previous: Mapping[str, Any]) -> tuple[str, str, int, bool]:
    """Prevent one neutral scan from reversing a negative Fresh Trend state."""
    negative = {"MISTER MOMENT", "FALSKT BREAKOUT"}
    if status in negative:
        return status, emoji, 0, True
    latched = bool(previous.get("negative_latch") or str(previous.get("status") or "") in negative)
    if not latched:
        return status, emoji, 0, False
    prior_comp = previous.get("components") if isinstance(previous.get("components"), Mapping) else {}
    confirmation_not_falling = float(comp.get("Confirmation") or 0) >= float(prior_comp.get("Confirmation") or 0)
    volume = float(_f(receipt.get("volume_ratio_20")) or 0.0)
    qualifies = bool(float(comp.get("Score delta") or 0) >= 4 and float(comp.get("Velocity") or 0) >= 65 and confirmation_not_falling and volume >= 0.8)
    streak = int(previous.get("recovery_confirmation_count") or 0) + 1 if qualifies else 0
    clear_recovery = bool(float(comp.get("Score delta") or 0) >= 8 and float(comp.get("Velocity") or 0) >= 70 and float(comp.get("Confirmation") or 0) >= 65 and volume >= 1.0)
    if clear_recovery or (qualifies and streak >= 2):
        return status, emoji, streak, False
    if not qualifies and str(previous.get("status") or "") in negative:
        prior_status = str(previous.get("status"))
        return prior_status, "🔴" if prior_status == "FALSKT BREAKOUT" else "🟠", 0, True
    return "AVVENTER BEKREFTELSE", "⚪", streak, True


def _status_reason(status: str, receipt: Mapping[str, Any], comp: Mapping[str, float]) -> str:
    delta = float(comp.get("Score delta") or 0.0)
    velocity = float(comp.get("Velocity") or 0.0)
    if status == "FALSKT BREAKOUT":
        return "Bruddet holder ikke, eller score har falt under sikkerhetsgrensen"
    if status == "MISTER MOMENT":
        return f"Kortsiktig svekkelse: scoreendring {delta:+.1f} og velocity {velocity:.0f}"
    if status == "STERKT BEKREFTET":
        return "Høy score med tilstrekkelig bekreftelse"
    if status == "AKSELERERER":
        return f"Kortsiktig fremdrift: scoreendring {delta:+.1f} og velocity {velocity:.0f}"
    if status == "AVVENTER BEKREFTELSE":
        return f"Blandet utvikling: scoreendring {delta:+.1f}; ny akselerasjon er ikke bekreftet"
    return "Nytt observasjonssignal som avventer bekreftelse"


def _pullback_retest(receipt: Mapping[str, Any]) -> dict[str, Any]:
    price = _f(receipt.get("last_price")); breakout = _f(receipt.get("prior_20d_high")); sma20 = _f(receipt.get("sma20"))
    reference = breakout or sma20
    distance = ((price / reference - 1.0) * 100.0) if price and reference else None
    detected = bool(distance is not None and -1.5 <= distance <= 2.0 and (receipt.get("breakout_20d") or receipt.get("breakout_holding")))
    held = bool(detected and price and reference and price >= reference)
    return {"detected": detected, "held": held, "reference": round(reference, 4) if reference else None,
            "distance_pct": round(distance, 2) if distance is not None else None,
            "label": "RETEST HOLDER" if held else "PULLBACK/RETEST" if detected else "INGEN RETEST"}


def _change_summary(receipt: Mapping[str, Any], previous: Mapping[str, Any]) -> dict[str, Any]:
    price = _f(receipt.get("last_price")); previous_price = _f(previous.get("last_price"))
    scan_amount = (price - previous_price) if price is not None and previous_price not in (None, 0) else None
    scan_pct = ((price / previous_price - 1.0) * 100.0) if price is not None and previous_price not in (None, 0) else None
    horizons = {}
    for days in (1, 3, 5):
        pct = _f(receipt.get(f"return_{days}d_pct"))
        baseline = (price / (1.0 + pct / 100.0)) if price is not None and pct is not None and (1.0 + pct / 100.0) != 0 else None
        horizons[str(days)] = {"pct": pct, "amount": (price - baseline) if price is not None and baseline is not None else None}
    current_components = receipt.get("components") if isinstance(receipt.get("components"), Mapping) else {}
    prior_components = previous.get("components") if isinstance(previous.get("components"), Mapping) else {}
    component_deltas = {name: round(float(current_components.get(name) or 0) - float(prior_components.get(name) or 0), 1)
                        for name in ("Confirmation", "Velocity", "Risk") if previous and name in prior_components}
    volume = _f(receipt.get("volume_ratio_20")); previous_volume = _f(previous.get("volume_ratio_20"))
    market_rs = _f(receipt.get("market_rs_5d_percentile")); prior_market_rs = _f(previous.get("market_rs_5d_percentile"))
    sector_rs = _f(receipt.get("sector_rs_5d_percentile")); prior_sector_rs = _f(previous.get("sector_rs_5d_percentile"))
    return {
        "scan_price_amount": round(scan_amount, 4) if scan_amount is not None else None,
        "scan_price_pct": round(scan_pct, 4) if scan_pct is not None else None,
        "horizons": horizons, "component_deltas": component_deltas,
        "volume_ratio": volume, "volume_ratio_delta": round(volume - previous_volume, 3) if volume is not None and previous_volume is not None else None,
        "market_rs_delta": round(market_rs - prior_market_rs, 1) if market_rs is not None and prior_market_rs is not None else None,
        "sector_rs_delta": round(sector_rs - prior_sector_rs, 1) if sector_rs is not None and prior_sector_rs is not None else None,
    }


def _direction(receipt: Mapping[str, Any], previous: Mapping[str, Any], comp: Mapping[str, float],
               changes: Mapping[str, Any], data_valid: bool) -> dict[str, Any]:
    if not data_valid:
        return {"score": None, "label": "UKJENT DATAGRUNNLAG", "icon": "⚫❓", "data_coverage": 0, "confidence": 0,
                "positive": [], "negative": ["Datagrunnlaget er ikke gyldig"]}
    values = []; positive = []; negative = []
    def add(value: float | None, pos: str, neg: str) -> None:
        if value is None: return
        values.append(float(value))
        if value >= 3: positive.append(pos)
        elif value <= -3: negative.append(neg)
    if receipt.get("breakout_20d") and not receipt.get("breakout_holding"):
        add(-25.0, "", "bruddet holder ikke")
    delta = float(comp.get("Score delta") or 0.0)
    add(max(-30, min(30, delta * 2.0)), f"score {delta:+.0f}", f"score {delta:+.0f}")
    if not previous:
        add(max(-15, min(15, (float(comp.get("Fresh Score") or 0) - 65) * .5)), "høy startscore", "lav startscore")
        add(max(-15, min(15, (float(comp.get("Velocity") or 0) - 50) * .4)), "høy velocity", "lav velocity")
        add(max(-8, min(8, (float(comp.get("Confirmation") or 0) - 50) * .3)), "god bekreftelse", "svak bekreftelse")
    if receipt.get("negative_latch"):
        add(-30.0, "", "momenttap er ikke gjenbekreftet")
    scan_pct = _f(changes.get("scan_price_pct"))
    add(max(-25, min(25, scan_pct * 15.0)) if scan_pct is not None else None, "kurs opp siden sist", "kurs ned siden sist")
    cd = changes.get("component_deltas") if isinstance(changes.get("component_deltas"), Mapping) else {}
    vd = _f(cd.get("Velocity")); add(max(-15, min(15, vd)) if vd is not None else None, "velocity øker", "velocity faller")
    confd = _f(cd.get("Confirmation")); add(max(-10, min(10, confd * .7)) if confd is not None else None, "bekreftelse øker", "bekreftelse faller")
    volume = _f(receipt.get("volume_ratio_20")); volume_delta = _f(changes.get("volume_ratio_delta"))
    volume_comparable = bool(receipt.get("volume_bar_complete") or receipt.get("volume_time_adjusted"))
    add(max(-15, min(15, (volume - 1.0) * 20.0)) if volume_comparable and volume is not None else None, "sterkt volum", "svakt volum")
    add(max(-8, min(8, volume_delta * 20.0)) if volume_comparable and volume_delta is not None else None, "volum bygger seg opp", "volum svekkes")
    rs_delta = _f(changes.get("market_rs_delta")) if str(receipt.get("rs_reference_scope") or "") != "PARTIAL_MONITOR_QUEUE" else None
    add(max(-10, min(10, rs_delta * .4)) if rs_delta is not None else None, "RS mot markedet styrkes", "RS mot markedet svekkes")
    if receipt.get("breakout_holding"):
        add(8.0, "brudd/retest holder", "")
    horizons = changes.get("horizons") if isinstance(changes.get("horizons"), Mapping) else {}
    h3 = _f((horizons.get("3") or {}).get("pct")); h5 = _f((horizons.get("5") or {}).get("pct"))
    add(max(-8, min(8, (h3 or 0) * .8 + (h5 or 0) * .5)) if h3 is not None or h5 is not None else None, "positiv 3–5d kursutvikling", "negativ 3–5d kursutvikling")
    score = round(max(-100.0, min(100.0, sum(values))), 1)
    if score >= 60: icon, label = "🟢⬆️", "STERKT OPP"
    elif score >= 20: icon, label = "🟢↗️", "OPP"
    elif score > -20: icon, label = "⚪➡️", "SIDELENGS / AVVENT"
    elif score > -60: icon, label = "🟠↘️", "SVEKKES"
    else: icon, label = "🔴⬇️", "STERKT NED"
    coverage = min(100, round(len(values) / 9.0 * 100))
    return {"score": score, "label": label, "icon": icon, "data_coverage": coverage, "confidence": coverage,
            "positive": positive[:3], "negative": negative[:3]}


def _fmt_signed(value: Any, decimals: int = 2, suffix: str = "") -> str:
    number = _f(value)
    return "-" if number is None else f"{number:+.{decimals}f}{suffix}"


def _message(row: Mapping[str, Any]) -> tuple[str, str]:
    raw_path = [round(float(x), 1) for x in row.get("score_path", [])]
    compact_path = [value for index, value in enumerate(raw_path) if index == 0 or value != raw_path[index - 1]]
    path = " → ".join(f"{value:.1f}" for value in compact_path)
    if len(raw_path) > 1 and len(compact_path) == 1:
        path = f"{compact_path[0]:.1f} (stabil, {len(raw_path)} målinger)"
    c = row.get("components") or {}; retest = row.get("pullback_retest") or {}
    fs = row.get("fresh_signal") if isinstance(row.get("fresh_signal"), Mapping) else {}
    cautions = [str(x) for x in (fs.get("cautions") or []) if x]
    signals = [str(x.get("label") or "") for x in (fs.get("signals") or []) if isinstance(x, Mapping) and x.get("label")]
    price = _f(row.get("last_price")); levels = row.get("action_levels") if isinstance(row.get("action_levels"), Mapping) else {}
    changes = row.get("changes") if isinstance(row.get("changes"), Mapping) else {}; direction = row.get("direction") if isinstance(row.get("direction"), Mapping) else {}
    horizons = changes.get("horizons") if isinstance(changes.get("horizons"), Mapping) else {}
    action = "Avvent en ny gyldig måling"
    if row.get("status") == "STERKT BEKREFTET": action = "Vurder manuelt mot ordinære kjøps- og risikoporter"
    elif row.get("status") == "AKSELERERER": action = "Følg volum og brudd/retest i neste 15-min scan"
    elif row.get("status") == "AVVENTER BEKREFTELSE": action = "Avvent: krev score +4, volum ≥0.80x og ny bekreftelse"
    elif row.get("status") in {"MISTER MOMENT", "FALSKT BREAKOUT"}: action = "Ikke jag; krev to forbedrede målinger før oppgradering"
    title = f"{row.get('emoji','⚫❓')} Fresh Trend: {row.get('status','UKJENT')}"
    name = str(row.get("company_name") or row.get("name") or "").strip()
    if len(name) > 72:
        name = name[:69].rsplit(" ", 1)[0] + "…"
    identity = f"{row.get('ticker')} · {name}" if name else str(row.get("ticker") or "-")
    exchange = str(row.get("exchange_name") or row.get("exchange") or "Ukjent børs")
    country = str(row.get("country") or "Ukjent land")
    freshness = row.get("data_freshness") if isinstance(row.get("data_freshness"), Mapping) else {}
    cd = changes.get("component_deltas") if isinstance(changes.get("component_deltas"), Mapping) else {}
    def horizon(days: str) -> str:
        item = horizons.get(days) if isinstance(horizons.get(days), Mapping) else {}
        return f"{days}d {_fmt_signed(item.get('amount'),2,' kr')}/{_fmt_signed(item.get('pct'),2,'%')}"
    volume = _f(row.get("volume_ratio_20")); volume_delta = _f(changes.get("volume_ratio_delta"))
    volume_text = f"{volume:.2f}x av 20d dagsnitt" if volume is not None else "mangler"
    if volume_delta is not None: volume_text += f" ({volume_delta:+.2f}x siden sist)"
    latest_volume = _f(row.get("latest_volume")); turnover = latest_volume * price if latest_volume is not None and price is not None else None
    if latest_volume is not None: volume_text += f" · {latest_volume:,.0f} aksjer"
    if turnover is not None: volume_text += f"/{turnover/1_000_000:.1f}m kr"
    market_rs = _f(row.get("market_rs_5d_percentile")); sector_rs = _f(row.get("sector_rs_5d_percentile"))
    market_count = int(row.get("market_rs_universe_count_5d") or 0); sector_count = int(row.get("sector_rs_universe_count_5d") or 0)
    rs_scope = str(row.get("rs_reference_scope") or "UKJENT")
    full_count = int(row.get("rs_full_stage1_universe") or 0)
    scope_label = "fullscan" if rs_scope == "FULL_STAGE1_UNIVERSE" else "delutvalg"
    rs_text = (f"marked: bedre enn {market_rs:.1f}% av {market_count} gyldige"
               f" ({scope_label}{f' av {full_count}' if full_count else ''})") if market_rs is not None else "marked -"
    if changes.get("market_rs_delta") is not None: rs_text += f" ({float(changes['market_rs_delta']):+.1f})"
    rs_text += f" · sektor: bedre enn {sector_rs:.1f}% av {sector_count}" if sector_rs is not None else " · sektor -"
    if changes.get("sector_rs_delta") is not None: rs_text += f" ({float(changes['sector_rs_delta']):+.1f})"
    age_seconds = freshness.get("age_seconds"); age_text = f"{max(0,int(age_seconds))//60} min gammel" if age_seconds is not None else "alder ukjent"
    breakout = _f(levels.get("breakout_level")); invalidation = _f(levels.get("invalidation_level")); target = _f(levels.get("first_target"))
    level_text = f"Inngang/retest {breakout:.2f}" if breakout is not None else "Inngang/retest -"
    if price is not None and breakout not in (None,0): level_text += f" · {(price-breakout):+.2f} kr/{(price/breakout-1)*100:+.2f}%"
    if invalidation is not None: level_text += f" · ugyldig under {invalidation:.2f}"
    if target is not None: level_text += f" · mål {target:.2f}"
    if price is not None and invalidation not in (None,0) and target not in (None,0):
        level_text += f" · ned {(invalidation-price):+.2f}/{(invalidation/price-1)*100:+.2f}% · opp {(target-price):+.2f}/{(target/price-1)*100:+.2f}%"
    risk_reasons = []
    volume_comparable = bool(row.get("volume_bar_complete") or row.get("volume_time_adjusted"))
    if volume_comparable and volume is not None and volume < .8: risk_reasons.append("svakt volum +25")
    elif volume is not None and not volume_comparable: risk_reasons.append("pågående volumbar: ingen negativ poengføring")
    rsi = _f(row.get("rsi"))
    if rsi is not None and rsi > 68: risk_reasons.append(f"RSI {rsi:.0f} +{max(0,(rsi-68)*3):.0f}")
    if row.get("breakout_20d") and not row.get("breakout_holding"): risk_reasons.append("bruddsvikt +25")
    drivers = "; ".join(direction.get("positive") or []) or "ingen tydelig positiv driver"
    brakes = "; ".join(direction.get("negative") or []) or (cautions[0] if cautions else "ingen ny negativ driver")
    interval = changes.get("scan_interval_minutes")
    since_label = f"siden sist ({int(interval)} min)" if interval is not None else "siden sist"
    body = (f"Oppsettstatus: {row.get('status')}\n"
            f"Retning nå: {direction.get('icon','⚫❓')} {direction.get('label','UKJENT')} ({direction.get('score','-')}) · datadekning {direction.get('data_coverage', direction.get('confidence',0))}%\n"
            f"Handling: {action}\n"
            f"{identity} · {exchange} · {country}\nOppfølging børsdag {row.get('follow_up_session','-')}/{FOLLOW_UP_SESSIONS} · signalalder {fs.get('trend_age_sessions', row.get('trend_age_sessions','-'))} økter\n"
            + (f"Kurs {price:.2f}" if price is not None else "Kurs -"))
    body += f" · {since_label} {_fmt_signed(changes.get('scan_price_amount'),2,' kr')}/{_fmt_signed(changes.get('scan_price_pct'),2,'%')}\n"
    body += f"{horizon('1')} · {horizon('3')} · {horizon('5')}\nScore {path} · sist {float(c.get('Score delta') or 0):+.1f}\n"
    body += f"Conf {float(c.get('Confirmation') or 0):.0f} ({float(cd.get('Confirmation') or 0):+.0f}) · Vel {float(c.get('Velocity') or 0):.0f} ({float(cd.get('Velocity') or 0):+.0f}) · Risk {float(c.get('Risk') or 0):.0f} ({', '.join(risk_reasons) or 'ingen tillegg'})\n"
    volume_basis = str(row.get("volume_comparison_basis") or "dagsvolum mot ferdige 20d-dager; ikke tidsjustert")
    body += f"Volum {volume_text} · basis {volume_basis}\nRS 5d {rs_text}\n{level_text} · {retest.get('label')}\n"
    body += f"Hovedstatus: {row.get('status_reason') or '-'}\nBakgrunnssignal: {'; '.join(signals[:2]) or fs.get('label') or '-'}\n"
    observed = freshness.get('observed_timestamp') or '-'
    body += f"+ {drivers}\n− {brakes}\nData: {freshness.get('status','UKJENT')} · hentet {freshness.get('fetched_at') or freshness.get('timestamp') or '-'} · bar {observed} · {age_text}\n{VERSION}"
    from notifier import fit_pushover_message
    body = fit_pushover_message(body, required_tail=f"Data: {freshness.get('status','UKJENT')} · {age_text}\n{VERSION}")
    return title, body


def monitor_receipts(receipts: Sequence[Mapping[str, Any]], *, now: datetime | None = None,
                     state: Mapping[str, Any] | None = None, notify: bool = True) -> dict[str, Any]:
    """Evaluate refreshed receipts and persist/notify meaningful transitions."""
    now = _now(now)
    loaded_state = read_json(STATE_KEY, STATE_PATH, {}) if state is None else state
    current = dict(loaded_state or {})
    tracked = dict(current.get("tracked") or {}); alerts = []; rows = []; seen_tickers = set()
    for receipt in list(receipts)[:MAX_CANDIDATES]:
        ticker = str(receipt.get("ticker") or "").upper()
        if not ticker or ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)
        previous = tracked.get(ticker) if isinstance(tracked.get(ticker), Mapping) else {}
        receipt = _stabilize_progress(receipt, previous)
        snapshot_fingerprint = _snapshot_fingerprint(receipt)
        previous_fingerprint = str(previous.get("snapshot_fingerprint") or "")
        unchanged_snapshot = bool(previous_fingerprint and snapshot_fingerprint == previous_fingerprint)
        data_valid, data_validation_reason = _data_is_decision_valid(receipt)
        first = str(previous.get("first_seen_at") or now.isoformat(timespec="seconds"))
        try: first_date = datetime.fromisoformat(first.replace("Z", "+00:00")).date()
        except Exception: first_date = now.date()
        market = receipt.get("market") or receipt.get("country") or "NORGE"
        session = max(_business_days(first_date, now.date(), str(market)), int(previous.get("follow_up_session") or 0))
        if session > FOLLOW_UP_SESSIONS:
            continue
        comp = _components(receipt, previous); status, emoji = _status(receipt, comp, previous)
        recovery_count = int(previous.get("recovery_confirmation_count") or 0)
        negative_latch = bool(previous.get("negative_latch"))
        if not unchanged_snapshot and data_valid:
            status, emoji, recovery_count, negative_latch = _apply_recovery_hysteresis(status, emoji, receipt, comp, previous)
        # An identical market snapshot is immutable: preserve the previous
        # decision and do not manufacture another score-path observation.
        if (unchanged_snapshot or not data_valid) and previous.get("status"):
            status = str(previous.get("status"))
            emoji = str(previous.get("emoji") or {"MISTER MOMENT": "🟠", "FALSKT BREAKOUT": "🔴", "STERKT BEKREFTET": "🟢", "AKSELERERER": "⚡"}.get(status, "🆕"))
            scores = list(previous.get("score_path") or [comp["Fresh Score"]])[-8:]
        else:
            scores = list(previous.get("score_path") or [])[-7:] + [comp["Fresh Score"]]
        status_reason = (str(previous.get("status_reason") or "") if unchanged_snapshot else "") or _status_reason(status, receipt, comp)
        row = {**dict(receipt), "monitor_version": VERSION, "first_seen_at": first,
               "last_scan_at": now.isoformat(timespec="seconds"), "follow_up_session": session,
               "components": comp, "score_path": scores[-8:], "status": status, "emoji": emoji,
               "status_reason": status_reason,
               "recovery_confirmation_count": recovery_count,
               "negative_latch": negative_latch,
               "data_timestamp": _data_timestamp(receipt),
               "snapshot_fingerprint": snapshot_fingerprint,
               "snapshot_unchanged": unchanged_snapshot,
               "decision_data_valid": data_valid,
               "decision_validation_reason": data_validation_reason,
               "pullback_retest": _pullback_retest(receipt)}
        changes = _change_summary(row, previous)
        try:
            prior_scan = datetime.fromisoformat(str(previous.get("last_scan_at") or "").replace("Z", "+00:00"))
            changes["scan_interval_minutes"] = max(0, round((now - prior_scan.astimezone(timezone.utc)).total_seconds() / 60))
        except Exception:
            changes["scan_interval_minutes"] = None
        direction = _direction(row, previous, comp, changes, data_valid)
        if unchanged_snapshot and isinstance(previous.get("changes"), Mapping):
            changes = dict(previous.get("changes") or {})
        if unchanged_snapshot and isinstance(previous.get("direction"), Mapping):
            direction = dict(previous.get("direction") or {})
        row["changes"] = changes
        row["direction"] = direction
        # A positive transition word must never be paired with a negative
        # aggregate direction. Strongly confirmed describes the setup level,
        # while its separate direction may legitimately be sideways.
        if status == "AKSELERERER" and _f(direction.get("score")) is not None and float(direction["score"]) <= 0:
            status, emoji = "AVVENTER BEKREFTELSE", "⚪"
            row["status"] = status
            row["emoji"] = emoji
            row["status_reason"] = _status_reason(status, row, comp)
        invariant_errors = []
        if int(row.get("signal_age_sessions") or 0) < int(previous.get("signal_age_sessions") or 0):
            invariant_errors.append("SIGNAL_AGE_DECREASED")
        if status in {"MISTER MOMENT", "FALSKT BREAKOUT"} and float(_f(direction.get("score")) or 0) >= 20:
            invariant_errors.append("NEGATIVE_STATUS_WITH_POSITIVE_DIRECTION")
        if status == "AKSELERERER" and float(_f(direction.get("score")) or 0) <= 0:
            invariant_errors.append("ACCELERATING_WITH_NONPOSITIVE_DIRECTION")
        row["invariant_errors"] = invariant_errors
        initial_price = _f(previous.get("initial_price")) or _f(receipt.get("last_price"))
        row["initial_price"] = initial_price
        outcomes = list(previous.get("signal_outcomes") or [])
        measured_days = {int(item.get("horizon_days") or 0) for item in outcomes if isinstance(item, Mapping)}
        current_price = _f(receipt.get("last_price"))
        for horizon in (1, 3, 5):
            if session >= horizon and horizon not in measured_days and initial_price and current_price:
                outcomes.append({
                    "horizon_days": horizon, "measured_at": now.isoformat(timespec="seconds"),
                    "entry_price": round(initial_price, 4), "price": round(current_price, 4),
                    "return_pct": round((current_price / initial_price - 1.0) * 100.0, 4),
                    "status": status, "score": comp["Fresh Score"],
                })
        row["signal_outcomes"] = outcomes
        previous_status = str(previous.get("status") or "")
        meaningful = data_valid and not invariant_errors and (not unchanged_snapshot) and (not previous_status or status != previous_status or abs(comp["Score delta"]) >= 10)
        if meaningful:
            title, body = _message(row); event = {"ticker": ticker, "status": status, "title": title, "message": body, "sent": False}
            if notify:
                from notifier import normalize_notification_result, send_pushover_alert
                report_url = str(row.get("report_url") or row.get("public_report_url") or "")
                ok, detail = normalize_notification_result(send_pushover_alert(
                    body, title=title, url=report_url or None,
                    url_title="Åpne siste rapportdetaljer" if report_url else None,
                ))
                event.update({"sent": ok, "detail": detail})
            alerts.append(event)
        tracked[ticker] = row; rows.append(row)
    missed = []
    active = {str(r.get("ticker") or "").upper() for r in rows}
    for ticker, old in tracked.items():
        if ticker in active or not isinstance(old, Mapping):
            continue
        peak = max([float(x) for x in old.get("score_path") or [0]])
        if peak >= 65 and not old.get("missed_opportunity_recorded"):
            missed.append({"ticker": ticker, "peak_fresh_score": peak, "last_status": old.get("status"),
                           "reason": "Forlot Fresh Trend-køen uten kjøpshandling; mål etterfølgende 5/20-dagers utfall.",
                           "recorded_at": now.isoformat(timespec="seconds")})
            tracked[ticker] = {**dict(old), "missed_opportunity_recorded": True}
    result = {"version": VERSION, "state": "COMPLETED", "last_scan_at": now.isoformat(timespec="seconds"),
              "interval_minutes": INTERVAL_MINUTES, "follow_up_sessions": FOLLOW_UP_SESSIONS,
              "tracked": tracked, "watchlist": rows, "alerts": alerts,
              "unchanged_count": max(0, len(rows) - len(alerts)),
              "notification_policy": "Kun ny status eller vesentlig scoreendring varsles; uendrede kandidater logges samlet.",
              "missed_opportunities": list(current.get("missed_opportunities") or [])[-250:] + missed,
              "production_scoring_changed": False, "trade_authority": False}
    write_json(STATE_KEY, STATE_PATH, result)
    return result


def _run_due_monitor_unlocked(*, now: datetime | None = None, notify: bool = True) -> dict[str, Any]:
    now = _now(now); state = read_json(STATE_KEY, STATE_PATH, {}) or {}
    if not _due(state, now):
        return {"state": "NOT_DUE", "last_scan_at": state.get("last_scan_at"), "interval_minutes": INTERVAL_MINUTES}
    latest = read_json("market_intelligence/latest_run.json", runtime_data_path("market_intelligence", "latest_run.json"), {}) or {}
    discovery = latest.get("trend_discovery") if isinstance(latest.get("trend_discovery"), Mapping) else {}
    receipts = [dict(x) for x in discovery.get("fresh_trend_watchlist") or [] if isinstance(x, Mapping)][:MAX_CANDIDATES]
    report_url = str(latest.get("report_url") or (latest.get("notification") or {}).get("report_url") or "")
    if report_url:
        for receipt in receipts:
            receipt["report_url"] = report_url
    if not receipts:
        result = {**dict(state), "state": "NO_CANDIDATES", "last_scan_at": now.isoformat(timespec="seconds")}
        write_json(STATE_KEY, STATE_PATH, result); return result
    # Refresh the small monitored queue only. The ordinary report retains its full 294/294 stage-1 scan.
    try:
        from candidate_market_data import enrich_candidate_rows
        from trend_intelligence import annotate_run
        # Keep prior receipt metadata at top level so the forced live
        # enrichment can overwrite market fields. A nested ``raw`` copy would
        # win in trend_intelligence._source and silently restore stale values.
        seeds = [{**dict(r), "ticker": r.get("ticker"), "market": r.get("market"),
                  "sector": r.get("sector"), "exchange_name": r.get("exchange_name")} for r in receipts]
        refreshed = enrich_candidate_rows(seeds, max_workers=min(4, len(seeds)), force_refresh=True)
        authoritative_rs = {
            str(row.get("ticker") or "").upper(): {key: row.get(key) for key in (
                "market_rs_5d_percentile", "market_rs_20d_percentile", "market_rs_60d_percentile",
                "sector_rs_5d_percentile", "sector_rs_20d_percentile",
                "market_rs_universe_count_5d", "sector_rs_universe_count_5d",
                "rs_reference_scope", "rs_full_stage1_universe", "rs_reference_at",
            )} for row in receipts
        }
        temp = {"markets": latest.get("markets") or ["Norge"], "candidates": refreshed, "fresh_screening_candidates": refreshed}
        annotate_run(temp, {})
        receipts = list((temp.get("trend_discovery") or {}).get("fresh_trend_watchlist") or receipts)
        full_stage1 = int((discovery.get("coverage") or {}).get("full_stage1_universe") or 0)
        for receipt in receipts:
            prior_rs = authoritative_rs.get(str(receipt.get("ticker") or "").upper(), {})
            if prior_rs:
                receipt.update({key: value for key, value in prior_rs.items() if value is not None})
            receipt["rs_reference_scope"] = "FULL_STAGE1_UNIVERSE" if full_stage1 > MAX_CANDIDATES else "PARTIAL_MONITOR_QUEUE"
            receipt["rs_full_stage1_universe"] = full_stage1
            receipt["rs_reference_at"] = receipt.get("rs_reference_at") or latest.get("completed_at") or latest.get("generated_at")
        if report_url:
            for receipt in receipts:
                receipt["report_url"] = report_url
    except Exception as exc:
        state["refresh_warning"] = f"{type(exc).__name__}: {str(exc)[:400]}"
    return monitor_receipts(receipts, now=now, state=state, notify=notify)


def run_due_monitor(*, now: datetime | None = None, notify: bool = True) -> dict[str, Any]:
    with _monitor_execution_lock() as acquired:
        if not acquired:
            return {"state": "ALREADY_RUNNING", "interval_minutes": INTERVAL_MINUTES,
                    "notification_policy": "Ingen parallell kjøring eller dobbeltvarsling."}
        return _run_due_monitor_unlocked(now=now, notify=notify)
