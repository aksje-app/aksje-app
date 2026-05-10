from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from core_models import ServiceResult, StockCandidate, UniverseRequest, UniverseResult, normalize_ticker
from services.state_service import get_state_service
from services.storage_service import get_storage_service

SMART_RESULT_KEY = "smart_universe_result"
AI_UNIVERSE_SMART_RESULT_KEY = SMART_RESULT_KEY
AI_UNIVERSE_SMART_RESULT_LEGACY_KEY = "ai_analysis_universe_smart_result_v1859"
TOP_PICKS_RESULT_KEY = "top_picks_result"
WATCHLIST_RESULT_KEY = "watchlist_result"

DEFAULTS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "EQNR.OL", "DNB.OL", "STB.OL", "NOVO-B.CO"]
ScoreProvider = Callable[[str, bool], Optional[Mapping[str, Any]]]


def _ok(data: Any = None, message: str = "", status: str = "ok", warnings: Optional[List[str]] = None) -> ServiceResult:
    return ServiceResult(ok=True, status=status, message=message, data=data or {}, warnings=warnings or [])


def _fail(message: str, status: str = "error") -> ServiceResult:
    return ServiceResult(ok=False, status=status, message=message, data={}, errors=[{"error": message}])


def _extract_tickers(value: Any) -> List[str]:
    out: List[str] = []

    def add(v: Any) -> None:
        if v is None:
            return
        if isinstance(v, str):
            for p in v.split(","):
                t = normalize_ticker(p)
                if t and t not in out:
                    out.append(t)
        elif isinstance(v, Mapping):
            # Row-like dict: prefer explicit ticker/symbol and do not treat
            # fields such as risk=Lav or sector=Technology as tickers.
            ticker = normalize_ticker(v.get("ticker") or v.get("symbol"))
            if ticker and ticker not in out:
                out.append(ticker)

            for k, val in v.items():
                key = str(k).strip()
                key_l = key.lower()
                if key_l in {"ticker", "symbol", "name", "risk", "sector", "source", "reason", "status", "metadata", "config", "request", "summary", "errors"}:
                    continue

                # Position maps often use ticker as key: {"AAPL": {position...}}.
                if isinstance(val, Mapping):
                    key_ticker = normalize_ticker(key)
                    if val and key_ticker and len(key_ticker) <= 12 and key_ticker not in {"POSITIONS", "HOLDINGS", "TRADES"} and key_ticker not in out:
                        out.append(key_ticker)
                    add(val)
                elif isinstance(val, (list, tuple, set)):
                    add(val)
                # Strings inside dicts are metadata unless under explicit ticker/symbol.
        elif isinstance(v, (list, tuple, set)):
            for i in v:
                add(i)

    add(value)
    return out


def _candidate_sort_key(candidate: StockCandidate):
    smart = candidate.smart_score if candidate.smart_score is not None else -1
    ai = candidate.ai_score if candidate.ai_score is not None else -1
    strength = candidate.strength if candidate.strength is not None else -1
    return (-float(smart), -float(ai), -float(strength), candidate.ticker)


