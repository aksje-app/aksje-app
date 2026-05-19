"""
core_models.py

v18.5.10: Felles datamodell for appens operative moduler.

Målet er at Analyseunivers, Watchlist, Top Picks, Paper Trading, Portefølje
og Forecast skal utveksle samme type objekter i stedet for hver sin ad-hoc dict.
Modellene er rene Python-dataklasser uten Streamlit-avhengighet og uten filskriving.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence


APP_MODEL_VERSION = "v18.5.10"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_ticker(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def _as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


@dataclass(frozen=True)
class StockCandidate:
    ticker: str
    name: str = ""
    market: str = ""
    source: str = ""
    sector: str = "Unknown"
    rank: int = 0
    ai_score: Optional[float] = None
    smart_score: Optional[float] = None
    strength: Optional[float] = None
    risk: str = "Ukjent"
    risk_score: Optional[float] = None
    sentiment: Optional[float] = None
    ret_1m_pct: Optional[float] = None
    ret_3m_pct: Optional[float] = None
    ret_6m_pct: Optional[float] = None
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", normalize_ticker(self.ticker))
        if not self.name:
            object.__setattr__(self, "name", self.ticker)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, item: Mapping[str, Any], source: str = "") -> "StockCandidate":
        ticker = normalize_ticker(item.get("ticker") or item.get("symbol"))
        return cls(
            ticker=ticker,
            name=str(item.get("name") or item.get("shortName") or item.get("longName") or ticker),
            market=str(item.get("market") or ""),
            source=str(source or item.get("source") or ""),
            sector=str(item.get("sector") or item.get("Sector") or item.get("industry") or "Unknown"),
            rank=int(item.get("rank") or 0),
            ai_score=_as_float(item.get("ai_score", item.get("score"))),
            smart_score=_as_float(item.get("smart_score")),
            strength=_as_float(item.get("strength", item.get("momentum_strength"))),
            risk=str(item.get("risk") or "Ukjent"),
            risk_score=_as_float(item.get("risk_score")),
            sentiment=_as_float(item.get("sentiment")),
            ret_1m_pct=_as_float(item.get("ret_1m_pct")),
            ret_3m_pct=_as_float(item.get("ret_3m_pct")),
            ret_6m_pct=_as_float(item.get("ret_6m_pct")),
            reason=str(item.get("reason") or item.get("note") or ""),
            metadata={k: v for k, v in item.items() if k not in {
                "ticker", "symbol", "name", "shortName", "longName", "market", "source", "sector", "Sector",
                "industry", "rank", "ai_score", "score", "smart_score", "strength", "momentum_strength", "risk",
                "risk_score", "sentiment", "ret_1m_pct", "ret_3m_pct", "ret_6m_pct", "reason", "note",
            }},
        )


@dataclass(frozen=True)
class UniverseRequest:
    mode: str = "Smart AI-utvalg"
    scopes: List[str] = field(default_factory=list)
    manual_ticker: str = ""
    max_count: int = 30
    max_risk: str = "Middels"
    sectors: List[str] = field(default_factory=lambda: ["Alle sektorer"])
    min_top_pick_score: float = 0.0
    min_strength: float = 0.0
    use_news: bool = False
    use_signal_intelligence: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> "UniverseRequest":
        return UniverseRequest(
            mode=str(self.mode or "Smart AI-utvalg"),
            scopes=[str(x) for x in (self.scopes or []) if str(x or "").strip()],
            manual_ticker=normalize_ticker(self.manual_ticker),
            max_count=max(1, min(int(self.max_count or 30), 250)),
            max_risk=str(self.max_risk or "Middels"),
            sectors=[str(x) for x in (self.sectors or ["Alle sektorer"]) if str(x or "").strip()] or ["Alle sektorer"],
            min_top_pick_score=float(self.min_top_pick_score or 0),
            min_strength=float(self.min_strength or 0),
            use_news=bool(self.use_news),
            use_signal_intelligence=bool(self.use_signal_intelligence),
            metadata=dict(self.metadata or {}),
        )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self.normalized())

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "UniverseRequest":
        return cls(
            mode=str(config.get("mode") or "Smart AI-utvalg"),
            scopes=list(config.get("scopes") or []),
            manual_ticker=str(config.get("manual_ticker") or ""),
            max_count=int(config.get("max_count") or 30),
            max_risk=str(config.get("max_risk") or "Middels"),
            sectors=list(config.get("sectors") or ["Alle sektorer"]),
            min_top_pick_score=float(config.get("min_top_pick_score") or 0),
            min_strength=float(config.get("min_strength") or 0),
            use_news=bool(config.get("use_news", False)),
            use_signal_intelligence=bool(config.get("use_signal_intelligence", False)),
            metadata={k: v for k, v in config.items() if k not in {
                "mode", "scopes", "manual_ticker", "max_count", "max_risk", "sectors",
                "min_top_pick_score", "min_strength", "use_news", "use_signal_intelligence",
            }},
        ).normalized()


@dataclass(frozen=True)
class UniverseResult:
    request: UniverseRequest
    candidates: List[StockCandidate] = field(default_factory=list)
    top_picks: List[StockCandidate] = field(default_factory=list)
    errors: List[Dict[str, str]] = field(default_factory=list)
    status: str = "ok"
    generated_at: str = field(default_factory=utc_now_iso)
    version: str = APP_MODEL_VERSION
    universe_size: int = 0
    scanned: int = 0
    raw_candidates: int = 0
    summary: Dict[str, Any] = field(default_factory=dict)

    @property
    def matched_candidates(self) -> int:
        return len(self.candidates)

    @property
    def top_tickers(self) -> List[str]:
        return [candidate.ticker for candidate in self.top_picks]

    def as_dict(self) -> Dict[str, Any]:
        # Backward-compatible dict shape used by existing UI and tests.
        return {
            "version": self.version,
            "status": self.status,
            "generated_at": self.generated_at,
            "config": self.request.as_dict(),
            "request": self.request.as_dict(),
            "scopes": list(self.request.scopes),
            "universe_size": self.universe_size,
            "scanned": self.scanned,
            "raw_candidates": self.raw_candidates,
            "matched_candidates": len(self.candidates),
            "top_tickers": self.top_tickers,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "top_picks": [candidate.as_dict() for candidate in self.top_picks],
            "errors": list(self.errors),
            "summary": dict(self.summary or {}),
        }

    @classmethod
    def from_engine_result(cls, engine_result: Mapping[str, Any]) -> "UniverseResult":
        request = UniverseRequest.from_config(engine_result.get("config") or engine_result.get("request") or {})
        candidates = [StockCandidate.from_mapping(row, source=str(row.get("source") or "Smart AI"))
                      for row in (engine_result.get("candidates") or []) if isinstance(row, Mapping)]
        top_pick_rows = engine_result.get("top_picks") or engine_result.get("candidates") or []
        top_picks = [StockCandidate.from_mapping(row, source=str(row.get("source") or "Smart AI"))
                     for row in top_pick_rows[:10] if isinstance(row, Mapping)]
        return cls(
            request=request,
            candidates=candidates,
            top_picks=top_picks,
            errors=list(engine_result.get("errors") or []),
            status=str(engine_result.get("status") or ("ok" if candidates else "empty")),
            generated_at=str(engine_result.get("generated_at") or utc_now_iso()),
            version=str(engine_result.get("version") or APP_MODEL_VERSION),
            universe_size=int(engine_result.get("universe_size") or 0),
            scanned=int(engine_result.get("scanned") or 0),
            raw_candidates=int(engine_result.get("raw_candidates") or len(candidates)),
            summary=dict(engine_result.get("summary") or {}),
        )


@dataclass(frozen=True)
class WatchlistItem:
    ticker: str
    source: str = "Watchlist"
    note: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", normalize_ticker(self.ticker))

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TopPickItem:
    candidate: StockCandidate
    list_name: str = "TopPicks_SmartAI"
    created_at: str = field(default_factory=utc_now_iso)

    def as_dict(self) -> Dict[str, Any]:
        out = self.candidate.as_dict()
        out["list_name"] = self.list_name
        out["created_at"] = self.created_at
        return out


@dataclass(frozen=True)
class PaperTradePosition:
    ticker: str
    side: str = "LONG"
    quantity: float = 0.0
    entry_price: Optional[float] = None
    source: str = "Smart AI"
    status: str = "planned"
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", normalize_ticker(self.ticker))

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioPosition:
    ticker: str
    quantity: float = 0.0
    avg_price: Optional[float] = None
    source: str = "Portfolio"
    updated_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", normalize_ticker(self.ticker))

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ForecastResult:
    ticker: str
    horizon: str = ""
    base_price: Optional[float] = None
    confidence: Optional[float] = None
    risk: str = "Ukjent"
    generated_at: str = field(default_factory=utc_now_iso)
    payload: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", normalize_ticker(self.ticker))

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ServiceResult:
    ok: bool
    status: str
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    generated_at: str = field(default_factory=utc_now_iso)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)
