from __future__ import annotations

import re

from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from core_models import ServiceResult, StockCandidate, UniverseRequest, UniverseResult, normalize_ticker
from app_version import get_app_version
from services.state_service import get_state_service
from services.storage_service import get_storage_service

SMART_RESULT_KEY = "smart_universe_result"
AI_UNIVERSE_SMART_RESULT_KEY = SMART_RESULT_KEY
AI_UNIVERSE_SMART_RESULT_LEGACY_KEY = "ai_analysis_universe_smart_result_v1859"
TOP_PICKS_RESULT_KEY = "top_picks_result"
WATCHLIST_RESULT_KEY = "watchlist_result"
ACTIVE_UNIVERSE_KEY = "smart_universe_picker_active_v18517"
ACTIVE_UNIVERSE_TICKERS_KEY = "smart_universe_picker_tickers_v18517"
ACTIVE_UNIVERSE_RANKING_KEY = "Smart Universe Picker"

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



def _split_ticker_text(value: Any) -> List[str]:
    """Parse a manual ticker list from textarea/string/list/dicts."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[\s,;|/]+", value.strip())
        return _dedupe_tickers(parts)
    return _extract_tickers(value)


def _dedupe_tickers(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    for value in values or []:
        ticker = normalize_ticker(value)
        if ticker and ticker not in out:
            out.append(ticker)
    return out


def _candidate_rows_from_tickers(tickers: Sequence[str], source: str, reason: str = "") -> List[StockCandidate]:
    rows: List[StockCandidate] = []
    for idx, ticker in enumerate(_dedupe_tickers(tickers), start=1):
        rows.append(
            StockCandidate(
                ticker=ticker,
                name=ticker,
                source=source,
                rank=idx,
                market="",
                reason=reason or f"Valgt fra {source}",
            )
        )
    return rows


def _candidate_dict_rows(candidates: Sequence[StockCandidate]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for candidate in candidates:
        row = candidate.as_dict()
        row.setdefault("score", row.get("ai_score"))
        rows.append(row)
    return rows

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

        # Render/session state can be lost between deploys. Pull persisted
        # picker-related data back into source maps when available.
        stored_watchlist = _extract_tickers(self.storage.read_json("watchlist.json", default=[]))
        if stored_watchlist:
            out.setdefault("Watchlist", []).extend(stored_watchlist)

        stored_rankings = self.storage.read_json("latest_rankings_v148.json", default={}) or {}
        if isinstance(stored_rankings, Mapping):
            for source, rows in stored_rankings.items():
                tickers = _extract_tickers(rows)
                if tickers:
                    out.setdefault(str(source), []).extend(tickers)
                    if str(source).startswith("TopPicks") or str(source) == "Top Picks":
                        out.setdefault("Top Picks", []).extend(tickers)
                    if str(source) in {"SmartAI", "Smart AI", ACTIVE_UNIVERSE_RANKING_KEY}:
                        out.setdefault("Smart AI-utvalg", []).extend(tickers)

        stored_top = self.storage.read_json("top_picks_result.json", default={}) or {}
        top_tickers = _extract_tickers(stored_top)
        if top_tickers:
            out.setdefault("Top Picks", []).extend(top_tickers)

        active = self.storage.read_json("active_universe.json", default={}) or self.storage.read_json("smart_universe_picker_active.json", default={}) or {}
        active_tickers = _extract_tickers(active.get("tickers") if isinstance(active, Mapping) else active)
        if active_tickers:
            out.setdefault(ACTIVE_UNIVERSE_RANKING_KEY, []).extend(active_tickers)

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

    def existing_tickers_by_scope(self) -> Dict[str, List[str]]:
        """Public snapshot for the Smart Universe Picker UI/tests."""
        return self._state_existing_tickers_by_scope()

    def _manual_list_from_config(self, config: Mapping[str, Any]) -> List[str]:
        metadata = config.get("metadata") if isinstance(config.get("metadata"), Mapping) else {}
        return _split_ticker_text(
            config.get("manual_list")
            or config.get("tickers")
            or metadata.get("manual_list")
            or metadata.get("tickers")
        )

    def _source_tickers_for_picker(self, config: Mapping[str, Any]) -> Tuple[List[str], str, str]:
        """Resolve every supported picker mode to a ticker list.

        The picker is intentionally deterministic and does not run a heavy
        Smart AI scan. It chooses the universe; the user explicitly starts scan
        / analysis afterwards.
        """
        mode = str(config.get("mode") or "Markedvalg").strip()
        scopes = [str(x) for x in (config.get("scopes") or []) if str(x or "").strip()]
        max_count = max(1, min(int(config.get("max_count") or 30), 250))
        existing = self._state_existing_tickers_by_scope()
        manual_ticker = normalize_ticker(config.get("manual_ticker"))
        manual_list = self._manual_list_from_config(config)

        if mode == "Enkeltaksje":
            return (_dedupe_tickers([manual_ticker]), "Enkeltaksje", "Én manuell ticker valgt")

        if mode == "Manuell liste" or "Manuell liste" in scopes:
            return (manual_list[:max_count], "Manuell liste", "Manuell tickerliste valgt")

        if mode == "Top Picks":
            return (existing.get("Top Picks", [])[:max_count], "Top Picks", "Lagrede Top Picks brukt som univers")

        if mode == "Watchlist":
            return (existing.get("Watchlist", [])[:max_count], "Watchlist", "Lagret watchlist brukt som univers")

        if mode == "Paper trading":
            return (existing.get("Paper trading", [])[:max_count], "Paper trading", "Åpne paper-posisjoner brukt som univers")

        if mode == "Portefølje":
            return (existing.get("Portefølje", [])[:max_count], "Portefølje", "Portefølje/holdings brukt som univers")

        if mode == "Smart AI-utvalg":
            smart = self.state.get(SMART_RESULT_KEY, None) or self.storage.read_json("smart_universe_result.json", default={}) or {}
            smart_tickers = _extract_tickers((smart or {}).get("candidates") if isinstance(smart, Mapping) else smart)
            if smart_tickers:
                return (smart_tickers[:max_count], "Smart AI-utvalg", "Siste Smart AI-resultat brukt som univers")
            return (existing.get("Smart AI-utvalg", [])[:max_count], "Smart AI-utvalg", "Siste Smart AI-rangering brukt som univers")

        # Markedvalg and Multi-marked both use selected scopes. Markedvalg often
        # has one market; Multi-marked can have several. Existing scopes such as
        # Watchlist/Top Picks can be mixed in deliberately.
        if not scopes:
            scopes = ["USA"]
        try:
            from universe_engine import resolve_universe_tickers

            tickers = resolve_universe_tickers(
                scopes=scopes,
                max_count=max_count,
                manual_ticker=manual_ticker if mode in {"Markedvalg", "Multi-marked"} else "",
                existing_tickers_by_scope=existing,
            )
        except Exception:
            tickers = _dedupe_tickers([manual_ticker] + DEFAULTS)[:max_count]

        source = "Multi-marked" if mode == "Multi-marked" or len(scopes) > 1 else "Marked"
        return (tickers[:max_count], source, f"Kilder: {', '.join(scopes)}")

    def resolve_picker(self, config: Mapping[str, Any]) -> ServiceResult:
        """Resolve the Smart Universe Picker without running a heavy scan."""
        try:
            req = self._request_from_any(config)
            normalized = req.as_dict()
            # Preserve manual list from UI because UniverseRequest.metadata keeps it
            # but .as_dict() does not expose it at top level.
            if isinstance(config, Mapping) and config.get("manual_list") is not None:
                normalized["manual_list"] = config.get("manual_list")
            tickers, source, reason = self._source_tickers_for_picker(normalized)
            max_count = max(1, min(int(normalized.get("max_count") or 30), 250))
            candidates = _candidate_rows_from_tickers(tickers[:max_count], source=source, reason=reason)
            result = UniverseResult(
                request=req,
                candidates=candidates,
                top_picks=candidates[: min(10, len(candidates))],
                status="ok" if candidates else "empty",
                universe_size=len(tickers),
                scanned=0,
                raw_candidates=len(candidates),
                summary={
                    "text": f"{len(candidates)} tickere valgt fra Smart Universe Picker.",
                    "source": source,
                    "reason": reason,
                },
            ).as_dict()
            result["tickers"] = [candidate.ticker for candidate in candidates]
            result["source"] = source
            result["picker_reason"] = reason
            return _ok({"result": result, "tickers": result["tickers"], "source": source}, status=result["status"])
        except Exception as exc:
            return _fail(f"Smart Universe Picker feilet: {exc}")

    def save_active_universe(self, config: Mapping[str, Any]) -> ServiceResult:
        """Persist the picker result as the app's active stock-selection core."""
        resolved = self.resolve_picker(config)
        if not resolved.ok:
            return resolved
        result = resolved.data.get("result") or {}
        tickers = list(result.get("tickers") or _extract_tickers(result.get("candidates") or []))
        rows = _candidate_dict_rows([StockCandidate.from_mapping(row, source=str(result.get("source") or ACTIVE_UNIVERSE_RANKING_KEY)) for row in result.get("candidates", []) if isinstance(row, Mapping)])
        payload = {
            "version": get_app_version(),
            "source": result.get("source") or "Smart Universe Picker",
            "picker_reason": result.get("picker_reason") or "",
            "tickers": tickers,
            "rows": rows,
            "config": dict(config or {}),
            "generated_at": result.get("generated_at"),
            "matched_candidates": len(tickers),
        }
        self.state.set(ACTIVE_UNIVERSE_KEY, payload)
        self.state.set(ACTIVE_UNIVERSE_TICKERS_KEY, tickers)
        self.state.set("active_universe", payload)
        self.state.set("active_universe_tickers", tickers)
        self.storage.write_json("active_universe.json", payload)
        self.storage.write_json("smart_universe_picker_active.json", payload)

        latest_rankings = self.state.get("latest_rankings_v148", {}) or {}
        if not isinstance(latest_rankings, dict):
            latest_rankings = {}
        latest_rankings[ACTIVE_UNIVERSE_RANKING_KEY] = rows
        self.state.set("latest_rankings_v148", latest_rankings)
        self.storage.write_json("latest_rankings_v148.json", latest_rankings)
        return _ok(payload, message=f"{len(tickers)} tickere satt som aktivt aksjeunivers.", status="ok" if tickers else "empty")

    def load_active_universe(self) -> ServiceResult:
        payload = self.state.get(ACTIVE_UNIVERSE_KEY, None) or self.state.get("active_universe", None)
        if not payload:
            payload = self.storage.read_json("active_universe.json", default={}) or self.storage.read_json("smart_universe_picker_active.json", default={}) or {}
        return _ok(payload or {}, status="ok" if payload else "empty")

    def resolve(self, request: Any = None) -> ServiceResult:
        """Resolve a picker request into shared StockCandidate rows without running a scan."""
        try:
            req = self._request_from_any(request)
            config = req.as_dict()
            if isinstance(request, Mapping) and request.get("manual_list") is not None:
                config["manual_list"] = request.get("manual_list")
            tickers, source, _reason = self._source_tickers_for_picker(config)

            max_count = max(1, min(int(config.get("max_count") or 30), 250))
            candidates: List[StockCandidate] = []
            for idx, ticker in enumerate(tickers[:max_count], start=1):
                candidates.append(
                    StockCandidate(
                        ticker=ticker,
                        name=ticker,
                        source=source,
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
