"""
analysis_universe_ai.py

v18.5.10: Analyseunivers koblet til felles datamodell og service-lag.

Dette er et workspace-/arkitekturlag for Analyseunivers. Modulen samler valg for
enkeltaksje, marked, multi-marked, top picks, watchlist, paper trading og
portefølje i AI Kontrollsenter.

Smart AI-utvalg kjører nå via services/universe_service.py og felles modeller i core_models.py.
Top Picks og Watchlist-handlinger går via egne services, ikke direkte UI-mutering.
"""

from __future__ import annotations
import logging
from utils import _safe_float  # v18.6.3 centralized helpers

from dataclasses import dataclass
import time
from html import escape
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from app_version import get_app_version
from market_universe import BASE_MARKET_SCOPES, MARKET_SCOPE_OPTIONS, NORDIC_MARKET_SCOPES, NO_MARKET_SELECTION_LABEL, expand_market_scope, picker_scope_options
from security_metadata import resolve_security_metadata, display_label, infer_security_listing

from services.service_registry import build_service_registry
from services.universe_service import (
    ACTIVE_UNIVERSE_KEY,
    ACTIVE_UNIVERSE_RANKING_KEY,
    ACTIVE_UNIVERSE_TICKERS_KEY,
    SMART_RESULT_KEY as AI_UNIVERSE_SMART_RESULT_KEY_V1859,
)

try:
    import streamlit as st
    from global_busy import set_global_busy, update_global_busy, finish_global_busy
except Exception:  # pragma: no cover - allows pure helper tests without Streamlit installed
    def set_global_busy(*args, **kwargs):
        return None
    def update_global_busy(*args, **kwargs):
        return None
    def finish_global_busy(*args, **kwargs):
        return None
    class _StreamlitUnavailable:
        session_state: Dict[str, Any] = {}

        def __getattr__(self, name: str):
            raise RuntimeError("Streamlit is required to render Analyseunivers AI UI")

    st = _StreamlitUnavailable()


def _safe_rerun() -> None:
    """Request a rerun on both new and older Streamlit versions."""
    try:
        st.rerun()
    except AttributeError:  # pragma: no cover
        try:
            st.experimental_rerun()
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)

AI_UNIVERSE_STATE_KEY = "ai_analysis_universe_config_v1853"
AI_UNIVERSE_PREVIEW_KEY = "ai_analysis_universe_preview_v1853"
AI_UNIVERSE_MODULE_VERSION = get_app_version()
AI_UNIVERSE_SMART_RESULT_KEY = AI_UNIVERSE_SMART_RESULT_KEY_V1859
AI_UNIVERSE_SMART_RESULT_LEGACY_KEY = "ai_analysis_universe_smart_result_v1858"

WORKSPACE_MODES = [
    "Analyseflyt input",
    "Enkeltaksje",
    "Markedvalg",
    "Multi-marked",
    "Top Picks",
    "Watchlist",
    "Paper trading",
    "Portefølje",
    "Manuell liste",
    "Smart AI-utvalg",
]

MARKET_SCOPES = picker_scope_options(include_sources=True)

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
    ("Enkeltaksje", "Operativ", "Manuell ticker løses til aktivt aksjeunivers uten fallback."),
    ("Markedvalg", "Operativ", "USA, Norge, Sverige, Finland, Danmark, Brasil, Norden og Alle løses via UniverseService og kan settes som aktivt univers."),
    ("Multi-marked", "Operativ", "Flere markeder kan blandes i samme picker-resultat med round-robin/deduplisering."),
    ("Top Picks", "Operativ", "Lagrede Top Picks kan brukes som univers og persisteres videre."),
    ("Watchlist", "Operativ", "Watchlist leses fra session/storage og kan bli aktivt univers."),
    ("Paper trading", "Operativ", "Åpne paper-posisjoner kan brukes som univers uten å starte handel."),
    ("Portefølje", "Operativ", "Portefølje/holdings kan brukes som univers via service-laget."),
    ("Manuell liste", "Operativ", "Flere tickere kan limes inn og lagres som aktivt univers."),
    ("Smart AI-utvalg", "Operativ", "Siste Smart AI-resultat kan brukes som univers, og ny scan kan fortsatt kjøres eksplisitt."),
    ("Aktivt aksjeunivers", "Operativ", "Smart Universe Picker lagrer felles tickerliste for Interaktiv analyse, Testing & Learning og videre moduler."),
    ("Risikofiltrering", "Operativ", "Bruker beregnet risiko fra volatilitet/drawdown eller eksisterende risk_score."),
    ("Sektorfiltrering", "Operativ", "Bruker sektor fra analysedata eller transparent ticker-fallback."),
    ("Momentum/strength-filter", "Operativ", "Beregner strength fra score_parts/avkastning eller eksisterende strength-felt."),
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
            "Navn": resolve_security_metadata(self.ticker, {"ticker": self.ticker}).get("name", self.ticker),
            "Visning": display_label(self.ticker, {"ticker": self.ticker}),
            "Kilde": self.source,
            "Score": self.score,
            "Strength": self.strength,
            "Risiko": self.risk,
            "Sektor": self.sector,
            "Status": self.note,
        }




