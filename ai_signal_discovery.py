"""AI Signal Discovery v18.6.73.

Passive signal discovery layer on top of AI Discovery Foundation.
It mines existing observations/results for candidate rules and lets the user
promote candidates into Signal Library. It does not change trading or engine
scoring logic.
"""
from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ai_discovery_foundation import (
    DB_PATH,
    _connect,
    _df,
    _now_iso,
    add_observation,
    csv_from_rows,
    init_ai_discovery_db,
    list_observations,
    list_results,
    log_history,
    upsert_signal,
)

DISCOVERY_VERSION = "v18.6.73"
MIN_OBSERVATIONS_DEFAULT = 3


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, "", "N/A", "-", "None"):
        return None
    try:
        if isinstance(value, str):
            value = value.replace("%", "").replace("$", "").replace(" ", "").replace(",", ".")
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    except Exception:
        return None


def _parse_features(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except Exception:
        return {}


def _numeric_feature_map(row: Dict[str, Any]) -> Dict[str, float]:
    """Extract useful numeric values from observation row + feature_json."""
    features = _parse_features(row.get("feature_json"))
    out: Dict[str, float] = {}
    candidate_keys = {
        "score", "Score", "Long Alpha", "long_alpha", "confidence", "Confidence", "Conf",
        "ownership", "Ownership", "insider", "Insider", "earnings", "Earnings",
        "analyst", "Analyst", "momentum", "Momentum", "short_interest", "Short Interest",
        "rsi", "RSI", "volume_boost", "Volume Boost", "data_quality", "Data", "Datakvalitet",
        "1M", "3M", "6M", "return_pct", "Max drawdown", "max_drawdown", "P/E", "pe",
    }
    for source in (row, features):
        for key, value in (source or {}).items():
            if key not in candidate_keys and not any(token.lower() in str(key).lower() for token in ["score", "conf", "alpha", "ownership", "insider", "earn", "analyst", "momentum", "rsi", "short", "volume"]):
                continue
            number = _safe_float(value)
            if number is not None:
                clean_key = str(key).strip().replace(" ", "_").replace("/", "_").lower()
                out[clean_key] = number
    return out


def init_signal_discovery_db() -> None:
    """Create candidate table used by v18.6.73 Signal Discovery."""
    init_ai_discovery_db()
    with _connect() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS discovered_signal_candidates (
                candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_key TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                category TEXT,
                rule_json TEXT NOT NULL DEFAULT '{}',
                support_count INTEGER NOT NULL DEFAULT 0,
                measured_count INTEGER NOT NULL DEFAULT 0,
                avg_return_pct REAL,
                hit_rate_pct REAL,
                score REAL,
                status TEXT NOT NULL DEFAULT 'CANDIDATE',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                note TEXT
            );
            """
        )
        con.commit()


def _results_by_observation() -> Dict[int, List[Dict[str, Any]]]:
    results = list_results(100000)
    by_obs: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for r in results:
        try:
            by_obs[int(r.get("observation_id"))].append(r)
        except Exception:
            continue
    return by_obs


def _candidate_stats(rows: List[Dict[str, Any]], feature_key: str, operator: str, threshold: float) -> Dict[str, Any]:
    matched = []
    for row in rows:
        features = _numeric_feature_map(row)
        value = features.get(feature_key)
        if value is None:
            continue
        if operator == ">=" and value >= threshold:
            matched.append(row)
        elif operator == "<=" and value <= threshold:
            matched.append(row)
    returns: List[float] = []
    measured = 0
    for row in matched:
        for res in row.get("_results", []):
            ret = _safe_float(res.get("return_pct"))
            if ret is not None:
                returns.append(ret)
                measured += 1
    avg_ret = round(sum(returns) / len(returns), 2) if returns else None
    hit = round(sum(1 for r in returns if r > 0) / len(returns) * 100.0, 1) if returns else None
    # Conservative discovery score: support + result quality. No trading decisions.
    base = min(len(matched), 50) * 1.0
    result_bonus = (avg_ret or 0) * 2.0 + ((hit or 0) - 50) * 0.2 if returns else 0
    score = round(base + result_bonus, 2)
    return {
        "support_count": len(matched),
        "measured_count": measured,
        "avg_return_pct": avg_ret,
        "hit_rate_pct": hit,
        "score": score,
    }


def mine_signal_candidates(min_support: int = MIN_OBSERVATIONS_DEFAULT) -> List[Dict[str, Any]]:
    """Generate passive candidate signal rules from tracked observations.

    It searches one-feature threshold rules first. With little data, it still
    proposes OBSERVE candidates, but marks them as low support.
    """
    init_signal_discovery_db()
    observations = list_observations(100000)
    results_by_obs = _results_by_observation()
    enriched: List[Dict[str, Any]] = []
    for row in observations:
        row = dict(row)
        try:
            row["_results"] = results_by_obs.get(int(row.get("observation_id")), [])
        except Exception:
            row["_results"] = []
        enriched.append(row)

    feature_values: Dict[str, List[float]] = defaultdict(list)
    for row in enriched:
        for key, value in _numeric_feature_map(row).items():
            feature_values[key].append(value)

    candidates: List[Dict[str, Any]] = []
    for key, values in feature_values.items():
        values = sorted(v for v in values if v is not None)
        if len(values) < 2:
            continue
        # Candidate thresholds: median and upper quartile for positive signals.
        idx_med = max(0, min(len(values) - 1, int(len(values) * 0.50)))
        idx_q75 = max(0, min(len(values) - 1, int(len(values) * 0.75)))
        for label, threshold in [("MEDIAN", values[idx_med]), ("Q75", values[idx_q75])]:
            stats = _candidate_stats(enriched, key, ">=", threshold)
            if stats["support_count"] <= 0:
                continue
            status = "CANDIDATE" if stats["support_count"] >= min_support else "LOW_SUPPORT"
            candidate_key = f"DISC_{key.upper()}_GE_{str(round(threshold, 4)).replace('.', '_')}_{label}"
            rule = {"feature": key, "operator": ">=", "threshold": threshold, "horizon_days": [30, 60, 90, 180], "source": "AI Signal Discovery v18.6.73"}
            candidates.append({
                "candidate_key": candidate_key,
                "name": f"{key} >= {round(threshold, 2)}",
                "category": "Signal Discovery",
                "rule": rule,
                "status": status,
                **stats,
                "note": "Passiv kandidat. Må observeres/valideres før eventuell bruk.",
            })
    # Seed templates if there is no tracked data yet.
    if not candidates:
        templates = [
            ("DISC_TEMPLATE_OWNERSHIP_ANALYST", "ownership >= 7 + analyst >= 7", {"ownership_min": 7, "analyst_min": 7, "horizon_days": [30, 60, 90, 180]}),
            ("DISC_TEMPLATE_INSIDER_EARNINGS", "insider >= 7 + earnings >= 6.5", {"insider_min": 7, "earnings_min": 6.5, "horizon_days": [30, 60, 90, 180]}),
            ("DISC_TEMPLATE_LOW_OVERLAP", "long_engine_exclusive == true", {"source": "Long Engine", "top_picks_overlap": 0, "horizon_days": [30, 60, 90, 180]}),
        ]
        for key, name, rule in templates:
            candidates.append({
                "candidate_key": key,
                "name": name,
                "category": "Signal Discovery template",
                "rule": rule,
                "support_count": 0,
                "measured_count": 0,
                "avg_return_pct": None,
                "hit_rate_pct": None,
                "score": 0,
                "status": "TEMPLATE",
                "note": "Startmal fordi datagrunnlaget er for lite ennå.",
            })

    save_discovered_candidates(candidates)
    log_history("SIGNAL_DISCOVERY_RUN", f"Signal Discovery kjørt: {len(candidates)} kandidater", payload={"candidates": len(candidates), "min_support": min_support})
    return list_discovered_candidates()


def save_discovered_candidates(candidates: Iterable[Dict[str, Any]]) -> None:
    init_signal_discovery_db()
    now = _now_iso()
    with _connect() as con:
        for c in candidates:
            con.execute(
                """INSERT INTO discovered_signal_candidates
                   (candidate_key, name, category, rule_json, support_count, measured_count, avg_return_pct, hit_rate_pct, score, status, created_at, updated_at, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(candidate_key) DO UPDATE SET
                       name=excluded.name,
                       category=excluded.category,
                       rule_json=excluded.rule_json,
                       support_count=excluded.support_count,
                       measured_count=excluded.measured_count,
                       avg_return_pct=excluded.avg_return_pct,
                       hit_rate_pct=excluded.hit_rate_pct,
                       score=excluded.score,
                       status=excluded.status,
                       updated_at=excluded.updated_at,
                       note=excluded.note""",
                (
                    c["candidate_key"], c.get("name"), c.get("category"), json.dumps(c.get("rule") or {}, ensure_ascii=False),
                    int(c.get("support_count") or 0), int(c.get("measured_count") or 0), c.get("avg_return_pct"), c.get("hit_rate_pct"),
                    c.get("score"), c.get("status") or "CANDIDATE", now, now, c.get("note"),
                ),
            )
        con.commit()


def list_discovered_candidates(limit: int = 500) -> List[Dict[str, Any]]:
    init_signal_discovery_db()
    with _connect() as con:
        rows = con.execute(
            "SELECT * FROM discovered_signal_candidates ORDER BY score DESC, support_count DESC, updated_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        try:
            d["rule"] = json.loads(d.pop("rule_json") or "{}")
        except Exception:
            d["rule"] = {}
        out.append(d)
    return out


def promote_candidate_to_library(candidate_key: str, new_signal_id: Optional[str] = None) -> str:
    candidates = [c for c in list_discovered_candidates(10000) if c.get("candidate_key") == candidate_key]
    if not candidates:
        raise ValueError(f"Kandidat finnes ikke: {candidate_key}")
    c = candidates[0]
    signal_id = (new_signal_id or c["candidate_key"].replace("DISC_", "AI_DISC_")).upper().strip()
    upsert_signal(
        signal_id=signal_id,
        name=f"AI Discovery: {c.get('name')}",
        category="AI Discovery promoted",
        description=f"Promotert fra Signal Discovery. Support {c.get('support_count')}, measured {c.get('measured_count')}, avg {c.get('avg_return_pct')}, hit {c.get('hit_rate_pct')}. Ikke automatisk trading.",
        definition=c.get("rule") or {},
        status="OBSERVE",
    )
    log_history("SIGNAL_PROMOTE", f"Kandidat {candidate_key} promotert til Signal Library som {signal_id}", signal_id=signal_id, payload={"candidate_key": candidate_key})
    return signal_id


def build_signal_discovery_report() -> Dict[str, Any]:
    candidates = list_discovered_candidates(10000)
    by_status: Dict[str, int] = defaultdict(int)
    for c in candidates:
        by_status[str(c.get("status") or "UNKNOWN")] += 1
    return {
        "version": DISCOVERY_VERSION,
        "created_at": _now_iso(),
        "scope": "Signal Discovery",
        "learning_loop": "OFF",
        "candidate_count": len(candidates),
        "by_status": dict(by_status),
        "top_candidates": candidates[:20],
    }


def render_signal_discovery_tab() -> None:
    """Streamlit tab content for v18.6.73 Signal Discovery."""
    import streamlit as st

    init_signal_discovery_db()
    st.markdown("#### 🔎 Signal Discovery")
    st.caption(
        "FASE 5A+: finner passive kandidatsignaler fra observasjoner/resultater. "
        "Learning Loop er fortsatt AV; ingen scoring, kjøp/salg eller motorlogikk endres."
    )

    c1, c2, c3 = st.columns([0.7, 0.7, 2.0])
    with c1:
        min_support = st.number_input("Min. observasjoner", min_value=1, max_value=100, value=MIN_OBSERVATIONS_DEFAULT, step=1, key="signal_discovery_min_support_v1873")
    with c2:
        if st.button("🔎 Kjør Signal Discovery", key="signal_discovery_run_v1873"):
            found = mine_signal_candidates(int(min_support))
            st.session_state["signal_discovery_latest_report_v1873"] = build_signal_discovery_report()
            st.success(f"Signal Discovery kjørt: {len(found)} kandidater.")
            st.rerun()
    with c3:
        st.info("Kandidater må promoteres til Signal Library før de spores som egne signaler. Dette er observasjon, ikke automatisk trading.")

    candidates = list_discovered_candidates(500)
    if not candidates:
        st.warning("Ingen kandidater ennå. Kjør Signal Discovery først.")
        return

    display_rows = []
    for c in candidates:
        display_rows.append({
            "Kandidat": c.get("candidate_key"),
            "Navn": c.get("name"),
            "Status": c.get("status"),
            "Support": c.get("support_count"),
            "Målt": c.get("measured_count"),
            "Snitt %": c.get("avg_return_pct"),
            "Hit %": c.get("hit_rate_pct"),
            "Score": c.get("score"),
            "Regel": json.dumps(c.get("rule") or {}, ensure_ascii=False),
        })
    st.dataframe(_df(display_rows), width="stretch", hide_index=True)

    with st.expander("Promoter kandidat til Signal Library", expanded=False):
        labels = [f"{c['candidate_key']} · {c.get('name')}" for c in candidates]
        label_map = {label: c for label, c in zip(labels, candidates)}
        selected = st.selectbox("Kandidat", labels, key="signal_discovery_promote_select_v1873")
        default_id = label_map[selected]["candidate_key"].replace("DISC_", "AI_DISC_")[:80]
        signal_id = st.text_input("Ny Signal-ID", value=default_id, key="signal_discovery_promote_id_v1873")
        if st.button("Legg i Signal Library som OBSERVE", key="signal_discovery_promote_btn_v1873"):
            try:
                new_id = promote_candidate_to_library(label_map[selected]["candidate_key"], signal_id)
                st.success(f"Promotert til Signal Library: {new_id}")
                st.rerun()
            except Exception as exc:
                st.error(f"Kunne ikke promotere kandidat: {exc}")

    report = st.session_state.get("signal_discovery_latest_report_v1873") or build_signal_discovery_report()
    with st.expander("Signal Discovery rapport", expanded=False):
        st.json(report)
        st.download_button("Last ned kandidater CSV", data=csv_from_rows(display_rows), file_name="ai_signal_discovery_candidates.csv", mime="text/csv")
        st.download_button("Last ned rapport JSON", data=json.dumps(report, ensure_ascii=False, indent=2), file_name="AI_SIGNAL_DISCOVERY_REPORT.json", mime="application/json")
