"""
analysis_universe_ai.py

v18.5.6: Analyseunivers som AI-modul med tydelig resultatfelt for valg.

Dette er et workspace-/arkitekturlag for Analyseunivers. Modulen samler valg for
enkeltaksje, marked, multi-marked, top picks, watchlist, paper trading og
portefølje i AI Kontrollsenter.

Viktig: ekte AI-universe-picker, intelligent filtrering og komplett
sammenslått workspace-motor er eksplisitt markert som planlagt / ikke ferdig.
Modulen skal derfor ikke late som at den gjør autonom AI-utvelgelse.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
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
AI_UNIVERSE_MODULE_VERSION = "v18.5.6"

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
    watchlist = session_state.get("latest_watchlist_tickers_v156", []) or []
    paper_count = len([c for c in candidates if c.source == "Paper trading"])
    top_pick_count = _count_ranked_items(latest_rankings, prefix="TopPicks")
    pending = bool(session_state.get("pending_manual_changes_v16", False))
    update_reason = str(session_state.get("last_update_started_by_v148", "Oppstart / cache") or "Oppstart / cache")
    update_at = str(session_state.get("last_update_started_at_v148", "-") or "-")
    manual_ticker = _normalize_ticker(config.get("manual_ticker") or session_state.get("search_main_v157", ""))

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
            "detail": "Disse kildene brukes i preview-filteret. Full multi-market AI-motor er fortsatt planlagt.",
            "kind": "preview",
        },
        {
            "label": "Manuell ticker",
            "value": manual_ticker or "Ingen",
            "detail": "Manuell ticker fungerer som overstyring/enkeltaksje når den er satt.",
            "kind": "ok" if manual_ticker else "neutral",
        },
        {
            "label": "Kandidater funnet",
            "value": f"{len(candidates)} totalt / {len(preview)} etter filter",
            "detail": "Basert på eksisterende rangeringer, watchlist og paper-posisjoner i session/cache.",
            "kind": "ok" if candidates else "warn",
        },
        {
            "label": "Watchlist",
            "value": f"{len(watchlist)} tickere",
            "detail": ", ".join([_normalize_ticker(x) for x in list(watchlist)[:8]]) or "Ingen watchlist-data registrert ennå.",
            "kind": "ok" if watchlist else "warn",
        },
        {
            "label": "Top Picks",
            "value": f"{top_pick_count} kandidater",
            "detail": "Leses fra TopPicks_* i siste rangering/cache.",
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
            "label": "Datagrunnlag",
            "value": f"{_count_ranked_items(latest_rankings)} rangerte rader",
            "detail": _rank_source_summary(latest_rankings),
            "kind": "ok" if latest_rankings else "warn",
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
            "detail": "Brukes til å avgrense preview og sendes videre som ventende analyseoppsett.",
            "kind": "preview",
        },
        {
            "label": "Enkeltaksje",
            "value": manual_ticker or "Ikke satt",
            "detail": "Når ticker er satt, fungerer den som manuell overstyring.",
            "kind": "ok" if manual_ticker else "neutral",
        },
        {
            "label": "Filtervalg",
            "value": f"Risiko ≤ {config.get('max_risk', 'Middels')}",
            "detail": f"Score ≥ {float(config.get('min_top_pick_score', 0) or 0):.1f} · Strength ≥ {float(config.get('min_strength', 0) or 0):.0f} · Sektor: {_safe_join(selected_sectors)}",
            "kind": "preview",
        },
        {
            "label": "Resultat nå",
            "value": f"{len(preview)} av {len(candidates)} kandidater matcher",
            "detail": "Vises i tabellen ‘Preview av eksisterende kandidater’ under. Hvis tallet er 0, mangler cache/session-data eller filtrene er for strenge.",
            "kind": "ok" if preview else "warn",
        },
        {
            "label": "Lagringsstatus",
            "value": saved_text,
            "detail": "Knappen lagrer valgene som ventende. Tung scan/oppdatering må fortsatt startes med appens vanlige oppdateringsknapp.",
            "kind": "ok" if saved else "neutral",
        },
    ]


def _render_selection_summary_panel(rows: Sequence[Mapping[str, str]]) -> None:
    cards: List[str] = []
    for row in rows:
        kind = escape(str(row.get("kind", "neutral") or "neutral"))
        label = escape(str(row.get("label", "")))
        value = escape(str(row.get("value", "")))
        detail = escape(str(row.get("detail", "")))
        cards.append(
            f"""
            <div class="ai-universe-choice-card {kind}">
                <div class="ai-universe-choice-label">{label}</div>
                <div class="ai-universe-choice-value">{value}</div>
                <div class="ai-universe-choice-detail">{detail}</div>
            </div>
            """
        )
    st.markdown('<div class="ai-universe-choice-grid">' + "".join(cards) + "</div>", unsafe_allow_html=True)


def _render_live_status_panel(rows: Sequence[Mapping[str, str]]) -> None:
    cards: List[str] = []
    for row in rows:
        kind = escape(str(row.get("kind", "neutral") or "neutral"))
        label = escape(str(row.get("label", "")))
        value = escape(str(row.get("value", "")))
        detail = escape(str(row.get("detail", "")))
        cards.append(
            f"""
            <div class="ai-universe-live-card {kind}">
                <div class="ai-universe-live-label">{label}</div>
                <div class="ai-universe-live-value">{value}</div>
                <div class="ai-universe-live-detail">{detail}</div>
            </div>
            """
        )
    st.markdown('<div class="ai-universe-live-grid">' + "".join(cards) + "</div>", unsafe_allow_html=True)


def _status_badge_class(status: str) -> str:
    normalized = str(status or "").strip().lower()
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
            min-height: 108px;
            box-shadow: 0 10px 24px rgba(0,0,0,.18);
        }
        .ai-universe-choice-card.ok { border-color: rgba(34,197,94,.54); }
        .ai-universe-choice-card.warn { border-color: rgba(250,204,21,.62); background: linear-gradient(180deg, rgba(66,52,8,.48), rgba(15,23,42,.84)); }
        .ai-universe-choice-card.preview { border-color: rgba(56,189,248,.58); }
        .ai-universe-choice-label {
            color:#bae6fd;
            font-size:.70rem;
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
            font-size:.74rem;
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
            min-height: 104px;
            box-shadow: 0 10px 24px rgba(0,0,0,.18);
        }
        .ai-universe-live-card.ok { border-color: rgba(34,197,94,.50); }
        .ai-universe-live-card.warn { border-color: rgba(250,204,21,.58); background: linear-gradient(180deg, rgba(66,52,8,.42), rgba(15,23,42,.82)); }
        .ai-universe-live-card.preview { border-color: rgba(56,189,248,.48); }
        .ai-universe-live-label {
            color:#94a3b8;
            font-size:.70rem;
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
            font-size:.74rem;
            line-height:1.32;
            overflow-wrap:anywhere;
        }
        .ai-universe-pill.ok { border-color: rgba(34,197,94,.50); color:#bbf7d0; }
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
            min-height: 92px;
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
            font-size: .86rem;
        }
        .ai-universe-status-badge {
            border-radius: 999px;
            padding: .15rem .42rem;
            font-size: .65rem;
            font-weight: 900;
            white-space: nowrap;
            border: 1px solid rgba(148,163,184,.30);
            color:#e2e8f0;
        }
        .ai-universe-status-badge.ui { border-color: rgba(34,197,94,.52); color:#bbf7d0; }
        .ai-universe-status-badge.partial { border-color: rgba(56,189,248,.52); color:#bae6fd; }
        .ai-universe-status-badge.arch { border-color: rgba(167,139,250,.52); color:#ddd6fe; }
        .ai-universe-status-badge.preview { border-color: rgba(250,204,21,.55); color:#fde68a; }
        .ai-universe-status-badge.planned { border-color: rgba(248,113,113,.52); color:#fecaca; }
        .ai-universe-status-text {
            color:#cbd5e1;
            font-size:.75rem;
            line-height:1.33;
        }
        .ai-universe-empty-note {
            border: 1px dashed rgba(250,204,21,.45);
            background: rgba(250,204,21,.08);
            border-radius: 12px;
            padding: .62rem .75rem;
            color: #fde68a;
            font-size: .78rem;
            font-weight: 780;
            margin-top: .25rem;
        }
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

        if submitted:
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

        if mode == "Smart AI-utvalg (planlagt)":
            st.warning("Smart AI-utvalg er lagt inn som modulvalg, men den ekte AI-universe-picker-motoren er ikke ferdig implementert ennå.")

        candidates = collect_universe_candidates(st.session_state, limit=max_count)
        preview = filter_universe_candidates(candidates, scopes, sectors, max_risk, min_top_pick_score, min_strength)
        st.session_state[AI_UNIVERSE_PREVIEW_KEY] = [c.as_dict() for c in preview]

        st.markdown("#### Resultat av valgene i skjemaet")
        _render_selection_summary_panel(build_universe_selection_summary(config, candidates, preview, saved=bool(submitted)))
        st.caption(
            "Dette er det direkte resultatet av valgene i skjemaet. Selve kandidatlisten ligger i "
            "‘Preview av eksisterende kandidater’ lenger ned."
        )

        st.markdown("#### Status for Analyseunivers-modulen")
        _render_live_status_panel(build_universe_live_status(st.session_state, config, candidates, preview))
        st.caption(
            "Dette feltet viser nå faktiske opplysninger fra session/cache og valgte filtre. "
            "Roadmap/delstatus ligger i detaljfeltet under."
        )

        with st.expander("Vis roadmap / detaljstatus for funksjonene", expanded=False):
            _render_feature_status_panel()

        st.markdown("#### Preview av eksisterende kandidater")
        if preview:
            st.dataframe(_candidate_dataframe(preview[:50]), use_container_width=True, hide_index=True)
            st.caption(
                "Preview bruker bare eksisterende rangeringer, watchlist og paper-posisjoner som allerede finnes i appen. "
                "Den kjører ikke en ny AI-scan."
            )
        else:
            st.markdown(
                '<div class="ai-universe-empty-note">Ingen eksisterende kandidater i cache/session for valgt scope ennå. '
                'Kjør vanlig markedspanel eller Top Picks for å fylle preview-data. Dette betyr ikke at modulen feiler; '
                'det betyr bare at AI-universet ikke har noe eksisterende datagrunnlag å forhåndsvise.</div>',
                unsafe_allow_html=True,
            )

        return dict(config or {})

    return dict(st.session_state.get(AI_UNIVERSE_STATE_KEY, current) or {})