def _normalize_ticker(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def _parse_manual_ticker_list(value: Any) -> List[str]:
    text = str(value or "").strip()
    if not text:
        return []
    raw_parts = []
    for part in text.replace(";", ",").replace("|", ",").replace("/", ",").replace("\n", ",").split(","):
        raw_parts.extend(part.split())
    out: List[str] = []
    for part in raw_parts:
        ticker = _normalize_ticker(part)
        if ticker and ticker not in out:
            out.append(ticker)
    return out


def infer_sector_from_ticker(ticker: str, item: Optional[Mapping[str, Any]] = None) -> str:
    """Shared metadata first; transparent pattern fallback second."""
    item = item or {}
    meta = resolve_security_metadata(ticker, item)
    meta_sector = str(meta.get("sector") or "").strip()
    if meta_sector and meta_sector not in {"Unknown", "Ukjent"}:
        return meta_sector[:48]
    for key in ("sector", "Sector", "industry", "Industry"):
        value = str(item.get(key, "") or "").strip()
        if value and value not in {"Unknown", "Ukjent"}:
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

    meta = resolve_security_metadata(item.get("ticker") or item.get("symbol"), item)
    meta_risk = str(meta.get("risk") or "").strip()
    return meta_risk if meta_risk and meta_risk != "Ukjent" else "Ukjent"


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
        import paper_store

        # Viewing Analyseunivers should not create a local runtime file.
        # paper_store.load_portfolio() creates paper_portfolio.json when the
        # local fallback file is missing, so skip the read until there is an
        # existing local file or an active Postgres store.
        if not paper_store.using_postgres() and not paper_store.STORE_FILE.exists():
            positions = {}
        else:
            portfolio = paper_store.load_portfolio() or {}
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


def _analysis_flow_input_count_for_smart_ai() -> int:
    try:
        from services.analysis_pipeline_service import get_analysis_pipeline_service
        from services.state_service import get_state_service
        from services.storage_service import get_storage_service

        pipeline = get_analysis_pipeline_service(
            state_service=get_state_service(st.session_state),
            storage_service=get_storage_service(),
        )
        return len(pipeline.candidates_for_stage("smart_ai"))
    except Exception:
        return 0


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

    active = session_state.get(ACTIVE_UNIVERSE_KEY, {}) or session_state.get("active_universe", {}) or {}
    if isinstance(active, Mapping):
        for raw in active.get("rows", []) or active.get("tickers", []) or []:
            if isinstance(raw, Mapping):
                ticker = _normalize_ticker(raw.get("ticker") or raw.get("symbol"))
                score = _safe_float(raw.get("score", raw.get("ai_score")))
                strength = _safe_float(raw.get("strength"))
                risk = str(raw.get("risk") or "Ukjent")
                sector = infer_sector_from_ticker(ticker, raw)
            else:
                ticker = _normalize_ticker(raw)
                score = strength = None
                risk = "Ukjent"
                sector = infer_sector_from_ticker(ticker)
            key = (ticker, ACTIVE_UNIVERSE_RANKING_KEY)
            if ticker and key not in seen:
                candidates.append(UniverseCandidate(ticker=ticker, source=ACTIVE_UNIVERSE_RANKING_KEY, score=score, strength=strength, risk=risk, sector=sector, note="Aktivt aksjeunivers"))
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
    selected_markets = {market for scope in selected_scopes for market in expand_market_scope(scope)}
    selected_sectors = {str(x) for x in sectors if x and x != "Alle sektorer"}
    risk_order = {"Lav": 1, "Middels": 2, "Høy": 3, "Ukjent": 4}
    max_risk_value = risk_order.get(max_risk, 4)

    filtered: List[UniverseCandidate] = []
    for c in candidates:
        source = str(c.source)
        source_is_top_pick = source.startswith("TopPicks") or "Top Picks" in source
        if selected_scopes:
            allowed = False
            listing = infer_security_listing(c.ticker, {"ticker": c.ticker, "source": source})
            market = str(listing.get("market") or "")
            if selected_markets and market in selected_markets:
                allowed = True
            for market_scope in MARKET_SCOPE_OPTIONS:
                if market_scope not in selected_scopes or expand_market_scope(market_scope):
                    continue
                if source == market_scope:
                    allowed = True
            if "Top Picks" in selected_scopes and source_is_top_pick:
                allowed = True
            if "Watchlist" in selected_scopes and source == "Watchlist":
                allowed = True
            if "Paper trading" in selected_scopes and source == "Paper trading":
                allowed = True
            if "Portefølje" in selected_scopes and source in {"Portefølje", "Paper trading"}:
                allowed = True
            if "Smart AI-utvalg" in selected_scopes and source in {"SmartAI", "Smart AI"}:
                allowed = True
            if "Smart Universe Picker" in selected_scopes and source == ACTIVE_UNIVERSE_RANKING_KEY:
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
    rows = []
    for idx, c in enumerate(candidates, start=1):
        raw = c.as_dict()
        meta = resolve_security_metadata(c.ticker, raw)
        listing = infer_security_listing(c.ticker, raw)
        rows.append({
            "Nr": idx,
            "Ticker": meta.get("ticker") or c.ticker,
            "Selskap": meta.get("name") or c.ticker,
            "Land": listing.get("country"),
            "Børs": listing.get("exchange"),
            "Marked": listing.get("market"),
            "Sektor": meta.get("sector") or c.sector,
            "Status": "Eksisterende score" if c.score is not None else "Ikke analysert ennå",
            "Score": c.score if c.score is not None else "Ikke scoret",
            "Risiko": meta.get("risk") or c.risk,
            "Forklaring": c.note or "Kandidat fra eksisterende cache/session. Kjør Smart AI-utvalg for ny scoring.",
        })
    return pd.DataFrame(rows)


def _smart_result_dataframe(result: Mapping[str, Any]) -> pd.DataFrame:
    rows = []
    source_label = str(result.get("source") or (result.get("summary") or {}).get("source") or "").lower()
    is_picker_only = source_label in {
        "marked", "multi-marked", "enkeltaksje", "manuell liste",
        "top picks", "watchlist", "paper trading", "portefølje", "portefã¸lje",
    }

    def _score_value(row: Mapping[str, Any], key: str) -> Any:
        value = row.get(key)
        return value if value not in (None, "") else ("Ikke scoret" if is_picker_only else "")

    def _reason_value(row: Mapping[str, Any], listing: Mapping[str, Any]) -> str:
        reason = str(row.get("reason") or "").strip()
        if reason and reason != "Valgt via Smart Universe Picker":
            return reason
        if is_picker_only:
            return f"Valgt fra {listing.get('market') or row.get('source') or 'univers'}. Ikke scoret ennå; kjør Smart AI-utvalg for rangering."
        return reason or "Scoret av Smart AI-utvalg."

    for idx, row in enumerate(result.get("candidates", []) or [], start=1):
        if not isinstance(row, Mapping):
            continue
        meta = resolve_security_metadata(row.get("ticker") or row.get("symbol"), row)
        try:
            from security_metadata import infer_security_listing
            listing = infer_security_listing(meta.get("ticker") or row.get("ticker"), row)
        except Exception:
            listing = {"country": "Ukjent", "exchange": "Ukjent", "market": row.get("market") or row.get("source") or "Ukjent"}
        rows.append(
            {
                "Nr": idx,
                "Ticker": meta.get("ticker") or row.get("ticker"),
                "Selskap": meta.get("name") or row.get("name"),
                "Land": listing.get("country"),
                "Børs": listing.get("exchange"),
                "Marked": listing.get("market") or row.get("market"),
                "Sektor": meta.get("sector") or row.get("sector"),
                "Status": "Ikke analysert ennå" if is_picker_only else "Scoret",
                "AI-score": _score_value(row, "ai_score"),
                "Smart-score": _score_value(row, "smart_score"),
                "Strength": _score_value(row, "strength"),
                "Risiko": meta.get("risk") or row.get("risk"),
                "Datakvalitet": row.get("data_quality") or row.get("data_quality_label") or ("Ikke testet" if is_picker_only else ""),
                "1m %": _score_value(row, "ret_1m_pct"),
                "3m %": _score_value(row, "ret_3m_pct"),
                "Forklaring": _reason_value(row, listing),
            }
        )
    df = pd.DataFrame(rows)
    if is_picker_only and not df.empty:
        picker_columns = ["Nr", "Ticker", "Selskap", "Land", "Børs", "Marked", "Sektor", "Status", "Risiko", "Forklaring"]
        return df[[col for col in picker_columns if col in df.columns]]
    return df




def _format_table_cell(value: Any) -> str:
    """Format values for compact HTML tables without showing Python None/nan."""
    try:
        if value is None:
            return ""
        if isinstance(value, float) and pd.isna(value):
            return ""
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            return f"{value:.2f}"
        text = str(value)
        if text.lower() in {"none", "nan", "nat"}:
            return ""
        return text
    except Exception:
        return str(value or "")


def _render_dark_table(
    df: pd.DataFrame,
    *,
    empty_message: str = "Ingen rader å vise ennå.",
    max_rows: int = 25,
    max_height_px: int = 320,
) -> None:
    """Render rows as compact dark cards, not a native/table dataframe.

    v18.5.21 hard-fix: several browsers/Streamlit builds kept painting table
    bodies as huge white rectangles even after v18.5.20 CSS. This renderer does
    not use native dataframe widget and does not use ``<table>``. It emits only small
    inline-styled div grids whose height follows the number of visible rows.
    """
    if df is None or df.empty:
        st.markdown(
            f'<div class="ai-universe-empty-note" style="border:1px dashed rgba(250,204,21,.45);background:rgba(250,204,21,.08);border-radius:12px;padding:.55rem .70rem;color:#fde68a;font-size:.78rem;font-weight:780;margin:.25rem 0 .45rem 0;">{escape(empty_message)}</div>',
            unsafe_allow_html=True,
        )
        return

    visible = df.head(max_rows).copy()
    columns = [str(c) for c in visible.columns]
    col_count = max(1, len(columns))
    min_width = max(760, min(1800, 128 * col_count))
    # No fixed blank body: just enough height for the rows that exist, capped.
    row_count = max(1, len(visible.index))
    dynamic_height = min(int(max_height_px), 48 + row_count * 42)
    grid = f"repeat({col_count}, minmax(110px, 1fr))"

    header_cells = "".join(
        f'<div style="padding:.40rem .50rem;color:#bae6fd;font-size:.78rem;font-weight:950;text-transform:uppercase;letter-spacing:.015em;white-space:nowrap;border-right:1px solid rgba(125,211,252,.13);">{escape(col)}</div>'
        for col in columns
    )

    rows_html: List[str] = []
    for _, row in visible.iterrows():
        cells = "".join(
            f'<div style="padding:.40rem .50rem;color:#e5edf8;font-size:.82rem;font-weight:760;line-height:1.30;overflow-wrap:anywhere;border-right:1px solid rgba(148,163,184,.10);">{escape(_format_table_cell(row.get(col)))}</div>'
            for col in visible.columns
        )
        rows_html.append(
            f'<div class="ai-universe-row-grid" style="display:grid;grid-template-columns:{grid};min-width:{min_width}px;background:rgba(15,23,42,.86);border-top:1px solid rgba(148,163,184,.13);">{cells}</div>'
        )

    overflow_note = ""
    total_rows = len(df.index)
    if total_rows > len(visible.index):
        overflow_note = (
            f'<div style="color:#cbd5e1;font-size:.80rem;margin:-.12rem 0 .48rem .15rem;opacity:.92;">Viser {len(visible.index)} av {total_rows} rader. '
            'Bruk filtre eller Top Picks for å korte ned listen.</div>'
        )

    html = (
        f'<div class="ai-universe-no-white-box" style="width:100%;max-height:{dynamic_height}px;overflow:auto;border:1px solid rgba(56,189,248,.28);border-radius:12px;background:#020617;margin:.28rem 0 .50rem 0;box-shadow:none;">'
        f'<div class="ai-universe-row-grid ai-universe-row-head" style="display:grid;grid-template-columns:{grid};min-width:{min_width}px;background:rgba(8,47,73,.98);position:sticky;top:0;z-index:2;border-bottom:1px solid rgba(125,211,252,.26);">{header_cells}</div>'
        f'{"".join(rows_html)}'
        '</div>'
        f'{overflow_note}'
    )
    st.markdown(html, unsafe_allow_html=True)


def _display_limit_choice_v1864d(key: str, total_rows: int) -> tuple[str, int]:
    options = ["10", "15", "20", "30", "Alle"]
    default = "Alle" if int(total_rows or 0) <= 60 else "30"
    choice = st.selectbox(
        "Vis antall rader",
        options,
        index=options.index(default),
        key=f"{key}_display_limit_v1864d",
        help="Endrer bare visningen. Pakken som sendes videre endres ikke.",
    )
    return choice, int(total_rows or 0) if choice == "Alle" else int(choice)


def _clamp_slider_state_v1864e(key: str, minimum: int, maximum: int, fallback: int) -> int:
    safe_min = int(minimum)
    safe_max = max(safe_min, int(maximum))
    safe_fallback = min(max(int(fallback), safe_min), safe_max)
    try:
        current_int = int(st.session_state.get(key, safe_fallback))
    except Exception:
        current_int = safe_fallback
    clamped = min(max(current_int, safe_min), safe_max)
    if st.session_state.get(key) != clamped:
        st.session_state[key] = clamped
    return clamped



AI_UNIVERSE_VISIBLE_PROGRESS_KEY = "ai_universe_visible_progress_v18526"


def _progress_panel_html(*, title: str, step: int, total: int, text: str, running: bool = True, ok: bool = True) -> str:
    pct = min(100, max(0, int(round((step / max(1, total)) * 100))))
    border = "rgba(56,189,248,.82)" if running else ("rgba(34,197,94,.60)" if ok else "rgba(250,204,21,.62)")
    glow = "rgba(14,165,233,.26)" if running else "rgba(34,197,94,.14)"
    icon = (
        '<span style="width:21px;height:21px;border:4px solid rgba(125,211,252,.24);border-top-color:#38bdf8;border-radius:999px;display:inline-block;animation:aiUniverseSpin .72s linear infinite;flex:0 0 auto;"></span>'
        if running
        else ("<span style='color:#bbf7d0;font-size:1.1rem;font-weight:950;'>✅</span>" if ok else "<span style='color:#fde68a;font-size:1.1rem;font-weight:950;'>⚠️</span>")
    )
    return (
        '<style>@keyframes aiUniverseSpin{to{transform:rotate(360deg)}}</style>'
        f'<div class="ai-universe-visible-progress" style="position:relative;z-index:80;border:2px solid {border};background:linear-gradient(180deg,rgba(7,89,133,.78),rgba(15,23,42,.98));border-radius:18px;padding:.86rem .95rem;margin:.55rem 0 .75rem 0;color:#e5edf8;box-shadow:0 14px 32px {glow};">'
        '<div style="display:flex;align-items:center;gap:.78rem;margin-bottom:.58rem;">'
        f'{icon}'
        f'<span style="font-weight:1000;color:#f8fafc;font-size:1rem;">{escape(title)}</span>'
        f'<span style="color:#bae6fd;font-weight:950;border:1px solid rgba(125,211,252,.35);background:rgba(8,47,73,.58);border-radius:999px;padding:.15rem .50rem;">{step}/{total}</span>'
        f'<span style="color:#cbd5e1;font-weight:820;">{escape(text)}</span>'
        '</div>'
        '<div style="height:11px;width:100%;border-radius:999px;background:rgba(15,23,42,.95);overflow:hidden;border:1px solid rgba(148,163,184,.22);">'
        f'<div style="height:100%;width:{pct}%;background:linear-gradient(90deg,#06b6d4,#38bdf8,#22c55e);border-radius:999px;transition:width .28s ease;"></div>'
        '</div>'
        '</div>'
    )


def _render_progress_snapshot() -> None:
    payload = st.session_state.get(AI_UNIVERSE_VISIBLE_PROGRESS_KEY)
    if not isinstance(payload, Mapping):
        return
    st.markdown(
        _progress_panel_html(
            title=str(payload.get("title") or "Smart AI-utvalg"),
            step=int(payload.get("step") or 1),
            total=int(payload.get("total") or 4),
            text=str(payload.get("text") or "Klar"),
            running=bool(payload.get("running", False)),
            ok=bool(payload.get("ok", True)),
        ),
        unsafe_allow_html=True,
    )


def _render_progress_step(holder: Any, progress: Any, *, title: str, step: int, total: int, text: str) -> None:
    """Show a sticky-looking, very visible run panel with spinner and progress bar."""
    pct = min(1.0, max(0.0, step / max(1, total)))
    st.session_state[AI_UNIVERSE_VISIBLE_PROGRESS_KEY] = {
        "title": f"🔄 Kjører {title}",
        "step": int(step),
        "total": int(total),
        "text": text,
        "running": True,
        "ok": True,
    }
    holder.markdown(
        _progress_panel_html(title=f"🔄 Kjører {title}", step=step, total=total, text=text, running=True, ok=True),
        unsafe_allow_html=True,
    )
    try:
        progress.progress(pct, text=f"{step}/{total} {text}")
    except TypeError:
        try:
            progress.progress(pct)
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
    try:
        # Give Streamlit/browser time to paint the status before the next blocking step.
        time.sleep(0.55)
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)


