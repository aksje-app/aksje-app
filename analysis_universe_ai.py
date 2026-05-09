"""
analysis_universe_ai.py

v18.5.3: Analyseunivers som AI-modul.

Dette er et workspace-/arkitekturlag for Analyseunivers. Modulen samler valg for
enkeltaksje, marked, multi-marked, top picks, watchlist, paper trading og
portefølje i AI Kontrollsenter.

Viktig: ekte AI-universe-picker, intelligent filtrering og komplett
sammenslått workspace-motor er eksplisitt markert som planlagt / ikke ferdig.
Modulen skal derfor ikke late som at den gjør autonom AI-utvelgelse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

try:
    import streamlit as st
except Exception:  # pragma: no cover - allows pure helper tests without Streamlit installed
    class _StreamlitUnavailable:
        session_state: Dict[str, Any] = {}

        def __getattr__(self, name: str):
            raise RuntimeError("Streamlit is required to render Analyseunivers AI UI")

    st = _StreamlitUnavailable()


AI_UNIVERSE_STATE_KEY = "ai_analysis_universe_config_v1853"
AI_UNIVERSE_PREVIEW_KEY = "ai_analysis_universe_preview_v1853"

WORKSPACE_MODES = [
    "Enkeltaksje",
    "Markedvalg",
    "Multi-marked",
    "Top Picks",
    "Watchlist",
    "Paper trading",
    "Portefølje",
    "Smart AI-utvalg (planlagt)",
]

MARKET_SCOPES = ["USA", "Norge", "Sverige", "Alle", "Top Picks", "Watchlist", "Paper trading", "Portefølje"]

SECTOR_OPTIONS = [
    "Alle sektorer",
    "Technology",
    "Financials",
    "Energy",
    "Industrials",
    "Healthcare",
    "Consumer",
    "Materials",
    "Utilities",
    "Communication",
    "Unknown",
]

FEATURE_STATUS_ROWS = [
    ("Enkeltaksje", "UI-koblet", "Manuell ticker kan fortsatt brukes som overstyring."),
    ("Markedvalg", "UI-koblet", "Bruker eksisterende markedskategori og appens aktive univers."),
    ("Multi-marked", "Arkitektur", "Kan lagres som scope, men full multi-market-motor er ikke ferdig."),
    ("Top Picks", "UI-koblet", "Leser eksisterende Top Picks når de finnes i session/cache."),
    ("Watchlist", "Delvis", "Kan vise siste kjente watchlist, men egen AI-watchlistvelger er ikke ferdig."),
    ("Paper trading", "Delvis", "Kan lese åpne paper-posisjoner; ingen automatisk handel startes her."),
    ("Portefølje", "Planlagt", "Porteføljeunivers er markert, men samlet porteføljemotor gjenstår."),
    ("Smart AI-utvalg", "Planlagt", "Ekte AI-universe-picker er ikke implementert ennå."),
    ("Risikofiltrering", "Preview", "Viser enkelt filter basert på eksisterende score/drawdown-felt."),
    ("Sektorfiltrering", "Preview", "Bruker grove ticker-/metadata-hint. Ikke full sektormodell."),
    ("Momentum/strength-filter", "Preview", "Bruker eksisterende score/momentum/strength når tilgjengelig."),
]


@dataclass(frozen=True)
class UniverseCandidate:
    ticker: str
    source: str
    score: Optional[float] = None
    strength: Optional[float] = None
    risk: str = "Ukjent"
    sector: str = "Unknown"
    note: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "Ticker": self.ticker,
            "Kilde": self.source,
            "Score": self.score,
            "Strength": self.strength,
            "Risiko": self.risk,
            "Sektor": self.sector,
            "Status": self.note,
        }


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _normalize_ticker(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def infer_sector_from_ticker(ticker: str, item: Optional[Mapping[str, Any]] = None) -> str:
    """Small, transparent fallback. Full sector model is still roadmap."""
    item = item or {}
    for key in ("sector", "Sector", "industry", "Industry"):
        value = str(item.get(key, "") or "").strip()
        if value:
            return value[:32]

    t = _normalize_ticker(ticker)
    if any(x in t for x in ("AAPL", "MSFT", "NVDA", "GOOGL", "META", "AVGO", "ADBE", "CRM")):
        return "Technology"
    if any(x in t for x in ("JPM", "BAC", "GS", "DNB", "STB", "NDA", "SHB")):
        return "Financials"
    if any(x in t for x in ("XOM", "CVX", "EQNR", "AKRBP", "VAR", "SHEL")):
        return "Energy"
    if any(x in t for x in ("ABB", "VOLV", "CAT", "GE", "BA", "KOG")):
        return "Industrials"
    if any(x in t for x in ("JNJ", "PFE", "MRK", "NOVO", "AZN", "LLY")):
        return "Healthcare"
    if any(x in t for x in ("AMZN", "TSLA", "MCD", "NKE", "HD", "ORSTED")):
        return "Consumer"
    if any(x in t for x in ("YAR", "NEM", "LIN", "NUE", "RIO")):
        return "Materials"
    return "Unknown"


def infer_risk_bucket(item: Mapping[str, Any]) -> str:
    """Infer simple risk label from fields the app already produces."""
    max_drawdown = _safe_float(item.get("max_drawdown"))
    score = _safe_float(item.get("score"))
    risk_score = _safe_float(item.get("risk_score") or item.get("risk"))

    if risk_score is not None:
        if risk_score >= 75:
            return "Høy"
        if risk_score >= 45:
            return "Middels"
        return "Lav"

    if max_drawdown is not None:
        dd_abs = abs(max_drawdown)
        # drawdown can be represented as -0.22 or -22 depending on source.
        if dd_abs <= 1:
            dd_abs *= 100
        if dd_abs >= 35:
            return "Høy"
        if dd_abs >= 18:
            return "Middels"
        return "Lav"

    if score is not None:
        if score >= 7.0:
            return "Lav"
        if score >= 5.0:
            return "Middels"
        return "Høy"

    return "Ukjent"


def infer_strength(item: Mapping[str, Any]) -> Optional[float]:
    for key in ("strength", "momentum_strength", "momentum", "score"):
        value = _safe_float(item.get(key))
        if value is not None:
            if key == "score" and value <= 10:
                return round(value * 10, 1)
            return round(value, 1)
    return None


def _candidate_from_rank_item(source: str, item: Mapping[str, Any]) -> Optional[UniverseCandidate]:
    ticker = _normalize_ticker(item.get("ticker") or item.get("symbol"))
    if not ticker:
        return None
    score = _safe_float(item.get("score"))
    strength = infer_strength(item)
    return UniverseCandidate(
        ticker=ticker,
        source=source,
        score=round(score, 2) if score is not None else None,
        strength=strength,
        risk=infer_risk_bucket(item),
        sector=infer_sector_from_ticker(ticker, item),
        note="Eksisterende rangering/cache",
    )


def _iter_ranked_sources(latest_rankings: Mapping[str, Any]) -> Iterable[UniverseCandidate]:
    for source, rows in (latest_rankings or {}).items():
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            continue
        for row in rows:
            if isinstance(row, Mapping):
                candidate = _candidate_from_rank_item(str(source), row)
                if candidate:
                    yield candidate


def _load_paper_positions() -> List[UniverseCandidate]:
    try:
        from paper_store import load_portfolio

        portfolio = load_portfolio() or {}
        positions = portfolio.get("positions", {}) or {}
    except Exception:
        positions = {}

    candidates: List[UniverseCandidate] = []
    for ticker, pos in positions.items():
        pos = pos if isinstance(pos, Mapping) else {}
        t = _normalize_ticker(pos.get("ticker") or ticker)
        if not t:
            continue
        confidence = _safe_float(pos.get("confidence"))
        candidates.append(
            UniverseCandidate(
                ticker=t,
                source="Paper trading",
                score=None,
                strength=confidence,
                risk="Ukjent",
                sector=infer_sector_from_ticker(t, pos),
                note="Åpen paper-posisjon",
            )
        )
    return candidates


def collect_universe_candidates(session_state: Mapping[str, Any], limit: int = 250) -> List[UniverseCandidate]:
    """Collect only existing app data. Does not run scans or pretend to be an AI picker."""
    seen: set[Tuple[str, str]] = set()
    candidates: List[UniverseCandidate] = []

    latest_rankings = session_state.get("latest_rankings_v148", {}) or {}
    for candidate in _iter_ranked_sources(latest_rankings):
        key = (candidate.ticker, candidate.source)
        if key not in seen:
            candidates.append(candidate)
            seen.add(key)

    for raw in session_state.get("latest_watchlist_tickers_v156", []) or []:
        ticker = _normalize_ticker(raw)
        key = (ticker, "Watchlist")
        if ticker and key not in seen:
            candidates.append(
                UniverseCandidate(
                    ticker=ticker,
                    source="Watchlist",
                    risk="Ukjent",
                    sector=infer_sector_from_ticker(ticker),
                    note="Siste kjente watchlist",
                )
            )
            seen.add(key)

    for candidate in _load_paper_positions():
        key = (candidate.ticker, candidate.source)
        if key not in seen:
            candidates.append(candidate)
            seen.add(key)

    return candidates[: max(1, int(limit or 250))]


def filter_universe_candidates(
    candidates: Sequence[UniverseCandidate],
    scopes: Sequence[str],
    sectors: Sequence[str],
    max_risk: str,
    min_score: float,
    min_strength: float,
) -> List[UniverseCandidate]:
    """Transparent preview filters. Not the final AI-selection engine."""
    selected_scopes = {str(x) for x in scopes if x}
    selected_sectors = {str(x) for x in sectors if x and x != "Alle sektorer"}
    risk_order = {"Lav": 1, "Middels": 2, "Høy": 3, "Ukjent": 4}
    max_risk_value = risk_order.get(max_risk, 4)

    filtered: List[UniverseCandidate] = []
    for c in candidates:
        source = str(c.source)
        source_is_top_pick = source.startswith("TopPicks") or "Top Picks" in source
        if selected_scopes and "Alle" not in selected_scopes:
            allowed = False
            if "USA" in selected_scopes and source == "USA":
                allowed = True
            if "Norge" in selected_scopes and source == "Norge":
                allowed = True
            if "Sverige" in selected_scopes and source == "Sverige":
                allowed = True
            if "Top Picks" in selected_scopes and source_is_top_pick:
                allowed = True
            if "Watchlist" in selected_scopes and source == "Watchlist":
                allowed = True
            if "Paper trading" in selected_scopes and source == "Paper trading":
                allowed = True
            if "Portefølje" in selected_scopes and source in {"Portefølje", "Paper trading"}:
                allowed = True
            if not allowed:
                continue

        if selected_sectors and c.sector not in selected_sectors:
            continue

        if risk_order.get(c.risk, 4) > max_risk_value:
            continue

        if c.score is not None and c.score < min_score:
            continue

        if c.strength is not None and c.strength < min_strength:
            continue

        filtered.append(c)
    return filtered


def _feature_status_dataframe() -> pd.DataFrame:
    return pd.DataFrame(FEATURE_STATUS_ROWS, columns=["Del", "Status", "Kommentar"])


def _candidate_dataframe(candidates: Sequence[UniverseCandidate]) -> pd.DataFrame:
    return pd.DataFrame([c.as_dict() for c in candidates])


def _inject_ai_universe_css() -> None:
    st.markdown(
        """
        <style>
        .ai-universe-card {
            border: 1px solid rgba(125, 211, 252, 0.28);
            background: linear-gradient(180deg, rgba(15,23,42,.88), rgba(2,6,23,.78));
            border-radius: 16px;
            padding: .72rem .82rem;
            margin: .15rem 0 .45rem 0;
        }
        .ai-universe-title {
            font-size: 1.05rem;
            font-weight: 950;
            color: #f8fafc;
            margin-bottom: .18rem;
        }
        .ai-universe-sub {
            color: #cbd5e1;
            font-size: .82rem;
            line-height: 1.35;
        }
        .ai-universe-pill-row {
            display:flex;
            flex-wrap:wrap;
            gap:.35rem;
            margin-top:.48rem;
        }
        .ai-universe-pill {
            border: 1px solid rgba(148,163,184,.28);
            background: rgba(15,23,42,.78);
            border-radius: 999px;
            padding: .22rem .52rem;
            font-size: .74rem;
            font-weight: 850;
            color: #e2e8f0;
        }
        .ai-universe-pill.plan { border-color: rgba(250,204,21,.55); color:#fde68a; }
        .ai-universe-pill.ok { border-color: rgba(34,197,94,.50); color:#bbf7d0; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _set_pending_change(reason: str) -> None:
    st.session_state["pending_manual_changes_v16"] = True
    st.session_state["pending_manual_changes_reason_v16"] = reason


def _default_config() -> Dict[str, Any]:
    return {
        "mode": st.session_state.get("ai_universe_mode_draft_v1853", "Markedvalg"),
        "scopes": st.session_state.get("ai_universe_scopes_draft_v1853", ["USA"]),
        "manual_ticker": st.session_state.get("search_main_v157", ""),
        "max_count": int(st.session_state.get("max_count_main_v157", 30) or 30),
        "min_top_pick_score": float(st.session_state.get("min_top_pick_score_main_v157", 6.5) or 6.5),
        "use_news": bool(st.session_state.get("use_news_main_v157", True)),
        "use_signal_intelligence": bool(st.session_state.get("use_signal_intelligence_main_v157", True)),
        "max_risk": st.session_state.get("ai_universe_max_risk_v1853", "Middels"),
        "sectors": st.session_state.get("ai_universe_sectors_v1853", ["Alle sektorer"]),
        "min_strength": float(st.session_state.get("ai_universe_min_strength_v1853", 0.0) or 0.0),
    }


def render_ai_analysis_universe_workspace(expanded: bool = False) -> Dict[str, Any]:
    """Render Analyseunivers inside AI Kontrollsenter.

    Returns the saved config for callers/tests. Streamlit UI writes to existing
    app session_state keys only after explicit submit.
    """
    _inject_ai_universe_css()
    current = _default_config()

    st.markdown(
        """
        <div class="ai-universe-card">
            <div class="ai-universe-title">🎯 Analyseunivers som AI-modul</div>
            <div class="ai-universe-sub">
                Arkitekturen er påbegynt og samlet i AI Kontrollsenter. Den smarte AI-universmodulen er fortsatt planlagt:
                ekte AI-universe-picker, intelligent risikofiltrering og full sammenslått workspace-motor er ikke ferdig implementert ennå.
            </div>
            <div class="ai-universe-pill-row">
                <span class="ai-universe-pill ok">UI-workspace aktivt</span>
                <span class="ai-universe-pill">Enkeltaksje</span>
                <span class="ai-universe-pill">Markedvalg</span>
                <span class="ai-universe-pill">Multi-marked</span>
                <span class="ai-universe-pill">Top Picks</span>
                <span class="ai-universe-pill">Watchlist</span>
                <span class="ai-universe-pill">Paper trading</span>
                <span class="ai-universe-pill plan">Smart AI-utvalg: planlagt</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Konfigurer Analyseunivers AI-modul", expanded=expanded):
        st.info(
            "Denne modulen lagrer og viser valgt analyseunivers. Den starter ikke skjulte scans, "
            "og den later ikke som at AI-utvalget er ferdig før motoren faktisk er implementert."
        )

        with st.form("ai_analysis_universe_form_v1853", clear_on_submit=False):
            c1, c2, c3 = st.columns(3)
            with c1:
                mode = st.selectbox(
                    "Workspace-modus",
                    WORKSPACE_MODES,
                    index=WORKSPACE_MODES.index(current["mode"]) if current["mode"] in WORKSPACE_MODES else 1,
                    key="ai_universe_mode_draft_v1853",
                )
                scopes = st.multiselect(
                    "Marked / kilde",
                    MARKET_SCOPES,
                    default=[x for x in current["scopes"] if x in MARKET_SCOPES] or ["USA"],
                    key="ai_universe_scopes_draft_v1853",
                    help="Multi-marked kan lagres her, men full AI-motor for sammenslått analyse kommer senere.",
                )
                manual_ticker = st.text_input(
                    "Manuell ticker / enkeltaksje",
                    value=str(current["manual_ticker"] or ""),
                    placeholder="F.eks. AAPL, EQNR.OL eller ABB.ST",
                    key="ai_universe_manual_ticker_draft_v1853",
                )
            with c2:
                max_count = st.slider(
                    "Antall kandidater",
                    5,
                    200,
                    int(current["max_count"]),
                    key="ai_universe_max_count_draft_v1853",
                )
                min_top_pick_score = st.slider(
                    "Minimum score for Top Picks",
                    4.0,
                    9.0,
                    float(current["min_top_pick_score"]),
                    0.1,
                    key="ai_universe_min_top_pick_score_draft_v1853",
                )
                min_strength = st.slider(
                    "Momentum / strength-filter",
                    0.0,
                    100.0,
                    float(current["min_strength"]),
                    5.0,
                    key="ai_universe_min_strength_v1853",
                    help="Preview-filter basert på eksisterende score/strength-felt. Ikke full AI-strengthmodell ennå.",
                )
            with c3:
                max_risk = st.selectbox(
                    "Maks risiko",
                    ["Lav", "Middels", "Høy", "Ukjent"],
                    index=["Lav", "Middels", "Høy", "Ukjent"].index(current["max_risk"]) if current["max_risk"] in ["Lav", "Middels", "Høy", "Ukjent"] else 1,
                    key="ai_universe_max_risk_v1853",
                    help="Preview-filter. Risiko tolkes fra eksisterende score/drawdown når det finnes.",
                )
                sectors = st.multiselect(
                    "Sektorfilter",
                    SECTOR_OPTIONS,
                    default=[x for x in current["sectors"] if x in SECTOR_OPTIONS] or ["Alle sektorer"],
                    key="ai_universe_sectors_v1853",
                    help="Grov sektormapping/fallback. Full sektormodell er ikke ferdig.",
                )
                use_news = st.checkbox(
                    "Bruk nyheter/sentiment",
                    value=bool(current["use_news"]),
                    key="ai_universe_use_news_draft_v1853",
                )
                use_signal_intelligence = st.checkbox(
                    "Bruk Signal Intelligence",
                    value=bool(current["use_signal_intelligence"]),
                    key="ai_universe_use_signal_intelligence_draft_v1853",
                )

            submitted = st.form_submit_button("💾 Lagre Analyseunivers AI-oppsett som ventende", use_container_width=True)

        if submitted:
            config = {
                "mode": mode,
                "scopes": scopes,
                "manual_ticker": _normalize_ticker(manual_ticker),
                "max_count": int(max_count),
                "min_top_pick_score": float(min_top_pick_score),
                "use_news": bool(use_news),
                "use_signal_intelligence": bool(use_signal_intelligence),
                "max_risk": max_risk,
                "sectors": sectors,
                "min_strength": float(min_strength),
                "status": "architecture_started_not_fully_implemented",
            }
            st.session_state[AI_UNIVERSE_STATE_KEY] = config

            # Sync to the existing app controls. Heavy work still waits for the
            # app's existing global update button/manual-mode flow.
            st.session_state["max_count_main_v157"] = int(max_count)
            st.session_state["min_top_pick_score_main_v157"] = float(min_top_pick_score)
            st.session_state["use_news_main_v157"] = bool(use_news)
            st.session_state["use_signal_intelligence_main_v157"] = bool(use_signal_intelligence)
            st.session_state["search_main_v157"] = _normalize_ticker(manual_ticker)

            if "Alle" in scopes:
                st.session_state["market_category_selector_v157"] = "All Markets"
            elif "Norge" in scopes and len(scopes) == 1:
                st.session_state["market_category_selector_v157"] = "Norway / Oslo"
            elif "Sverige" in scopes and len(scopes) == 1:
                st.session_state["market_category_selector_v157"] = "Sweden / Stockholm"
            elif "USA" in scopes and len(scopes) == 1:
                st.session_state["market_category_selector_v157"] = "US Markets"

            _set_pending_change("Analyseunivers AI-modul endret")
            st.success("Analyseunivers AI-oppsett er lagret som ventende. Trykk Oppdater hele appen når du vil bruke det i tunge analyser.")
        else:
            config = st.session_state.get(AI_UNIVERSE_STATE_KEY, current)

        if mode == "Smart AI-utvalg (planlagt)":
            st.warning("Smart AI-utvalg er lagt inn som modulvalg, men den ekte AI-universe-picker-motoren er ikke ferdig implementert ennå.")

        st.markdown("#### Status for Analyseunivers-modulen")
        st.dataframe(_feature_status_dataframe(), use_container_width=True, hide_index=True)

        candidates = collect_universe_candidates(st.session_state, limit=max_count)
        preview = filter_universe_candidates(candidates, scopes, sectors, max_risk, min_top_pick_score, min_strength)
        st.session_state[AI_UNIVERSE_PREVIEW_KEY] = [c.as_dict() for c in preview]

        st.markdown("#### Preview av eksisterende kandidater")
        if preview:
            st.dataframe(_candidate_dataframe(preview[:50]), use_container_width=True, hide_index=True)
            st.caption(
                "Preview bruker bare eksisterende rangeringer, watchlist og paper-posisjoner som allerede finnes i appen. "
                "Den kjører ikke en ny AI-scan."
            )
        else:
            st.caption("Ingen eksisterende kandidater i cache/session for valgt scope ennå. Kjør vanlig markedspanel eller Top Picks for å fylle preview-data.")

        return dict(config or {})

    return dict(st.session_state.get(AI_UNIVERSE_STATE_KEY, current) or {})
