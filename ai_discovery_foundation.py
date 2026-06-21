"""AI Discovery Foundation v18.6.72.

Foundation layer only: signal library, signal tracking, result database,
history and reporting. This module does not make trading decisions and does
not change existing motor logic.
"""
from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # type: ignore

DATA_DIR = Path("data") / "ai_discovery"
DB_PATH = DATA_DIR / "ai_discovery.db"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
REPORT_DIR = DATA_DIR / "reports"


try:
    from ai_signal_discovery import render_signal_discovery_tab, build_signal_discovery_report
except Exception:  # pragma: no cover
    render_signal_discovery_tab = None  # type: ignore
    build_signal_discovery_report = None  # type: ignore

DEFAULT_SIGNALS: List[Dict[str, Any]] = [
    {
        "signal_id": "OWNERSHIP_ANALYST_MOMENTUM_V1",
        "name": "Ownership + Analyst + Momentum",
        "category": "Long discovery",
        "description": "Kombinerer sterk ownership, analytikerstøtte og momentum. Kun observasjon, ikke automatisk kjøp.",
        "definition_json": {
            "ownership_min": 7.0,
            "analyst_min": 7.0,
            "momentum_min": 6.5,
            "horizon_days": [30, 60, 90, 180],
        },
        "status": "OBSERVE",
    },
    {
        "signal_id": "INSIDER_EARNINGS_REVISION_V1",
        "name": "Insider + Earnings Revision",
        "category": "Long discovery",
        "description": "Ser etter samspill mellom insiderstøtte og positiv earnings/estimate-revisjon.",
        "definition_json": {
            "insider_min": 7.0,
            "earnings_min": 6.5,
            "horizon_days": [30, 60, 90, 180],
        },
        "status": "OBSERVE",
    },
    {
        "signal_id": "LOW_OVERLAP_LONG_ALPHA_V1",
        "name": "Low-overlap Long Alpha",
        "category": "Engine overlap",
        "description": "Fanger kandidater fra Long Engine som ikke finnes i Top Picks. Måler om unik motor faktisk gir merverdi.",
        "definition_json": {
            "source": "Long Engine",
            "top_picks_overlap": 0,
            "horizon_days": [30, 60, 90, 180],
        },
        "status": "OBSERVE",
    },
    {
        "signal_id": "SHORT_INTEREST_PRESSURE_V1",
        "name": "Short Interest Pressure",
        "category": "Risk / short",
        "description": "Observerer om høy short interest kombinert med svak trend predikerer videre fall eller squeeze.",
        "definition_json": {
            "short_interest_min": 7.0,
            "trend_max": 4.5,
            "horizon_days": [30, 60, 90, 180],
        },
        "status": "OBSERVE",
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


def _connect() -> sqlite3.Connection:
    _ensure_dirs()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_ai_discovery_db() -> None:
    """Create all foundation tables and seed default signal library."""
    with _connect() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS signal_library (
                signal_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT,
                description TEXT,
                definition_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'OBSERVE',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS signal_observations (
                observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                market TEXT,
                source_engine TEXT,
                observed_at TEXT NOT NULL,
                entry_price REAL,
                score REAL,
                confidence REAL,
                horizon_days INTEGER,
                feature_json TEXT NOT NULL DEFAULT '{}',
                note TEXT,
                FOREIGN KEY(signal_id) REFERENCES signal_library(signal_id)
            );

            CREATE TABLE IF NOT EXISTS signal_results (
                result_id INTEGER PRIMARY KEY AUTOINCREMENT,
                observation_id INTEGER NOT NULL,
                signal_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                horizon_days INTEGER NOT NULL,
                measured_at TEXT NOT NULL,
                entry_price REAL,
                exit_price REAL,
                return_pct REAL,
                max_drawdown_pct REAL,
                outcome TEXT,
                note TEXT,
                FOREIGN KEY(observation_id) REFERENCES signal_observations(observation_id)
            );

            CREATE TABLE IF NOT EXISTS signal_history (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                signal_id TEXT,
                ticker TEXT,
                message TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS discovery_reports (
                report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_at TEXT NOT NULL,
                title TEXT NOT NULL,
                report_json TEXT NOT NULL,
                summary TEXT
            );
            """
        )
        now = _now_iso()
        for item in DEFAULT_SIGNALS:
            existing = con.execute("SELECT signal_id FROM signal_library WHERE signal_id=?", (item["signal_id"],)).fetchone()
            if existing:
                continue
            con.execute(
                """INSERT INTO signal_library
                   (signal_id, name, category, description, definition_json, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item["signal_id"],
                    item["name"],
                    item.get("category"),
                    item.get("description"),
                    json.dumps(item.get("definition_json") or {}, ensure_ascii=False),
                    item.get("status") or "OBSERVE",
                    now,
                    now,
                ),
            )
        con.commit()


def log_history(event_type: str, message: str, signal_id: str = "", ticker: str = "", payload: Optional[Dict[str, Any]] = None) -> None:
    init_ai_discovery_db()
    with _connect() as con:
        con.execute(
            "INSERT INTO signal_history (event_at, event_type, signal_id, ticker, message, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
            (_now_iso(), event_type, signal_id or None, ticker or None, message, json.dumps(payload or {}, ensure_ascii=False)),
        )
        con.commit()


def list_signals() -> List[Dict[str, Any]]:
    init_ai_discovery_db()
    with _connect() as con:
        rows = con.execute("SELECT * FROM signal_library ORDER BY status, category, name").fetchall()
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        try:
            d["definition"] = json.loads(d.pop("definition_json") or "{}")
        except Exception:
            d["definition"] = {}
        out.append(d)
    return out


def upsert_signal(signal_id: str, name: str, category: str, description: str, definition: Dict[str, Any], status: str = "OBSERVE") -> None:
    init_ai_discovery_db()
    now = _now_iso()
    with _connect() as con:
        con.execute(
            """INSERT INTO signal_library (signal_id, name, category, description, definition_json, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(signal_id) DO UPDATE SET
                    name=excluded.name,
                    category=excluded.category,
                    description=excluded.description,
                    definition_json=excluded.definition_json,
                    status=excluded.status,
                    updated_at=excluded.updated_at""",
            (signal_id, name, category, description, json.dumps(definition or {}, ensure_ascii=False), status, now, now),
        )
        con.commit()
    log_history("SIGNAL_UPSERT", f"Signal {signal_id} lagret/oppdatert", signal_id=signal_id, payload={"status": status})


def add_observation(
    signal_id: str,
    ticker: str,
    market: str = "",
    source_engine: str = "Manual",
    entry_price: Optional[float] = None,
    score: Optional[float] = None,
    confidence: Optional[float] = None,
    horizon_days: int = 90,
    features: Optional[Dict[str, Any]] = None,
    note: str = "",
) -> int:
    init_ai_discovery_db()
    ticker = str(ticker or "").upper().strip()
    if not ticker:
        raise ValueError("ticker mangler")
    with _connect() as con:
        cur = con.execute(
            """INSERT INTO signal_observations
               (signal_id, ticker, market, source_engine, observed_at, entry_price, score, confidence, horizon_days, feature_json, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                signal_id,
                ticker,
                market or None,
                source_engine or None,
                _now_iso(),
                entry_price,
                score,
                confidence,
                int(horizon_days or 90),
                json.dumps(features or {}, ensure_ascii=False),
                note or None,
            ),
        )
        obs_id = int(cur.lastrowid)
        con.commit()
    log_history("OBSERVATION_ADD", f"Observasjon #{obs_id}: {ticker} på {signal_id}", signal_id=signal_id, ticker=ticker, payload={"observation_id": obs_id})
    return obs_id


def add_result(
    observation_id: int,
    exit_price: Optional[float],
    horizon_days: int,
    max_drawdown_pct: Optional[float] = None,
    outcome: str = "MEASURED",
    note: str = "",
) -> int:
    init_ai_discovery_db()
    with _connect() as con:
        obs = con.execute("SELECT * FROM signal_observations WHERE observation_id=?", (int(observation_id),)).fetchone()
        if not obs:
            raise ValueError(f"Observation {observation_id} finnes ikke")
        entry = obs["entry_price"]
        ret = None
        if entry not in (None, 0) and exit_price is not None:
            ret = (float(exit_price) - float(entry)) / float(entry) * 100.0
        cur = con.execute(
            """INSERT INTO signal_results
               (observation_id, signal_id, ticker, horizon_days, measured_at, entry_price, exit_price, return_pct, max_drawdown_pct, outcome, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                int(observation_id),
                obs["signal_id"],
                obs["ticker"],
                int(horizon_days or obs["horizon_days"] or 90),
                _now_iso(),
                entry,
                exit_price,
                ret,
                max_drawdown_pct,
                outcome,
                note or None,
            ),
        )
        rid = int(cur.lastrowid)
        con.commit()
    log_history("RESULT_ADD", f"Resultat #{rid}: {obs['ticker']} {ret if ret is not None else 'N/A'}%", signal_id=obs["signal_id"], ticker=obs["ticker"], payload={"result_id": rid, "return_pct": ret})
    return rid


def _query(sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
    init_ai_discovery_db()
    with _connect() as con:
        rows = con.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def list_observations(limit: int = 500) -> List[Dict[str, Any]]:
    return _query(
        """SELECT o.*, s.name AS signal_name, s.status AS signal_status
           FROM signal_observations o
           LEFT JOIN signal_library s ON s.signal_id=o.signal_id
           ORDER BY o.observed_at DESC, o.observation_id DESC
           LIMIT ?""",
        (int(limit),),
    )


def list_results(limit: int = 500) -> List[Dict[str, Any]]:
    return _query(
        """SELECT r.*, s.name AS signal_name
           FROM signal_results r
           LEFT JOIN signal_library s ON s.signal_id=r.signal_id
           ORDER BY r.measured_at DESC, r.result_id DESC
           LIMIT ?""",
        (int(limit),),
    )


def list_history(limit: int = 500) -> List[Dict[str, Any]]:
    return _query("SELECT * FROM signal_history ORDER BY event_at DESC, event_id DESC LIMIT ?", (int(limit),))


def build_report() -> Dict[str, Any]:
    init_ai_discovery_db()
    signals = list_signals()
    observations = list_observations(10000)
    results = list_results(10000)
    summary_by_signal: Dict[str, Dict[str, Any]] = {}
    for s in signals:
        sid = s["signal_id"]
        obs_count = sum(1 for o in observations if o.get("signal_id") == sid)
        sig_results = [r for r in results if r.get("signal_id") == sid]
        returns = [float(r["return_pct"]) for r in sig_results if r.get("return_pct") is not None]
        avg_return = round(sum(returns) / len(returns), 2) if returns else None
        hit_rate = round(sum(1 for v in returns if v > 0) / len(returns) * 100.0, 1) if returns else None
        summary_by_signal[sid] = {
            "name": s.get("name"),
            "status": s.get("status"),
            "observations": obs_count,
            "measured_results": len(sig_results),
            "avg_return_pct": avg_return,
            "hit_rate_pct": hit_rate,
        }
    report = {
        "version": "v18.6.73",
        "created_at": _now_iso(),
        "scope": "AI Discovery Foundation + Signal Discovery",
        "learning_loop": "OFF",
        "signals": len(signals),
        "observations": len(observations),
        "results": len(results),
        "summary_by_signal": summary_by_signal,
    }
    with _connect() as con:
        con.execute(
            "INSERT INTO discovery_reports (report_at, title, report_json, summary) VALUES (?, ?, ?, ?)",
            (_now_iso(), "AI Discovery Foundation rapport", json.dumps(report, ensure_ascii=False), f"{len(signals)} signaler, {len(observations)} observasjoner, {len(results)} resultater"),
        )
        con.commit()
    return report


def report_to_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# AI Discovery Foundation rapport",
        "",
        f"Opprettet: {report.get('created_at', '-')}",
        f"Learning Loop: {report.get('learning_loop', 'OFF')}",
        "",
        f"Signal Library: {report.get('signals', 0)} signaler",
        f"Signal Tracking: {report.get('observations', 0)} observasjoner",
        f"Resultatdatabase: {report.get('results', 0)} målte resultater",
        "",
        "## Signaloppsummering",
    ]
    for sid, row in (report.get("summary_by_signal") or {}).items():
        lines.append(f"- **{sid}** ({row.get('status')}): {row.get('observations')} observasjoner, {row.get('measured_results')} resultater, snitt {row.get('avg_return_pct')}, hit-rate {row.get('hit_rate_pct')}")
    return "\n".join(lines) + "\n"


def csv_from_rows(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def capture_rows_as_observations(rows: Iterable[Dict[str, Any]], signal_id: str, source_engine: str, horizon_days: int = 90, max_rows: int = 50) -> int:
    """Capture candidate rows from another engine as discovery observations.

    This is passive tracking only. It does not feed back into scoring or trading.
    """
    count = 0
    for row in list(rows or [])[: int(max_rows)]:
        ticker = row.get("Ticker") or row.get("ticker") or row.get("symbol") or row.get("Symbol")
        if not ticker:
            continue
        price = row.get("Pris") or row.get("price") or row.get("Last") or row.get("last_price")
        score = row.get("Score") or row.get("score") or row.get("Long Alpha") or row.get("long_alpha")
        conf = row.get("Confidence") or row.get("confidence") or row.get("Conf")
        market = row.get("Land") or row.get("market") or row.get("Market")
        try:
            price_f = float(str(price).replace("%", "").replace(",", ".")) if price not in (None, "") else None
        except Exception:
            price_f = None
        try:
            score_f = float(str(score).replace("%", "").replace(",", ".")) if score not in (None, "") else None
        except Exception:
            score_f = None
        try:
            conf_f = float(str(conf).replace("%", "").replace(",", ".")) if conf not in (None, "") else None
        except Exception:
            conf_f = None
        add_observation(signal_id, str(ticker), market=str(market or ""), source_engine=source_engine, entry_price=price_f, score=score_f, confidence=conf_f, horizon_days=horizon_days, features=dict(row), note="Auto-captured foundation observation")
        count += 1
    return count


def _df(rows: List[Dict[str, Any]]):
    if pd is None:
        return rows
    return pd.DataFrame(rows)


def render_ai_discovery_foundation_panel() -> None:
    """Streamlit UI for AI Discovery Foundation."""
    import streamlit as st  # imported lazily so non-UI tests can import module

    init_ai_discovery_db()
    st.subheader("🧠 AI Discovery Foundation")
    st.caption(
        "FASE 5A: passivt signalbibliotek, tracking, resultatdatabase, historikk og rapportering. "
        "Learning Loop er AV og ingen motorlogikk endres."
    )

    signals = list_signals()
    observations = list_observations(500)
    results = list_results(500)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Signal Library", len(signals))
    k2.metric("Observasjoner", len(observations))
    k3.metric("Resultater", len(results))
    k4.metric("Learning Loop", "OFF")

    tab_library, tab_tracking, tab_results, tab_history, tab_reports, tab_discovery = st.tabs(
        ["Signal Library", "Signal Tracking", "Resultatdatabase", "Historikk", "Rapportering", "Signal Discovery"]
    )

    with tab_library:
        st.markdown("#### Signal Library")
        st.caption("Standard-signaler opprettes automatisk. Nye signaler kan legges inn som observasjonssignaler uten å påvirke trading.")
        if signals:
            display = []
            for s in signals:
                display.append({
                    "Signal": s.get("signal_id"),
                    "Navn": s.get("name"),
                    "Kategori": s.get("category"),
                    "Status": s.get("status"),
                    "Definisjon": json.dumps(s.get("definition") or {}, ensure_ascii=False),
                })
            st.dataframe(_df(display), use_container_width=True, hide_index=True)
        with st.expander("Legg til / oppdater signal", expanded=False):
            c1, c2, c3 = st.columns([1.2, 1.2, 0.8])
            with c1:
                signal_id = st.text_input("Signal-ID", value="CUSTOM_SIGNAL_V1", key="ai_disc_signal_id_v1872")
                name = st.text_input("Navn", value="Egendefinert signal", key="ai_disc_signal_name_v1872")
            with c2:
                category = st.text_input("Kategori", value="Manual discovery", key="ai_disc_signal_category_v1872")
                status = st.selectbox("Status", ["OBSERVE", "ACTIVE", "DEGRADED", "RETIRED"], key="ai_disc_signal_status_v1872")
            with c3:
                st.caption("JSON-definisjon")
            description = st.text_area("Beskrivelse", value="Beskriv hva signalet observerer.", height=80, key="ai_disc_signal_desc_v1872")
            definition_text = st.text_area("Definisjon JSON", value='{"horizon_days":[30,60,90,180]}', height=90, key="ai_disc_signal_def_v1872")
            if st.button("Lagre signal", key="ai_disc_save_signal_v1872"):
                try:
                    definition = json.loads(definition_text or "{}")
                    upsert_signal(signal_id.strip().upper(), name.strip(), category.strip(), description.strip(), definition, status)
                    st.success("Signal lagret.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Kunne ikke lagre signal: {exc}")

    with tab_tracking:
        st.markdown("#### Signal Tracking")
        st.caption("Legg inn passive observasjoner. Dette er en logg for senere evaluering, ikke kjøpssignal.")
        sig_options = [s.get("signal_id") for s in signals]
        if not sig_options:
            st.warning("Ingen signaler i biblioteket.")
        else:
            c1, c2, c3, c4 = st.columns([1, 0.7, 0.7, 0.7])
            with c1:
                obs_signal = st.selectbox("Signal", sig_options, key="ai_disc_obs_signal_v1872")
                obs_ticker = st.text_input("Ticker", value="", placeholder="f.eks. MEDI, AAPL, SUBC.OL", key="ai_disc_obs_ticker_v1872")
            with c2:
                obs_market = st.text_input("Marked", value="USA", key="ai_disc_obs_market_v1872")
                obs_engine = st.selectbox("Kilde", ["Manual", "Top Picks", "Long Engine", "AI Kandidattest", "Paper Trading"], key="ai_disc_obs_engine_v1872")
            with c3:
                obs_price = st.number_input("Entry-pris", value=0.0, step=0.01, key="ai_disc_obs_price_v1872")
                obs_score = st.number_input("Score", value=0.0, step=0.1, key="ai_disc_obs_score_v1872")
            with c4:
                obs_conf = st.number_input("Confidence", value=0.0, step=1.0, key="ai_disc_obs_conf_v1872")
                obs_horizon = st.selectbox("Horisont", [30, 60, 90, 180], index=2, key="ai_disc_obs_horizon_v1872")
            obs_note = st.text_input("Notat", value="", key="ai_disc_obs_note_v1872")
            if st.button("Legg til observasjon", key="ai_disc_add_obs_v1872"):
                try:
                    oid = add_observation(obs_signal, obs_ticker, obs_market, obs_engine, obs_price or None, obs_score or None, obs_conf or None, int(obs_horizon), {}, obs_note)
                    st.success(f"Observasjon #{oid} lagret.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Kunne ikke lagre observasjon: {exc}")
        if observations:
            st.dataframe(_df(observations), use_container_width=True, hide_index=True)
            st.download_button("Last ned observasjoner CSV", data=csv_from_rows(observations), file_name="ai_discovery_observations.csv", mime="text/csv")
        else:
            st.info("Ingen observasjoner ennå.")

    with tab_results:
        st.markdown("#### Resultatdatabase")
        st.caption("Registrer resultat etter 30/60/90/180 dager. Resultat brukes kun til rapportering i FASE 5A.")
        if observations:
            obs_labels = [f"#{o['observation_id']} {o['ticker']} · {o['signal_id']} · {o.get('observed_at','')}" for o in observations]
            obs_map = {label: o for label, o in zip(obs_labels, observations)}
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                selected_obs_label = st.selectbox("Observasjon", obs_labels, key="ai_disc_result_obs_v1872")
            with c2:
                result_horizon = st.selectbox("Målt horisont", [30, 60, 90, 180], index=2, key="ai_disc_result_horizon_v1872")
            with c3:
                exit_price = st.number_input("Exit/siste pris", value=0.0, step=0.01, key="ai_disc_result_exit_v1872")
            with c4:
                dd = st.number_input("Max drawdown %", value=0.0, step=0.1, key="ai_disc_result_dd_v1872")
            outcome = st.selectbox("Outcome", ["MEASURED", "WIN", "LOSS", "FLAT", "INCOMPLETE"], key="ai_disc_result_outcome_v1872")
            result_note = st.text_input("Resultatnotat", value="", key="ai_disc_result_note_v1872")
            if st.button("Lagre resultat", key="ai_disc_add_result_v1872"):
                try:
                    obs_id = int(obs_map[selected_obs_label]["observation_id"])
                    rid = add_result(obs_id, exit_price or None, int(result_horizon), dd, outcome, result_note)
                    st.success(f"Resultat #{rid} lagret.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Kunne ikke lagre resultat: {exc}")
        if results:
            st.dataframe(_df(results), use_container_width=True, hide_index=True)
            st.download_button("Last ned resultater CSV", data=csv_from_rows(results), file_name="ai_discovery_results.csv", mime="text/csv")
        else:
            st.info("Ingen målte resultater ennå.")

    with tab_history:
        st.markdown("#### Historikk")
        hist = list_history(500)
        if hist:
            st.dataframe(_df(hist), use_container_width=True, hide_index=True)
            st.download_button("Last ned historikk CSV", data=csv_from_rows(hist), file_name="ai_discovery_history.csv", mime="text/csv")
        else:
            st.info("Ingen historikk ennå.")

    with tab_reports:
        st.markdown("#### Rapportering")
        st.caption("Rapporten oppsummerer signaler, observasjoner og målte resultater. Learning Loop er fortsatt av.")
        if st.button("Bygg rapport", key="ai_disc_build_report_v1872"):
            report = build_report()
            st.session_state["ai_disc_latest_report_v1872"] = report
            st.success("Rapport bygget.")
        report = st.session_state.get("ai_disc_latest_report_v1872") or build_report()
        st.json(report)
        md = report_to_markdown(report)
        st.download_button("Last ned rapport Markdown", data=md, file_name="AI_DISCOVERY_FOUNDATION_REPORT.md", mime="text/markdown")
        st.download_button("Last ned rapport JSON", data=json.dumps(report, ensure_ascii=False, indent=2), file_name="AI_DISCOVERY_FOUNDATION_REPORT.json", mime="application/json")


    with tab_discovery:
        if render_signal_discovery_tab is None:
            st.error("Signal Discovery-modulen kunne ikke lastes.")
        else:
            render_signal_discovery_tab()