def _finish_progress(holder: Any, progress: Any, *, title: str, text: str, ok: bool = True) -> None:
    st.session_state[AI_UNIVERSE_VISIBLE_PROGRESS_KEY] = {
        "title": title,
        "step": 4,
        "total": 4,
        "text": text,
        "running": False,
        "ok": bool(ok),
    }
    holder.markdown(
        _progress_panel_html(title=title, step=4, total=4, text=text, running=False, ok=ok),
        unsafe_allow_html=True,
    )
    try:
        progress.empty()
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)


def _existing_tickers_by_scope_from_state(session_state: Mapping[str, Any]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    latest_rankings = session_state.get("latest_rankings_v148", {}) or {}
    for source, rows in latest_rankings.items():
        tickers: List[str] = []
        if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
            for row in rows:
                if isinstance(row, Mapping):
                    ticker = _normalize_ticker(row.get("ticker") or row.get("symbol"))
                    if ticker:
                        tickers.append(ticker)
        if tickers:
            out[str(source)] = tickers
            if str(source).startswith("TopPicks"):
                out.setdefault("Top Picks", []).extend(tickers)
            if str(source).startswith("SmartAI") or str(source).startswith("Smart AI"):
                out.setdefault("Smart AI-utvalg", []).extend(tickers)
    watchlist = [_normalize_ticker(x) for x in (session_state.get("latest_watchlist_tickers_v156", []) or [])]
    if watchlist:
        out["Watchlist"] = [x for x in watchlist if x]
    return out


def _store_smart_result_in_rankings(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    services = build_service_registry(st.session_state)
    ranked_rows = services.universe.store_result_as_rankings(result)
    return ranked_rows


def _picker_result_summary_rows(result: Mapping[str, Any]) -> List[Dict[str, str]]:
    if not result:
        return [
            {
                "label": "Picker-status",
                "value": "Tom",
                "detail": "Velg kilde eller manuell liste for å bygge en tickerliste/univers. Scorede kandidater lages først når Smart AI-utvalg kjøres.",
                "kind": "warn",
            }
        ]
    tickers = result.get("tickers") or [row.get("ticker") for row in result.get("candidates", []) if isinstance(row, Mapping) and row.get("ticker")]
    source = str(result.get("source") or (result.get("summary") or {}).get("source") or "Smart Universe Picker")
    reason = str(result.get("picker_reason") or (result.get("summary") or {}).get("reason") or "")
    return [
        {
            "label": "Picker-kilde",
            "value": source,
            "detail": reason or "Valgt kilde er løst til en tickerliste/univers. Dette er ikke en ny scoret kandidatliste.",
            "kind": "ok" if tickers else "warn",
        },
        {
            "label": "Tickerliste / univers",
            "value": f"{len(tickers)} tickere",
            "detail": (_safe_join(tickers[:12], empty="Ingen") + (" …" if len(tickers) > 12 else "")) + " · Usortert arbeidsliste, ikke scorede kandidater.",
            "kind": "ok" if tickers else "warn",
        },
        {
            "label": "Dataflyt",
            "value": "Kan aktiveres",
            "detail": "Listen kan settes som aktivt aksjeunivers eller sendes videre. Scorede kandidater krever Smart AI-utvalg.",
            "kind": "preview",
        },
    ]


def _smart_result_summary_rows(result: Mapping[str, Any]) -> List[Dict[str, str]]:
    if not result:
        return [
            {
                "label": "Scorede kandidater",
                "value": "Ikke kjørt ennå",
                "detail": "Trykk ‘Kjør Smart AI-utvalg nå’ for å gjøre tickerlisten/universet om til scorede kandidater.",
                "kind": "neutral",
            }
        ]
    errors = result.get("errors", []) or []
    return [
        {
            "label": "Smart AI-status",
            "value": str(result.get("status", "ukjent")),
            "detail": str(result.get("generated_at", "-")),
            "kind": "ok" if result.get("status") == "ok" else "warn",
        },
        {
            "label": "Input-univers",
            "value": f"{result.get('universe_size', 0)} tickere",
            "detail": f"Tickerlisten som ble analysert. Scannet: {result.get('scanned', 0)} · scorede før filter: {result.get('raw_candidates', 0)}",
            "kind": "preview",
        },
        {
            "label": "Scorede kandidater",
            "value": f"{result.get('matched_candidates', 0)} kandidater",
            "detail": str((result.get("summary") or {}).get("text", "")),
            "kind": "ok" if result.get("matched_candidates", 0) else "warn",
        },
        {
            "label": "Top Picks fra Smart AI",
            "value": _safe_join(result.get("top_tickers", []) or [], empty="Ingen"),
            "detail": "Disse kan sendes direkte til appens Top Picks eller watchlist.",
            "kind": "ok" if result.get("top_tickers") else "neutral",
        },
        {
            "label": "Feil/skip",
            "value": str(len(errors)),
            "detail": "Enkelte tickere kan mangle analysedata fra datakilde uten at hele kjøringen feiler.",
            "kind": "warn" if errors else "ok",
        },
    ]


def _count_ranked_items(latest_rankings: Mapping[str, Any], prefix: Optional[str] = None) -> int:
    total = 0
    for key, rows in (latest_rankings or {}).items():
        if prefix and not str(key).startswith(prefix):
            continue
        if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
            total += len(rows)
    return total


def _rank_source_summary(latest_rankings: Mapping[str, Any], max_items: int = 5) -> str:
    parts: List[str] = []
    for key, rows in (latest_rankings or {}).items():
        if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
            parts.append(f"{key}: {len(rows)}")
    if not parts:
        return "Ingen rangerte lister i cache"
    return ", ".join(parts[:max_items]) + (" …" if len(parts) > max_items else "")


def _safe_join(values: Sequence[Any], empty: str = "Ikke valgt") -> str:
    clean = [str(v) for v in values if str(v or "").strip()]
    return ", ".join(clean) if clean else empty


def build_universe_live_status(
    session_state: Mapping[str, Any],
    config: Mapping[str, Any],
    candidates: Sequence[UniverseCandidate],
    preview: Sequence[UniverseCandidate],
) -> List[Dict[str, str]]:
    """Build the live information shown in the status field.

    This is intentionally based on existing session/cache data only. It makes
    the module status useful without pretending that the future AI universe
    picker is already active.
    """
    latest_rankings = session_state.get("latest_rankings_v148", {}) or {}
    smart_result = session_state.get(AI_UNIVERSE_SMART_RESULT_KEY, {}) or session_state.get(AI_UNIVERSE_SMART_RESULT_LEGACY_KEY, {}) or {}
    watchlist = session_state.get("latest_watchlist_tickers_v156", []) or []
    paper_count = len([c for c in candidates if c.source == "Paper trading"])
    top_pick_count = _count_ranked_items(latest_rankings, prefix="TopPicks")
    pending = bool(session_state.get("pending_manual_changes_v16", False))
    update_reason = str(session_state.get("last_update_started_by_v148", "Oppstart / cache") or "Oppstart / cache")
    update_at = str(session_state.get("last_update_started_at_v148", "-") or "-")
    manual_ticker = _normalize_ticker(config.get("manual_ticker") or session_state.get("search_main_v157", ""))
    active_universe = session_state.get(ACTIVE_UNIVERSE_KEY, {}) or session_state.get("active_universe", {}) or {}
    active_tickers = active_universe.get("tickers", []) if isinstance(active_universe, Mapping) else []

    rows = [
        {
            "label": "Modulversjon",
            "value": AI_UNIVERSE_MODULE_VERSION,
            "detail": "Live statusfelt aktivt. Roadmap vises separat under detaljstatus.",
            "kind": "ok",
        },
        {
            "label": "Workspace-modus",
            "value": str(config.get("mode") or "Markedvalg"),
            "detail": "Valgt arbeidsmodus for Analyseuniverset.",
            "kind": "ok",
        },
        {
            "label": "Marked/kilder",
            "value": _safe_join(config.get("scopes") or []),
            "detail": "Disse kildene løses til en tickerliste/univers. Listen blir ikke scorede kandidater før Smart AI-utvalg kjøres.",
            "kind": "preview",
        },
        {
            "label": "Manuell ticker",
            "value": manual_ticker or "Ingen",
            "detail": "Manuell ticker fungerer som overstyring/enkeltaksje når den er satt.",
            "kind": "ok" if manual_ticker else "neutral",
        },
        {
            "label": "Aktivt aksjeunivers",
            "value": f"{len(active_tickers)} tickere" if active_tickers else "Ikke satt",
            "detail": (_safe_join(active_tickers[:10], empty="Trykk ‘Bruk som aktivt aksjeunivers’") + (" …" if len(active_tickers) > 10 else "")),
            "kind": "ok" if active_tickers else "warn",
        },
        {
            "label": "Preview-data funnet",
            "value": f"{len(candidates)} totalt / {len(preview)} etter filter",
            "detail": "Eksisterende cache/session-data for visning. Ikke en ny Smart AI-scoring.",
            "kind": "ok" if candidates else "warn",
        },
        {
            "label": "Watchlist",
            "value": f"{len(watchlist)} tickere",
            "detail": ", ".join([_normalize_ticker(x) for x in list(watchlist)[:8]]) or "Ingen watchlist-data registrert ennå.",
            "kind": "ok" if watchlist else "warn",
        },
        {
            "label": "Top Picks-cache",
            "value": f"{top_pick_count} kandidater",
            "detail": "Scorede/rangerte kandidater som allerede ligger i TopPicks_* cache.",
            "kind": "ok" if top_pick_count else "warn",
        },
        {
            "label": "Paper trading",
            "value": f"{paper_count} åpne posisjoner",
            "detail": "Kun visning/preview. Modulen starter ikke automatisk handel.",
            "kind": "ok" if paper_count else "neutral",
        },
        {
            "label": "Aktive filtre",
            "value": f"Risiko ≤ {config.get('max_risk', 'Middels')} · score ≥ {float(config.get('min_top_pick_score', 0) or 0):.1f} · strength ≥ {float(config.get('min_strength', 0) or 0):.0f}",
            "detail": f"Sektor: {_safe_join(config.get('sectors') or ['Alle sektorer'])}",
            "kind": "preview",
        },
        {
            "label": "Datakilder",
            "value": f"{_count_ranked_items(latest_rankings)} rangerte rader",
            "detail": _rank_source_summary(latest_rankings),
            "kind": "ok" if latest_rankings else "warn",
        },
        {
            "label": "Smart AI-scoring",
            "value": f"{smart_result.get('matched_candidates', 0)} scorede kandidater" if smart_result else "Ikke kjørt",
            "detail": str(smart_result.get("generated_at", "Trykk ‘Kjør Smart AI-utvalg nå’ for å lage scorede kandidater fra tickerlisten.")),
            "kind": "ok" if smart_result.get("matched_candidates", 0) else "neutral",
        },
        {
            "label": "Siste tunge oppdatering",
            "value": update_at,
            "detail": update_reason,
            "kind": "neutral",
        },
        {
            "label": "Ventende endringer",
            "value": "Ja" if pending else "Nei",
            "detail": str(session_state.get("pending_manual_changes_reason_v16", "Ingen ventende endringer") or "Ingen ventende endringer"),
            "kind": "warn" if pending else "ok",
        },
    ]
    return rows


def build_universe_selection_summary(
    config: Mapping[str, Any],
    candidates: Sequence[UniverseCandidate],
    preview: Sequence[UniverseCandidate],
    saved: bool = False,
) -> List[Dict[str, str]]:
    """Build a visible summary of the choices made in the form.

    This answers the practical UI question: the form choices are not a hidden
    result. They become a selected universe setup, and the available existing
    candidates are shown as a preview underneath.
    """
    manual_ticker = _normalize_ticker(config.get("manual_ticker"))
    manual_tickers = list(config.get("manual_tickers") or _parse_manual_ticker_list(config.get("manual_list")))
    saved_text = "Lagret som ventende" if saved else "Forhåndsvisning – ikke lagret"
    selected_sectors = config.get("sectors") or ["Alle sektorer"]
    scopes = config.get("scopes") or []
    mode = str(config.get("mode") or "Markedvalg")

    return [
        {
            "label": "Valgt modus",
            "value": mode,
            "detail": "Dette styrer hvilken del av Analyseuniverset oppsettet gjelder.",
            "kind": "ok",
        },
        {
            "label": "Valgte kilder",
            "value": _safe_join(scopes),
            "detail": "Brukes til å bygge tickerliste/univers og avgrense preview. Dette er ikke en scoret kandidatkjøring.",
            "kind": "preview",
        },
        {
            "label": "Enkeltaksje",
            "value": manual_ticker or "Ikke satt",
            "detail": "Når modus er Enkeltaksje, blir dette et én-ticker-univers.",
            "kind": "ok" if manual_ticker else "neutral",
        },
        {
            "label": "Manuell liste",
            "value": f"{len(manual_tickers)} tickere" if manual_tickers else "Ikke satt",
            "detail": _safe_join(manual_tickers[:10], empty="Brukes når modus er Manuell liste") + (" …" if len(manual_tickers) > 10 else ""),
            "kind": "ok" if manual_tickers else "neutral",
        },
        {
            "label": "Filtervalg",
            "value": f"Risiko ≤ {config.get('max_risk', 'Middels')}",
            "detail": f"Score ≥ {float(config.get('min_top_pick_score', 0) or 0):.1f} · Strength ≥ {float(config.get('min_strength', 0) or 0):.0f} · Sektor: {_safe_join(selected_sectors)}",
            "kind": "preview",
        },
        {
            "label": "Preview nå",
            "value": f"{len(preview)} av {len(candidates)} eksisterende kandidater matcher",
            "detail": "Viser bare eksisterende cache/session-kandidater under. Scorede Smart AI-kandidater lages først når du trykker Kjør.",
            "kind": "ok" if preview else "warn",
        },
        {
            "label": "Lagringsstatus",
            "value": saved_text,
            "detail": "Knappen lagrer oppsettet. ‘Bruk som aktivt aksjeunivers’ gjør tickerlisten til felles valgkjerne for appen.",
            "kind": "ok" if saved else "neutral",
        },
    ]


def _render_compact_status_rows(rows: Sequence[Mapping[str, str]], *, variant: str) -> None:
    """Render compact dark rows with inline CSS only.

    v18.5.22 final white-box fix: do not rely on external CSS classes for the
    default result/status panels. Every visible row gets inline dark styling and
    the panel height is bounded by real content. This avoids Streamlit/browser
    theme fallbacks that have produced large white empty rectangles.
    """
    if not rows:
        st.markdown(
            '<div style="border:1px dashed rgba(250,204,21,.45);background:rgba(250,204,21,.08);border-radius:10px;padding:.50rem .65rem;color:#fde68a;font-size:.84rem;font-weight:800;margin:.25rem 0 .45rem 0;">Ingen resultater ennå.</div>',
            unsafe_allow_html=True,
        )
        return

    def border_for(kind: str) -> str:
        if kind == "ok":
            return "rgba(34,197,94,.30)"
        if kind == "warn":
            return "rgba(250,204,21,.60)"
        if kind == "preview":
            return "rgba(56,189,248,.50)"
        return "rgba(148,163,184,.30)"

    row_html: List[str] = []
    for row in list(rows)[:12]:
        kind = str(row.get("kind", "neutral") or "neutral")
        label = escape(str(row.get("label", "")))
        value = escape(str(row.get("value", "")))
        detail = escape(str(row.get("detail", "")))
        border = border_for(kind)
        detail_html = (
            f'<span class="ai-universe-compact-detail">{detail}</span>'
            if detail
            else ""
        )
        row_html.append(
            f'<div class="ai-universe-compact-row {escape(kind)}" style="border-color:{border};">'
            f'<span class="ai-universe-compact-label">{label}</span>'
            f'<span class="ai-universe-compact-value">{value}</span>'
            f'{detail_html}'
            f'</div>'
        )

    st.markdown(
        f'<div data-ai-universe-panel="{escape(variant)}" class="ai-universe-compact-panel">'
        + "".join(row_html)
        + "</div>",
        unsafe_allow_html=True,
    )

def _render_selection_summary_panel(rows: Sequence[Mapping[str, str]]) -> None:
    _render_compact_status_rows(rows, variant="selection")


def _render_live_status_panel(rows: Sequence[Mapping[str, str]]) -> None:
    _render_compact_status_rows(rows, variant="live")


def _status_badge_class(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if "operativ" in normalized:
        return "ui"
    if "ui" in normalized:
        return "ui"
    if "delvis" in normalized:
        return "partial"
    if "arkitektur" in normalized:
        return "arch"
    if "preview" in normalized:
        return "preview"
    if "planlagt" in normalized:
        return "planned"
    return ""


def _render_feature_status_panel() -> None:
    """Render status as dark cards instead of Streamlit dataframe.

    The app normally runs in dark mode. A native dataframe can render with a
    bright white background in some Streamlit themes, which made the status
    section look empty. These cards make the architecture/roadmap status
    visible regardless of dataframe styling.
    """
    cards: List[str] = []
    for name, status, comment in FEATURE_STATUS_ROWS:
        badge_class = _status_badge_class(status)
        cards.append(
            f'''
            <div class="ai-universe-status-card">
                <div class="ai-universe-status-head">
                    <span class="ai-universe-status-name">{escape(str(name))}</span>
                    <span class="ai-universe-status-badge {badge_class}">{escape(str(status))}</span>
                </div>
                <div class="ai-universe-status-text">{escape(str(comment))}</div>
            </div>
            '''
        )
    st.markdown(
        '<div class="ai-universe-status-grid">' + "".join(cards) + "</div>",
        unsafe_allow_html=True,
    )


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
            font-size: .90rem;
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
            font-size: .82rem;
            font-weight: 850;
            color: #e2e8f0;
        }
        .ai-universe-pill.plan { border-color: rgba(250,204,21,.55); color:#fde68a; }
        .ai-universe-compact-panel {
            display: flex;
            flex-direction: column;
            gap: .38rem;
            margin: .35rem 0 .70rem 0;
            width: 100%;
            max-width: 100%;
        }
        .ai-universe-compact-row {
            display: grid;
            grid-template-columns: minmax(120px, 180px) minmax(110px, 210px) 1fr;
            gap: .55rem;
            align-items: center;
            border: 1px solid rgba(56,189,248,.34);
            background: linear-gradient(180deg, rgba(8,47,73,.40), rgba(15,23,42,.78));
            border-radius: 12px;
            padding: .46rem .58rem;
            min-height: 0;
            box-shadow: none;
        }
        .ai-universe-compact-row.ok { border-color: rgba(34,197,94,.36); }
        .ai-universe-compact-row.warn { border-color: rgba(250,204,21,.58); background: linear-gradient(180deg, rgba(66,52,8,.38), rgba(15,23,42,.80)); }
        .ai-universe-compact-row.preview { border-color: rgba(56,189,248,.50); }
        .ai-universe-compact-label {
            color:#bae6fd !important;
            font-size:.78rem;
            text-transform: uppercase;
            letter-spacing:.04em;
            font-weight: 950;
            white-space: nowrap;
        }
        .ai-universe-compact-value {
            color:#f8fafc !important;
            font-size:.92rem;
            font-weight: 950;
            line-height:1.2;
            overflow-wrap:anywhere;
        }
        .ai-universe-compact-detail {
            color:#cbd5e1 !important;
            font-size:.82rem;
            line-height:1.36;
            overflow-wrap:anywhere;
        }
        @media (max-width: 900px) {
            .ai-universe-compact-row {
                grid-template-columns: 1fr;
                gap: .14rem;
                align-items: start;
            }
        }
        .ai-universe-choice-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(235px, 1fr));
            gap: .52rem;
            margin: .45rem 0 .95rem 0;
        }
        .ai-universe-choice-card {
            border: 1px solid rgba(56,189,248,.42);
            background: linear-gradient(180deg, rgba(8,47,73,.50), rgba(15,23,42,.86));
            border-radius: 16px;
            padding: .68rem .75rem;
            min-height: 0;
            box-shadow: 0 10px 24px rgba(0,0,0,.18);
        }
        .ai-universe-choice-card.ok { border-color: rgba(34,197,94,.36); }
        .ai-universe-choice-card.warn { border-color: rgba(250,204,21,.62); background: linear-gradient(180deg, rgba(66,52,8,.48), rgba(15,23,42,.84)); }
        .ai-universe-choice-card.preview { border-color: rgba(56,189,248,.58); }
        .ai-universe-choice-label {
            color:#bae6fd;
            font-size:.80rem;
            text-transform: uppercase;
            letter-spacing:.04em;
            font-weight: 950;
            margin-bottom:.16rem;
        }
        .ai-universe-choice-value {
            color:#f8fafc;
            font-size:1rem;
            font-weight: 950;
            line-height:1.15;
            margin-bottom:.25rem;
        }
        .ai-universe-choice-detail {
            color:#cbd5e1;
            font-size:.84rem;
            line-height:1.32;
            overflow-wrap:anywhere;
        }
        .ai-universe-live-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: .52rem;
            margin: .45rem 0 .85rem 0;
        }
        .ai-universe-live-card {
            border: 1px solid rgba(148,163,184,.26);
            background: linear-gradient(180deg, rgba(15,23,42,.92), rgba(2,6,23,.80));
            border-radius: 15px;
            padding: .64rem .72rem;
            min-height: 0;
            box-shadow: 0 10px 24px rgba(0,0,0,.18);
        }
        .ai-universe-live-card.ok { border-color: rgba(34,197,94,.36); }
        .ai-universe-live-card.warn { border-color: rgba(250,204,21,.58); background: linear-gradient(180deg, rgba(66,52,8,.42), rgba(15,23,42,.82)); }
        .ai-universe-live-card.preview { border-color: rgba(56,189,248,.48); }
        .ai-universe-live-label {
            color:#94a3b8;
            font-size:.80rem;
            text-transform: uppercase;
            letter-spacing:.04em;
            font-weight: 950;
            margin-bottom:.16rem;
        }
        .ai-universe-live-value {
            color:#f8fafc;
            font-size:.98rem;
            font-weight: 950;
            line-height:1.15;
            margin-bottom:.25rem;
        }
        .ai-universe-live-detail {
            color:#cbd5e1;
            font-size:.84rem;
            line-height:1.32;
            overflow-wrap:anywhere;
        }
        .ai-universe-pill.ok { border-color: rgba(34,197,94,.36); color:#bbf7d0; }
        .ai-universe-pill.active { background: rgba(16,185,129,.18); box-shadow: 0 0 0 1px rgba(34,197,94,.18) inset; }
        .ai-universe-status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
            gap: .5rem;
            margin: .5rem 0 .75rem 0;
        }
        .ai-universe-status-card {
            border: 1px solid rgba(148,163,184,.22);
            background: rgba(15, 23, 42, .72);
            border-radius: 14px;
            padding: .62rem .68rem;
            min-height: 0;
        }
        .ai-universe-status-head {
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:.45rem;
            margin-bottom:.32rem;
        }
        .ai-universe-status-name {
            font-weight: 900;
            color: #f8fafc;
            font-size: .94rem;
        }
        .ai-universe-status-badge {
            border-radius: 999px;
            padding: .15rem .42rem;
            font-size: .76rem;
            font-weight: 900;
            white-space: nowrap;
            border: 1px solid rgba(148,163,184,.30);
            color:#e2e8f0;
        }
        .ai-universe-status-badge.ui { border-color: rgba(34,197,94,.38); color:#bbf7d0; }
        .ai-universe-status-badge.partial { border-color: rgba(56,189,248,.52); color:#bae6fd; }
        .ai-universe-status-badge.arch { border-color: rgba(167,139,250,.52); color:#ddd6fe; }
        .ai-universe-status-badge.preview { border-color: rgba(250,204,21,.55); color:#fde68a; }
        .ai-universe-status-badge.planned { border-color: rgba(248,113,113,.52); color:#fecaca; }
        .ai-universe-status-text {
            color:#cbd5e1;
            font-size:.84rem;
            line-height:1.33;
        }
        .ai-universe-empty-note {
            border: 1px dashed rgba(250,204,21,.45);
            background: rgba(250,204,21,.08);
            border-radius: 12px;
            padding: .62rem .75rem;
            color: #fde68a;
            font-size: .86rem;
            font-weight: 780;
            margin-top: .25rem;
        }

        .ai-universe-table-wrap {
            width: 100%;
            overflow: auto;
            border: 1px solid rgba(34,197,94,.42);
            border-radius: 12px;
            background: rgba(2, 6, 23, .92);
            margin: .32rem 0 .58rem 0;
            box-shadow: none;
        }
        .ai-universe-table {
            width: 100%;
            border-collapse: collapse;
            color: #e5edf8;
            font-size: .84rem;
            line-height: 1.25;
            min-width: 900px;
        }
        .ai-universe-table thead th {
            position: sticky;
            top: 0;
            z-index: 2;
            background: rgba(8, 47, 73, .98);
            color: #bae6fd;
            text-align: left;
            font-weight: 950;
            letter-spacing: .02em;
            border-bottom: 1px solid rgba(125,211,252,.30);
            padding: .40rem .46rem;
            white-space: nowrap;
        }
        .ai-universe-table tbody td {
            background: rgba(15, 23, 42, .72);
            border-bottom: 1px solid rgba(148,163,184,.16);
            color: #e5edf8;
            padding: .34rem .46rem;
            vertical-align: top;
            max-width: 380px;
            overflow-wrap: anywhere;
        }
        .ai-universe-table tbody tr:nth-child(even) td {
            background: rgba(11, 21, 39, .76);
        }
        .ai-universe-table-note {
            color: #cbd5e1;
            font-size: .80rem;
            margin: -.20rem 0 .55rem .15rem;
            opacity: .88;
        }
        .ai-universe-no-white-box,
        .ai-universe-no-white-box * {
            box-sizing: border-box !important;
            background-clip: padding-box !important;
        }
        .ai-universe-row-grid {
            color: #e5edf8 !important;
            min-height: 0 !important;
        }


        /* v18.5.26: local hard guard for the manual ticker field. Chrome/Edge autofill can paint the BaseWeb wrapper white. */
        div[data-testid="stTextInput"],
        div[data-testid="stTextInput"] > div,
        div[data-testid="stTextInput"] > div > div,
        div[data-baseweb="input"],
        div[data-baseweb="input"] > div,
        div[data-baseweb="base-input"],
        div[data-baseweb="base-input"] > div {
            background: #0f172a !important;
            background-color: #0f172a !important;
            color: #f8fafc !important;
            -webkit-text-fill-color: #f8fafc !important;
            opacity: 1 !important;
            border-color: rgba(125, 211, 252, .50) !important;
            box-shadow: none !important;
        }
        div[data-testid="stTextInput"]:focus-within,
        div[data-baseweb="input"]:focus-within,
        div[data-baseweb="input"]:focus-within > div,
        div[data-baseweb="base-input"]:focus-within,
        div[data-baseweb="base-input"]:focus-within > div {
            background: #0b1220 !important;
            background-color: #0b1220 !important;
            border-color: rgba(56, 189, 248, .96) !important;
            box-shadow: 0 0 0 1px rgba(56, 189, 248, .45) !important;
        }
        div[data-testid="stTextInput"] input,
        div[data-baseweb="input"] input,
        div[data-baseweb="base-input"] input {
            background: transparent !important;
            background-color: transparent !important;
            color: #f8fafc !important;
            -webkit-text-fill-color: #f8fafc !important;
            caret-color: #7dd3fc !important;
            font-weight: 900 !important;
            text-shadow: none !important;
        }
        input:-webkit-autofill,
        input:-webkit-autofill:hover,
        input:-webkit-autofill:focus,
        input:-webkit-autofill:active {
            -webkit-text-fill-color: #f8fafc !important;
            caret-color: #7dd3fc !important;
            box-shadow: 0 0 0 1000px #0f172a inset !important;
            -webkit-box-shadow: 0 0 0 1000px #0f172a inset !important;
            transition: background-color 999999s ease-in-out 0s, color 999999s ease-in-out 0s !important;
        }

        /* v18.5.22 hard guard against leftover native Streamlit white panels. */
        div[data-testid="stDataFrame"] > div,
        div[data-testid="stDataFrame"] iframe,
        div[data-testid="stDataFrame"] [class*="stDataFrame"] {
            background: #020617 !important;
            color: #e5edf8 !important;
            max-height: 340px !important;
            min-height: 0 !important;
        }
        .ai-universe-no-white-box {
            height: auto !important;
            min-height: 0 !important;
            max-height: 340px !important;
        }
        /* v18.5.26 final null-panel guard: no empty white expander/dataframe regions in Analyseunivers. */
        div[data-testid="stExpander"],
        div[data-testid="stExpander"] details,
        div[data-testid="stExpander"] div[role="region"],
        div[data-testid="stExpander"] [data-testid="stVerticalBlock"],
        div[data-testid="stExpander"] [data-testid="stElementContainer"] {
            background: #020617 !important;
            background-color: #020617 !important;
            color: #e5edf8 !important;
        }
        div[data-testid="stDataFrame"],
        div[data-testid="stDataFrame"] > div,
        div[data-testid="stDataFrame"] iframe,
        div[data-testid="stDataFrame"] [class*="stDataFrame"],
        div[data-testid="stTable"],
        div[data-testid="stTable"] * {
            background: #020617 !important;
            background-color: #020617 !important;
            color: #e5edf8 !important;
            min-height: 0 !important;
        }
        div[data-testid="stDataFrame"] iframe {
            max-height: 280px !important;
            border: 1px solid rgba(56,189,248,.24) !important;
            border-radius: 12px !important;
        }
        .ai-universe-visible-progress {
            background-color: #0f172a !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _set_pending_change(reason: str) -> None:
    st.session_state["pending_manual_changes_v16"] = True
    st.session_state["pending_manual_changes_reason_v16"] = reason


def _default_config() -> Dict[str, Any]:
    if not st.session_state.get("ai_universe_default_reset_v1863u"):
        if st.session_state.get("ai_universe_scopes_draft_v1853") in (["USA"], ("USA",)):
            st.session_state["ai_universe_scopes_draft_v1853"] = []
        if str(st.session_state.get("ai_universe_manual_ticker_draft_v18523") or "").upper() in {"AAPL", "STB.OL"}:
            st.session_state["ai_universe_manual_ticker_draft_v18523"] = ""
        st.session_state["ai_universe_default_reset_v1863u"] = True
    mode = st.session_state.get("ai_universe_mode_draft_v1853", "Markedvalg")
    if mode == "Smart AI-utvalg (planlagt)":
        mode = "Smart AI-utvalg"
        try:
            st.session_state["ai_universe_mode_draft_v1853"] = mode
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)
    return {
        "mode": mode,
        "scopes": st.session_state.get("ai_universe_scopes_draft_v1853", []),
        "manual_ticker": st.session_state.get("ai_universe_manual_ticker_draft_v18523", ""),
        "manual_list": st.session_state.get("ai_universe_manual_list_draft_v18517", ""),
        "max_count": int(st.session_state.get("max_count_main_v157", 30) or 30),
        "min_top_pick_score": float(st.session_state.get("min_top_pick_score_main_v157", 6.5) or 6.5),
        "use_news": bool(st.session_state.get("use_news_main_v157", False)),
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

    active_mode = str(current.get("mode") or "Markedvalg")
    mode_pills = []
    for pill_mode in ["Enkeltaksje", "Markedvalg", "Multi-marked", "Top Picks", "Watchlist", "Paper trading", "Portefølje", "Manuell liste"]:
        pill_class = "ai-universe-pill ok active" if pill_mode == active_mode else "ai-universe-pill"
        mode_pills.append(f'<span class="{pill_class}">{escape(pill_mode)}</span>')
    mode_pills_html = "".join(mode_pills)

    st.markdown(
        f"""
        <div class="ai-universe-card">
            <div class="ai-universe-title">🎯 Analyseunivers som AI-modul</div>
            <div class="ai-universe-sub">
                Arkitekturen er nå koblet til en operativ Smart AI-motor: valgt univers kan kjøres, scores,
                risikofiltreres, momentumfiltreres og rangeres. Portefølje-/workspace-automatisering bygges videre i neste fase.
            </div>
            <div class="ai-universe-pill-row">
                <span class="ai-universe-pill ok">UI-workspace aktivt</span>
                {mode_pills_html}
                <span class="ai-universe-pill ok">Smart AI-utvalg: service-koblet Fase 2</span>
                <span class="ai-universe-pill ok">{AI_UNIVERSE_MODULE_VERSION}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        from services.analysis_pipeline_service import PIPELINE_PENDING_NAV_KEY, get_analysis_pipeline_service, stage_wizard_info
        from services.state_service import get_state_service
        from services.storage_service import get_storage_service

        pipeline = get_analysis_pipeline_service(
            state_service=get_state_service(st.session_state),
            storage_service=get_storage_service(),
        )
        info = stage_wizard_info("smart_ai")
        inp = pipeline.load_stage_input("smart_ai")
        out = pipeline.load_stage_output("smart_ai")
        inp_count = int(inp.get("candidate_count") or 0)
        out_count = int(out.get("candidate_count") or 0)
        if int(inp.get("candidate_count") or 0) > 0 and str(current.get("mode") or "") in {"", "Markedvalg"}:
            current["mode"] = "Analyseflyt input"
            current["scopes"] = ["Analyseflyt input"]
            st.session_state["ai_universe_mode_draft_v1853"] = "Analyseflyt input"
            st.session_state["ai_universe_scopes_draft_v1853"] = ["Analyseflyt input"]
        st.markdown(
            f"""
            <div style="border:1px solid rgba(56,189,248,.52);border-radius:8px;padding:.62rem .72rem;margin:.4rem 0;background:rgba(15,23,42,.72);">
              <div style="display:flex;justify-content:space-between;gap:.65rem;flex-wrap:wrap;align-items:center;">
                <b>{escape(str(info.get('wizard_label') or 'Test 3 av 10: Smart AI-filter'))}</b>
                <span>{inp_count} inn | {out_count} ut</span>
                <span>Auto-kjoring: av</span>
              </div>
              <div style="font-size:.82rem;color:rgba(226,232,240,.86);margin-top:.22rem;">Kjor Smart AI-utvalg eksplisitt, og send ferdige kandidater videre til Top Picks.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        def _open_top_picks_stage_v1864g() -> None:
            target = stage_wizard_info("top_picks")
            st.session_state[PIPELINE_PENDING_NAV_KEY] = {
                "stage_id": "top_picks",
                "group": target.get("group") or "",
                "panel": target.get("panel_label") or "",
                "defaults": dict(target.get("defaults") or {}),
                "auto_run": False,
            }
            st.rerun()

        nav_prev_col, nav_status_col = st.columns([1.0, 1.05])
        with nav_prev_col:
            if st.button("Forrige: Test 2 Marked/rangering", key="smart_ai_pipeline_prev_v1864b", width="stretch"):
                previous = stage_wizard_info("market_ranking")
                st.session_state[PIPELINE_PENDING_NAV_KEY] = {
                    "stage_id": "market_ranking",
                    "group": previous.get("group") or "",
                    "panel": previous.get("panel_label") or "",
                    "defaults": dict(previous.get("defaults") or {}),
                    "auto_run": False,
                }
                st.rerun()
        with nav_status_col:
            st.metric("Input / output", f"{inp_count} / {out_count}")
            st.caption("Input er kandidatpakken fra Test 2. Kjor-knappen ligger i Smart AI-utvalg-seksjonen under, slik at samme jobb ikke har to like knapper.")

        if out_count > 0:
            next_text = f"Smart AI-output er klar: {out_count} funn kan sendes til Test 4. Du kan ogsaa sende raa Test 2-input hvis du vil overstyre filteret."
        elif inp_count > 0:
            next_text = f"Ingen Smart AI-funn er klare. Du kan kjoere Smart AI, eller sende raa input fra Test 2 videre til Test 4."
        else:
            next_text = "Ingen inputpakke fra Test 2 er mottatt. Gaa tilbake til Test 2 og send kandidater hit forst."
        st.markdown(
            f"""
            <div style="border:1px solid rgba(56,189,248,.45);border-radius:8px;padding:.62rem .72rem;margin:.50rem 0;background:rgba(8,47,73,.34);">
              <b>Videre til Test 4</b>
              <div style="font-size:.82rem;color:rgba(226,232,240,.88);margin-top:.18rem;">{escape(next_text)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if out_count > 0:
            if st.button(
                f"Send {out_count} Smart AI-funn til Test 4 og aapne Top Picks",
                key="smart_ai_pipeline_send_findings_to_top_picks_v1864k",
                width="stretch",
                type="primary",
            ):
                result = pipeline.handoff_latest_output_to_next("smart_ai")
                if not result.ok:
                    st.warning(result.message)
                else:
                    _open_top_picks_stage_v1864g()
        elif inp_count > 0:
            st.caption("Smart AI har 0 funn. Fortsett likevel med inputpakken fra Test 2 for aa komme videre til Test 4.")
            if st.button(
                f"Fortsett med raa input fra Test 2 ({inp_count}) til Test 4",
                key="smart_ai_pipeline_send_raw_input_to_top_picks_v1864k",
                width="stretch",
                type="primary",
                help="Bruk dette hvis Smart AI-filteret gir 0 treff, eller hvis du vil sende hele inputpakken videre ufiltrert.",
            ):
                input_rows = pipeline.candidates_for_stage("smart_ai", prefer_output=False)
                result = pipeline.save_stage_output(
                    "smart_ai",
                    input_rows,
                    source_label="Smart AI-filter bypass",
                    context={
                        "bypass_reason": "zero_output_or_manual_continue",
                        "input_count": inp_count,
                        "note": "Bruker sendte inputpakken videre uten Smart AI-filter.",
                    },
                    max_items=len(input_rows),
                    auto_handoff=True,
                )
                if not result.ok:
                    st.warning(result.message)
                else:
                    _open_top_picks_stage_v1864g()
        else:
            st.button("Ingen input/output aa sende videre", key="smart_ai_pipeline_no_input_v1864k", width="stretch", disabled=True)
    except Exception as exc:
        st.caption(f"Analyseflyt-status kunne ikke vises: {exc}")

    saved_config = st.session_state.get(AI_UNIVERSE_STATE_KEY, {}) if isinstance(st.session_state.get(AI_UNIVERSE_STATE_KEY, {}), Mapping) else {}
    saved_mode = str(saved_config.get("mode") or "ikke lagret")
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;gap:.45rem;align-items:center;margin:.35rem 0 .55rem 0;">'
        f'<span style="border:1px solid rgba(56,189,248,.38);background:rgba(8,47,73,.40);border-radius:999px;padding:.24rem .55rem;color:#bae6fd;font-size:.76rem;font-weight:900;">Valgt nå: {escape(active_mode)}</span>'
        f'<span style="border:1px solid rgba(148,163,184,.25);background:rgba(15,23,42,.72);border-radius:999px;padding:.24rem .55rem;color:#cbd5e1;font-size:.76rem;font-weight:850;">Sist lagret: {escape(saved_mode)}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    with st.expander("Konfigurer Analyseunivers AI-modul", expanded=expanded):
        st.info(
            "Denne modulen er nå Smart Universe Picker: den velger og lagrer appens aktive aksjeunivers. "
            "Picker-resultatet er tickerliste/univers, ikke scorede kandidater. "
            "Smart AI-utvalg/scanning kjører fortsatt kun når du trykker på kjør-knappen."
        )

        # v18.6.3y: buffer config widgets so several choices can be changed
        # before Streamlit reruns the workspace.
        with st.form("ai_universe_config_form_v1863y", clear_on_submit=False):
            c1, c2, c3 = st.columns(3)
            with c1:
                mode = st.selectbox(
                    "Workspace-modus",
                    WORKSPACE_MODES,
                    index=WORKSPACE_MODES.index(current["mode"]) if current["mode"] in WORKSPACE_MODES else 1,
                    key="ai_universe_mode_draft_v1853",
                )
                current_scope_values = current["scopes"]
                if isinstance(current_scope_values, str):
                    current_scope_values = [current_scope_values]
                current_scopes = [x for x in current_scope_values if x in MARKET_SCOPES]
                if mode == "Markedvalg":
                    market_options = [NO_MARKET_SELECTION_LABEL] + MARKET_SCOPE_OPTIONS
                    default_market = current_scopes[0] if current_scopes and current_scopes[0] in MARKET_SCOPE_OPTIONS else NO_MARKET_SELECTION_LABEL
                    market_choice = st.selectbox(
                        "Marked",
                        market_options,
                        index=market_options.index(default_market),
                        key="ai_universe_market_single_v1863w",
                        help="Velg ett marked. Menyen lukker seg etter valg og starter ingen analyse.",
                    )
                    scopes = [] if market_choice == NO_MARKET_SELECTION_LABEL else [market_choice]
                elif mode == "Multi-marked":
                    st.caption("Velg flere markeder uten nedtrekksmeny.")
                    scopes = []
                    checkbox_markets = BASE_MARKET_SCOPES + ["Norden", "Alle"]
                    market_cols = st.columns(4)
                    for idx, market_name in enumerate(checkbox_markets):
                        with market_cols[idx % 4]:
                            if st.checkbox(
                                market_name,
                                value=market_name in current_scopes,
                                key=f"ai_universe_market_chip_{market_name}_v1863w",
                            ):
                                scopes.append(market_name)
                    if "Alle" in scopes:
                        scopes = ["Alle"]
                else:
                    scopes = [mode] if mode in MARKET_SCOPES else []
                    if mode in {"Top Picks", "Watchlist", "Paper trading", "Portefølje", "Manuell liste", "Smart AI-utvalg"}:
                        st.markdown(
                            f"<div class='ai-universe-empty-note'>Kilde: {escape(mode)}</div>",
                            unsafe_allow_html=True,
                        )
                st.session_state["ai_universe_scopes_draft_v1853"] = scopes
                manual_ticker = str(current["manual_ticker"] or "")
                if mode == "Enkeltaksje":
                    manual_ticker = st.text_input(
                        "Manuell ticker / enkeltaksje",
                        value=manual_ticker,
                        placeholder="F.eks. EQNR.OL, VOLV-B.ST, NOKIA.HE, NOVO-B.CO eller PETR4.SA",
                        key="ai_universe_manual_ticker_draft_v18523",
                    )
                _manual_ticker_preview = _normalize_ticker(manual_ticker)
                if mode == "Enkeltaksje":
                    st.markdown(
                        f'<div style="display:inline-flex;align-items:center;gap:.35rem;margin:.12rem 0 .35rem 0;padding:.28rem .55rem;border-radius:999px;border:1px solid rgba(34,197,94,.50);background:rgba(16,65,52,.62);color:#bbf7d0;font-weight:950;font-size:.78rem;">Aktiv ticker: {escape(_manual_ticker_preview or "ingen")}</div>',
                        unsafe_allow_html=True,
                    )
                manual_list_text = str(current.get("manual_list") or "")
                if mode == "Manuell liste":
                    manual_list_text = st.text_area(
                        "Manuell liste",
                        value=manual_list_text,
                        placeholder="EQNR.OL, VOLV-B.ST, NOKIA.HE\nNOVO-B.CO, PETR4.SA",
                        key="ai_universe_manual_list_draft_v18517",
                        help="Brukes naar modus er Manuell liste. Du kan skille tickere med komma, mellomrom eller linjeskift.",
                        height=86,
                    )
            with c2:
                flow_input_count = _analysis_flow_input_count_for_smart_ai() if mode == "Analyseflyt input" else 0
                slider_max = max(1, flow_input_count) if mode == "Analyseflyt input" and flow_input_count > 0 else 200
                slider_min = 1 if slider_max < 5 else 5
                if mode == "Analyseflyt input" and flow_input_count > 0:
                    slider_value = slider_max
                else:
                    slider_value = min(max(int(current["max_count"]), slider_min), slider_max)
                max_count = st.slider(
                    "Antall kandidater",
                    slider_min,
                    slider_max,
                    _clamp_slider_state_v1864e("ai_universe_max_count_draft_v1853", slider_min, slider_max, slider_value),
                    1,
                    key="ai_universe_max_count_draft_v1853",
                )
                if mode == "Analyseflyt input" and flow_input_count > 0:
                    st.caption(f"Maks er låst til inputpakken fra Test 2: {flow_input_count} kandidater.")
                min_top_pick_score = st.slider(
                    "Minimum score for Top Picks",
                    4.0,
                    9.0,
                    float(current["min_top_pick_score"]),
                    0.1,
                    key="ai_universe_min_top_pick_score_draft_v1853",
                    help="Standard 6.50. Kandidater under denne AI-scoreterskelen filtreres bort foer Top Picks.",
                )
                st.caption("Standard 6.50: streng nok til aa kutte svake kandidater, men slipper fortsatt normale funn videre.")
                min_strength = st.slider(
                    "Momentum / strength-filter",
                    0.0,
                    100.0,
                    float(current["min_strength"]),
                    5.0,
                    key="ai_universe_min_strength_v1853",
                    help="Operativt filter. Smart AI-motoren beregner strength fra score_parts/avkastning eller eksisterende strength.",
                )
                st.caption("Standard 0: ingen momentumkrav. Oek bare naar du vil kreve tydelig trend/styrke i tillegg til score.")
            with c3:
                max_risk = st.selectbox(
                    "Maks risiko",
                    ["Lav", "Middels", "Høy", "Ukjent"],
                    index=["Lav", "Middels", "Høy", "Ukjent"].index(current["max_risk"]) if current["max_risk"] in ["Lav", "Middels", "Høy", "Ukjent"] else 1,
                    key="ai_universe_max_risk_v1853",
                    help="Operativt filter. Risiko beregnes fra volatilitet/drawdown eller eksisterende risk_score.",
                )
                current_sector_values = current["sectors"]
                if isinstance(current_sector_values, str):
                    current_sector_values = [current_sector_values]
                current_sector = next((x for x in current_sector_values if x in SECTOR_OPTIONS), "Alle sektorer")
                sector_choice = st.selectbox(
                    "Sektorfilter",
                    SECTOR_OPTIONS,
                    index=SECTOR_OPTIONS.index(current_sector) if current_sector in SECTOR_OPTIONS else 0,
                    key="ai_universe_sector_single_v1863w",
                    help="Ett sektorfilter om gangen. Velg Alle sektorer for bred scan.",
                )
                sectors = [sector_choice]
                st.session_state["ai_universe_sectors_v1853"] = sectors
                use_news = st.checkbox(
                    "Bruk nyheter/sentiment (NewsAPI)",
                    value=bool(current["use_news"]),
                    key="ai_universe_use_news_draft_v1853",
                    help="Av som standard for å spare API-kall. Når på brukes cache først; live NewsAPI-kall krever eksplisitt tillatelse i news.py/NEWSAPI_ALLOW_AUTO_CALLS.",
                )
                use_signal_intelligence = st.checkbox(
                    "Bruk Signal Intelligence",
                    value=bool(current["use_signal_intelligence"]),
                    key="ai_universe_use_signal_intelligence_draft_v1853",
                )

            submitted = st.form_submit_button("💾 Lagre Analyseunivers AI-oppsett som ventende", width="stretch")

        config = {
            "mode": mode,
            "scopes": scopes,
            "manual_ticker": _normalize_ticker(manual_ticker),
            "manual_list": manual_list_text,
            "manual_tickers": _parse_manual_ticker_list(manual_list_text),
            "max_count": int(max_count),
            "min_top_pick_score": float(min_top_pick_score),
            "use_news": bool(use_news),
            "use_signal_intelligence": bool(use_signal_intelligence),
            "max_risk": max_risk,
            "sectors": sectors,
            "min_strength": float(min_strength),
            "status": "smart_ai_universe_phase1_operational",
        }

        if submitted:
            st.session_state[AI_UNIVERSE_STATE_KEY] = config

            # Sync to the existing app controls. Heavy work still waits for the
            # app's existing global update button/manual-mode flow.
            st.session_state["max_count_main_v157"] = int(max_count)
            st.session_state["min_top_pick_score_main_v157"] = float(min_top_pick_score)
            st.session_state["use_news_main_v157"] = bool(use_news)
            st.session_state["use_signal_intelligence_main_v157"] = bool(use_signal_intelligence)
            st.session_state["search_main_v157"] = _normalize_ticker(manual_ticker) if mode == "Enkeltaksje" else ""
            # v18.5.26: Do not assign to ai_universe_manual_list_draft_v18517 after
            # its st.text_area widget has been instantiated in this run. Streamlit
            # raises if a widget key is mutated post-instantiation. Keep a separate
            # non-widget sync key for services/status panels instead.
            st.session_state["ai_universe_manual_list_saved_v18525"] = str(manual_list_text or "")

            if "Alle" in scopes:
                st.session_state["market_category_selector_v157"] = "All Markets"
            elif "Norge" in scopes and len(scopes) == 1:
                st.session_state["market_category_selector_v157"] = "Norway / Oslo"
            elif "Sverige" in scopes and len(scopes) == 1:
                st.session_state["market_category_selector_v157"] = "Sweden / Stockholm"
            elif "Finland" in scopes and len(scopes) == 1:
                st.session_state["market_category_selector_v157"] = "Finland / Helsinki"
            elif "Danmark" in scopes and len(scopes) == 1:
                st.session_state["market_category_selector_v157"] = "Danmark / Copenhagen"
            elif "Brasil" in scopes and len(scopes) == 1:
                st.session_state["market_category_selector_v157"] = "Brasil / B3"
            elif "USA" in scopes and len(scopes) == 1:
                st.session_state["market_category_selector_v157"] = "US Markets"

            _set_pending_change("Analyseunivers AI-modul endret")
            st.success("Analyseunivers-oppsett er lagret. Bruk knappen under for å gjøre det til aktivt aksjeunivers.")

        services = build_service_registry(st.session_state)
        picker_result_service = services.universe.resolve_picker(config)
        picker_result = picker_result_service.data.get("result", {}) if picker_result_service.ok else {}

        st.markdown("#### Smart Universe Picker")
        st.caption(
            "Dette er valg av tickerliste/univers: en arbeidsliste med symboler fra valgt kilde. "
            "Den er ikke en scoret kandidatliste før du kjører Smart AI-utvalg."
        )
        _render_selection_summary_panel(_picker_result_summary_rows(picker_result))
        if picker_result.get("candidates"):
            picker_df = _smart_result_dataframe(picker_result)
            picker_choice, picker_limit = _display_limit_choice_v1864d("smart_picker", len(picker_df.index))
            _render_dark_table(picker_df, empty_message="Picker-resultatet er tomt.", max_rows=picker_limit, max_height_px=420)
            st.caption(f"Viser {picker_choice.lower()} av {len(picker_df.index)} tickere. Hele tickerlisten/universet beholdes for send videre.")
        else:
            st.markdown(
                '<div class="ai-universe-empty-note">Picker-resultatet er tomt. Velg en kilde med data, skriv enkeltaksje, eller lim inn en manuell liste.</div>',
                unsafe_allow_html=True,
            )

        picker_a, picker_b, picker_c = st.columns(3)
        with picker_a:
            if st.button("🎯 Bruk som aktivt aksjeunivers", key="use_smart_universe_picker_active_v18517", width="stretch"):
                service_result = services.universe.save_active_universe(config)
                _set_pending_change("Smart Universe Picker satt som aktivt aksjeunivers")
                st.success(service_result.message or "Smart Universe Picker er satt som aktivt aksjeunivers.")
        with picker_b:
            if st.button("🔔 Send aktivt valg til watchlist", key="smart_universe_picker_to_watchlist_v18517", width="stretch"):
                service_result = services.watchlist.set_from_candidates(picker_result, limit=int(max_count or len(picker_result.get("candidates") or []) or 30))
                _set_pending_change("Smart Universe Picker sendt til watchlist")
                st.success(service_result.message or "Picker-resultatet er lagt inn som watchlist.")
        with picker_c:
            if st.button("⭐ Send aktivt valg til Top Picks", key="smart_universe_picker_to_top_picks_v18517", width="stretch"):
                service_result = services.top_picks.save_from_universe_result(picker_result, limit=int(max_count or len(picker_result.get("candidates") or []) or 10), list_name="TopPicks_Picker")
                _set_pending_change("Smart Universe Picker sendt til Top Picks")
                st.success(service_result.message or "Picker-resultatet er lagret som TopPicks_Picker.")

        active_universe = services.universe.load_active_universe().data or {}
        if active_universe.get("tickers"):
            st.caption(
                f"Aktivt aksjeunivers nå: {active_universe.get('source', 'Smart Universe Picker')} · "
                f"{len(active_universe.get('tickers', []))} tickere · første: {active_universe.get('tickers', ['-'])[0]}"
            )

        st.markdown("#### Smart AI-utvalg")
        st.caption(
            "Dette er scoring/rangering: knappen analyserer tickerlisten/universet via UniverseService "
            "og lager scorede kandidater som kan sendes til Top Picks/Watchlist."
        )
        run_col, info_col = st.columns([1, 2])
        with run_col:
            run_smart = st.button(
                "🚀 Kjør Smart AI-utvalg nå",
                key="run_smart_ai_universe_v1859",
                width="stretch",
                disabled=not bool(picker_result.get("tickers") or picker_result.get("candidates")),
                on_click=set_global_busy,
                kwargs={"label": "Kjører Smart AI-utvalg", "detail": "Forbereder valgt ticker-univers", "step": 1, "total": 4},
            )
        with info_col:
            st.info("Før du trykker Kjør er listen bare et univers. Etter kjøring får du scorede kandidater med filter/rangering. Runtime-data skrives ikke til GitHub/prosjektfiler.")

        # v18.5.26: Keep a visible progress panel in the module, not only a transient spinner.
        # This makes the run state visible even after Streamlit reruns or if the browser misses
        # the native spinner paint during a blocking data fetch.
        _render_progress_snapshot()

        run_pending_key = "ai_universe_smart_run_pending_v18524"
        if run_smart:
            st.session_state[run_pending_key] = True
            _safe_rerun()

        if bool(st.session_state.pop(run_pending_key, False)):
            services = build_service_registry(st.session_state)
            progress_holder = st.empty()
            try:
                progress_bar = st.progress(0.0, text="Starter Smart AI-utvalg …")
            except TypeError:
                progress_bar = st.progress(0.0)
            update_global_busy("Kjører Smart AI-utvalg", "Henter ticker-univers fra valgt Workspace-modus", step=1, total=4)
            _render_progress_step(progress_holder, progress_bar, title="Smart AI-utvalg", step=1, total=4, text="Henter ticker-univers fra valgt Workspace-modus")
            existing_scope_tickers = _existing_tickers_by_scope_from_state(st.session_state)
            update_global_busy("Kjører Smart AI-utvalg", "Henter kursdata og scorer kandidater", step=2, total=4)
            _render_progress_step(progress_holder, progress_bar, title="Smart AI-utvalg", step=2, total=4, text="Henter kursdata og scorer kandidater")
            service_result = services.universe.run_smart_universe(config, existing_tickers_by_scope=existing_scope_tickers)
            result = service_result.data.get("result", {})
            update_global_busy("Kjører Smart AI-utvalg", "Filtrerer risiko, score, sektor og momentum", step=3, total=4)
            _render_progress_step(progress_holder, progress_bar, title="Smart AI-utvalg", step=3, total=4, text="Filtrerer risiko, score, sektor og momentum")
            ranked_rows = result.get("ranked_rows") if isinstance(result, Mapping) else None
            if not ranked_rows:
                ranked_rows = services.universe.store_result_as_rankings(result)
            update_global_busy("Kjører Smart AI-utvalg", "Rangerer og lagrer resultat kompakt", step=4, total=4)
            _render_progress_step(progress_holder, progress_bar, title="Smart AI-utvalg", step=4, total=4, text="Rangerer og lagrer resultat kompakt")
            if ranked_rows:
                try:
                    from services.analysis_pipeline_service import get_analysis_pipeline_service
                    from services.state_service import get_state_service
                    from services.storage_service import get_storage_service

                    get_analysis_pipeline_service(
                        state_service=get_state_service(st.session_state),
                        storage_service=get_storage_service(),
                    ).save_stage_output(
                        "smart_ai",
                        ranked_rows,
                        source_label="Smart AI-filter",
                        context={
                            "mode": active_mode,
                            "scopes": list(scopes or []),
                            "max_count": int(max_count or len(ranked_rows)),
                            "input_count": _analysis_flow_input_count_for_smart_ai(),
                        },
                        max_items=len(ranked_rows),
                        auto_handoff=True,
                    )
                except Exception:
                    pass
                _finish_progress(progress_holder, progress_bar, title="Smart AI-utvalg ferdig", text=f"{len(ranked_rows)} kandidater matcher filtrene.", ok=True)
                finish_global_busy("Klar", f"Smart AI-utvalg ferdig: {len(ranked_rows)} kandidater")
                st.success(f"Smart AI-utvalg ferdig: {len(ranked_rows)} kandidater matcher filtrene.")
            else:
                _finish_progress(progress_holder, progress_bar, title="Smart AI-utvalg ferdig", text="Ingen kandidater matchet filtrene.", ok=False)
                finish_global_busy("Klar", "Smart AI-utvalg ferdig uten kandidater")
                st.info("Du kan senke filtrene og kjoere paa nytt, eller bruke knappen oppe i flytbaren for aa fortsette til Test 4 med inputpakken ufiltrert.")
                st.warning("Smart AI-utvalg ble kjørt, men ingen kandidater matchet filtrene eller datakilden returnerte ikke score.")

        smart_result = st.session_state.get(AI_UNIVERSE_SMART_RESULT_KEY, {}) or st.session_state.get(AI_UNIVERSE_SMART_RESULT_LEGACY_KEY, {}) or {}
        _render_selection_summary_panel(_smart_result_summary_rows(smart_result))
        if smart_result and smart_result.get("candidates"):
            smart_df = _smart_result_dataframe(smart_result)
            smart_choice, smart_limit = _display_limit_choice_v1864d("smart_result", len(smart_df.index))
            _render_dark_table(smart_df, empty_message="Smart AI-resultatet er tomt.", max_rows=smart_limit, max_height_px=440)
            st.caption(f"Viser {smart_choice.lower()} av {len(smart_df.index)} scorede kandidater. Visningsvalg endrer ikke pakken.")
            action_a, action_b = st.columns(2)
            with action_a:
                if st.button("⭐ Bruk Smart AI-resultat som Top Picks", key="smart_ai_to_top_picks_v1859", width="stretch"):
                    services = build_service_registry(st.session_state)
                    service_result = services.top_picks.save_from_universe_result(smart_result, limit=int(max_count or len(smart_result.get("candidates") or []) or 10), list_name="TopPicks_SmartAI")
                    _set_pending_change("Smart AI-resultat sendt til Top Picks")
                    st.success(service_result.message or "Smart AI-resultatet er lagt inn som TopPicks_SmartAI.")
            with action_b:
                if st.button("🔔 Bruk Smart AI-resultat som watchlist", key="smart_ai_to_watchlist_v1859", width="stretch"):
                    services = build_service_registry(st.session_state)
                    service_result = services.watchlist.set_from_candidates(smart_result, limit=int(max_count or len(smart_result.get("candidates") or []) or 30))
                    _set_pending_change("Smart AI-resultat sendt til watchlist")
                    st.success(service_result.message or "Smart AI-resultatet er lagt inn som watchlist.")
            if smart_result.get("errors"):
                with st.expander("Vis tickere som ble hoppet over / feilet", expanded=False):
                    _render_dark_table(pd.DataFrame(smart_result.get("errors", [])), empty_message="Ingen feilede tickere.", max_rows=25, max_height_px=260)

        candidates = collect_universe_candidates(st.session_state, limit=max_count)
        preview = filter_universe_candidates(candidates, scopes, sectors, max_risk, min_top_pick_score, min_strength)
        st.session_state[AI_UNIVERSE_PREVIEW_KEY] = [c.as_dict() for c in preview]

        st.markdown("#### Resultat av valgene i skjemaet")
        _render_selection_summary_panel(build_universe_selection_summary(config, candidates, preview, saved=bool(submitted)))
        st.caption(
            "Dette er resultatet av valgene i skjemaet: valgt tickerliste/univers og preview mot eksisterende cache. "
            "Ny scoring skjer bare i Smart AI-utvalg."
        )

        st.markdown("#### Status for Analyseunivers-modulen")
        _render_live_status_panel(build_universe_live_status(st.session_state, config, candidates, preview))
        st.caption(
            "Dette feltet viser nå faktiske opplysninger fra session/cache og valgte filtre. "
            "Roadmap/delstatus ligger i detaljfeltet under."
        )

        # v18.5.26: Use a normal toggle instead of an expander here. On some
        # Streamlit/browser combinations the empty expander region painted as a
        # large white null-data panel. A toggle plus dark inline cards avoids
        # native empty containers entirely.
        show_roadmap = st.checkbox("Vis roadmap / detaljstatus for funksjonene", value=False, key="ai_universe_show_roadmap_v18526")
        if show_roadmap:
            st.info("Roadmap/detaljstatus er midlertidig vist kompakt i denne QA-versjonen for aa hindre stor hvit/tom flate.")

        st.markdown("#### Preview av eksisterende scorede/cache-kandidater")
        if preview:
            preview_df = _candidate_dataframe(preview)
            preview_choice, preview_limit = _display_limit_choice_v1864d("cache_preview", len(preview_df.index))
            _render_dark_table(preview_df, empty_message="Ingen eksisterende kandidater å forhåndsvise.", max_rows=preview_limit, max_height_px=420)
            st.caption(f"Viser {preview_choice.lower()} av {len(preview_df.index)} preview-rader. Dette er bare visning.")
            st.caption(
                "Preview bruker bare eksisterende rangeringer, watchlist og paper-posisjoner som allerede finnes i appen. "
                "Den kjører ikke ny AI-scan og er ikke samme ting som valgt tickerliste/univers."
            )
        else:
            st.markdown(
                '<div class="ai-universe-empty-note">Ingen eksisterende kandidater i cache/session for valgt scope ennå. '
                'Kjør vanlig markedspanel eller Top Picks for å fylle preview-data. Dette betyr ikke at modulen feiler; '
                'det betyr bare at tickerlisten/universet ikke har eksisterende scorede kandidater å forhåndsvise.</div>',
                unsafe_allow_html=True,
            )

        return dict(config or {})

    return dict(st.session_state.get(AI_UNIVERSE_STATE_KEY, current) or {})