class UniverseService:
    def __init__(self, state_service=None, storage_service=None, score_provider: Optional[ScoreProvider] = None):
        self.state = state_service or get_state_service()
        self.storage = storage_service or get_storage_service()
        self.score_provider = score_provider

    def _state_existing_tickers_by_scope(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        latest_rankings = self.state.get("latest_rankings_v148", {}) or {}
        if isinstance(latest_rankings, Mapping):
            for source, rows in latest_rankings.items():
                tickers = _extract_tickers(rows)
                if tickers:
                    source_key = str(source)
                    out[source_key] = tickers
                    if source_key.startswith("TopPicks"):
                        out.setdefault("Top Picks", []).extend(tickers)
                    if source_key.startswith("SmartAI") or source_key.startswith("Smart AI"):
                        out.setdefault("Smart AI-utvalg", []).extend(tickers)

        watch = _extract_tickers(
            self.state.get_first(["latest_watchlist_tickers_v156", "watchlist", "watchlist_items"], [])
        )
        if watch:
            out["Watchlist"] = watch

        paper = _extract_tickers(self.state.get_first(["paper_portfolio", "paper_positions", "paper_trading_positions"], {}))
        if paper:
            out["Paper trading"] = paper

        portfolio = _extract_tickers(self.state.get_first(["portfolio", "holdings", "positions"], {}))
        if portfolio:
            out["Portefølje"] = portfolio

        try:
            from paper_store import load_portfolio

            loaded = load_portfolio()
            paper_store_tickers = _extract_tickers((loaded or {}).get("positions", {}))
            if paper_store_tickers:
                out.setdefault("Paper trading", []).extend(paper_store_tickers)
        except Exception:
            pass

        for key, vals in list(out.items()):
            deduped: List[str] = []
            for ticker in vals:
                t = normalize_ticker(ticker)
                if t and t not in deduped:
                    deduped.append(t)
            out[key] = deduped
        return out

    def _request_from_any(self, request: Any = None) -> UniverseRequest:
        if request is None:
            return UniverseRequest()
        if isinstance(request, UniverseRequest):
            return request.normalized()
        if isinstance(request, Mapping):
            return UniverseRequest.from_config(request)
        return UniverseRequest().normalized()

    def resolve(self, request: Any = None) -> ServiceResult:
        """Resolve a picker request into shared StockCandidate rows without running a scan."""
        try:
            req = self._request_from_any(request)
            config = req.as_dict()
            existing = self._state_existing_tickers_by_scope()
            manual_list = config.get("metadata", {}).get("manual_list") or config.get("metadata", {}).get("tickers")

            if manual_list:
                tickers = _extract_tickers(manual_list)
            else:
                try:
                    from universe_engine import resolve_universe_tickers

                    tickers = resolve_universe_tickers(
                        scopes=config.get("scopes") or ["USA"],
                        max_count=int(config.get("max_count") or 30),
                        manual_ticker=str(config.get("manual_ticker") or ""),
                        existing_tickers_by_scope=existing,
                    )
                except Exception:
                    tickers = _extract_tickers(config.get("manual_ticker")) or DEFAULTS[: int(config.get("max_count") or 10)]

            max_count = max(1, min(int(config.get("max_count") or 30), 250))
            candidates: List[StockCandidate] = []
            for idx, ticker in enumerate(tickers[:max_count], start=1):
                candidates.append(
                    StockCandidate(
                        ticker=ticker,
                        name=ticker,
                        source=str(config.get("mode") or "Smart Universe Picker"),
                        rank=idx,
                        market="",
                        reason="Valgt via Smart Universe Picker",
                    )
                )
            result = UniverseResult(
                request=req,
                candidates=candidates,
                top_picks=candidates[: min(10, len(candidates))],
                status="ok" if candidates else "empty",
                universe_size=len(tickers),
                scanned=0,
                raw_candidates=len(candidates),
                summary={"text": f"{len(candidates)} tickere valgt fra universet."},
            )
            return _ok(result, status=result.status)
        except Exception as exc:
            return _fail(str(exc))

    def get_universe(self, request: Any = None) -> ServiceResult:
        return self.resolve(request)

    def smart_universe(self, market: str = "all", limit: int = 10) -> ServiceResult:
        scope = "Alle" if market == "all" else str(market).title()
        return self.resolve({"mode": "Smart AI-utvalg", "scopes": [scope], "max_count": limit})

    def top_picks(self, market: str = "all", limit: int = 10) -> ServiceResult:
        return self.resolve({"mode": "Top Picks", "scopes": ["Top Picks"], "max_count": limit})

    def run_smart_universe(
        self,
        config: Mapping[str, Any],
        existing_tickers_by_scope: Optional[Mapping[str, Sequence[str]]] = None,
    ) -> ServiceResult:
        """Run the real Smart AI universe engine and store the shared result."""
        try:
            from universe_engine import run_smart_ai_universe

            existing = dict(existing_tickers_by_scope or {})
            state_existing = self._state_existing_tickers_by_scope()
            for key, vals in state_existing.items():
                existing.setdefault(key, vals)

            raw = run_smart_ai_universe(
                dict(config or {}),
                existing_tickers_by_scope=existing,
                score_provider=self.score_provider,
            )
            result = UniverseResult.from_engine_result(raw).as_dict()

            self.state.set(SMART_RESULT_KEY, result)
            self.state.set(AI_UNIVERSE_SMART_RESULT_LEGACY_KEY, result)
            self.storage.write_json("smart_universe_result.json", result)

            ranked_rows = self.store_result_as_rankings(result)
            result["ranked_rows"] = ranked_rows
            return _ok({"result": result}, message="Smart AI-univers kjørt og lagret.", status=str(result.get("status") or "ok"))
        except Exception as exc:
            return _fail(f"Smart AI-univers feilet: {exc}")

    def store_result_as_rankings(self, result: Mapping[str, Any]) -> List[Dict[str, Any]]:
        try:
            from universe_engine import candidate_dicts_for_app

            rows = candidate_dicts_for_app(result)
        except Exception:
            rows = []
            for row in result.get("candidates", []) or []:
                if not isinstance(row, Mapping):
                    continue
                rows.append({
                    "ticker": row.get("ticker"),
                    "name": row.get("name") or row.get("ticker"),
                    "score": row.get("ai_score") or row.get("score"),
                    "smart_score": row.get("smart_score"),
                    "strength": row.get("strength"),
                    "risk": row.get("risk"),
                    "sector": row.get("sector"),
                    "source": "Smart AI",
                    "reason": row.get("reason"),
                })

        latest_rankings = self.state.get("latest_rankings_v148", {}) or {}
        if not isinstance(latest_rankings, dict):
            latest_rankings = {}
        latest_rankings["SmartAI"] = rows
        latest_rankings["Smart AI"] = rows
        self.state.set("latest_rankings_v148", latest_rankings)
        self.storage.write_json("latest_rankings_v148.json", latest_rankings)

        # v18.5.16: Persist score explanations so Testing & Learning can show
        # the explanation after a Render/session restart, not only immediately
        # after the scan.
        try:
            from score_explanation_store import capture_score_explanations

            capture_score_explanations(
                rows,
                source="Smart AI",
                context={"origin": "UniverseService.store_result_as_rankings"},
                storage=self.storage,
            )
        except Exception:
            pass
        return rows


_default = UniverseService()


def get_universe_service(state_service=None, storage_service=None, score_provider: Optional[ScoreProvider] = None) -> UniverseService:
    if state_service is not None or storage_service is not None or score_provider is not None:
        return UniverseService(state_service=state_service, storage_service=storage_service, score_provider=score_provider)
    return _default
