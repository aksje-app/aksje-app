from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

try:
    from core_models import normalize_ticker as _core_normalize_ticker
except Exception:  # pragma: no cover - fallback for isolated imports
    def _core_normalize_ticker(value: Any) -> str:
        return str(value or "").strip().upper().replace(" ", "")

try:
    from evidence_ledger import build_evidence_ledger, normalize_evidence_item
except Exception:  # pragma: no cover - evidence layer is optional for the core
    build_evidence_ledger = None
    normalize_evidence_item = None


RANKING_SERVICE_VERSION = "v18.6.3bo"

DEFAULT_RANKING_WEIGHTS = {
    "base": 0.22,
    "evidence": 0.24,
    "ownership": 0.18,
    "catalyst": 0.14,
    "timing": 0.10,
    "quality": 0.07,
    "risk_inverse": 0.05,
}

SCORE_KEYS = (
    "score",
    "alpha_score",
    "hidden_potential_score",
    "early_warning_score",
    "potential_score",
    "ai_score",
    "smart_score",
)

EVIDENCE_SCORE_KEYS = ("evidence_score", "source_score", "confidence_score")
OWNERSHIP_SCORE_KEYS = (
    "insider_score",
    "bjellesau_score",
    "nbim_signal_score",
    "owner_signal",
    "smart_money_score",
    "ownership_score",
)
CATALYST_SCORE_KEYS = ("catalyst_score", "inflection_score", "earnings_score", "event_score")
TIMING_SCORE_KEYS = ("volume_score", "macro_score", "strength", "momentum_strength", "trend_score")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_ticker(value: Any) -> str:
    return _core_normalize_ticker(value)


def _first(row: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        if key in row and row.get(key) not in {None, ""}:
            return row.get(key)
        low_key = str(key).lower()
        if low_key in lowered and lowered[low_key] not in {None, ""}:
            return lowered[low_key]
    return default


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    if value in {None, ""}:
        return []
    return [value]


def _split_text_list(value: Any) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        parts = [_clean(item) for item in value if _clean(item)]
    else:
        parts = [_clean(part) for part in re.split(r"[;,|]", _clean(value)) if _clean(part)]
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        marker = part.lower()
        if marker in seen:
            continue
        seen.add(marker)
        out.append(part)
    return tuple(out)


def _parse_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = _clean(value)
    if not text:
        return default
    text = text.replace("\xa0", " ").replace("%", "")
    text = re.sub(r"\s+", "", text)
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    text = re.sub(r"[^0-9.\-]", "", text)
    if text.count(".") > 1:
        text = text.replace(".", "")
    if text in {"", "-", ".", "-."}:
        return default
    try:
        return float(text)
    except Exception:
        return default


def score100(value: Any, default: float = 0.0) -> float:
    number = _parse_float(value, None)
    if number is None:
        return float(default)
    if 0.0 <= number <= 1.0:
        number *= 100.0
    return max(0.0, min(100.0, float(number)))


def _max_score(row: Mapping[str, Any], keys: Sequence[str], default: float = 0.0) -> float:
    values = [score100(row.get(key), default=-1.0) for key in keys if row.get(key) not in {None, ""}]
    values = [value for value in values if value >= 0.0]
    return max(values) if values else float(default)


def _quality_score(value: Any, *, has_evidence: bool = False) -> float:
    number = _parse_float(value, None)
    if number is not None:
        return score100(number)
    text = _clean(value).lower()
    if not text:
        return 62.0 if has_evidence else 48.0
    if any(word in text for word in ("ekte", "sterk", "high", "god", "confirmed", "bekreftet")):
        return 82.0
    if any(word in text for word in ("proxy", "middels", "medium", "normal")):
        return 58.0
    if any(word in text for word in ("mangler", "lav", "low", "svak", "hypotese")):
        return 32.0
    return 55.0


def _risk_score(row: Mapping[str, Any]) -> float:
    explicit = _first(row, ("risk_score", "risk_pressure", "Risiko-score"))
    if explicit not in {None, ""}:
        return score100(explicit, default=45.0)
    text = _clean(_first(row, ("risk", "Risiko", "risk_label"), "")).lower()
    if not text:
        return 45.0
    if any(word in text for word in ("lav", "low")):
        return 25.0
    if any(word in text for word in ("hoy", "high", "høy", "stor")):
        return 75.0
    if any(word in text for word in ("kritisk", "extreme", "ekstrem")):
        return 90.0
    return 50.0


def _hash_marker(parts: Sequence[Any]) -> str:
    blob = "|".join(_clean(part).lower() for part in parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _evidence_base_weight(evidence_type: str) -> float:
    text = evidence_type.lower()
    if "insider" in text or "primaer" in text or "primær" in text:
        return 18.0
    if "bjellesau" in text or "smart money" in text or "finansavisen" in text:
        return 18.0
    if "nbim" in text or "oljefond" in text or "institusjon" in text:
        return 16.0
    if "nyhet" in text or "news" in text or "katalys" in text or "børsmelding" in text:
        return 12.0
    if "resultat" in text or "earnings" in text:
        return 9.0
    return 6.0


def _adjust_evidence_weight(base: float, strength: str, trust_level: str) -> float:
    text = f"{strength} {trust_level}".lower()
    if any(word in text for word in ("sterk", "strong", "bekreftet", "high")):
        base += 4.0
    if any(word in text for word in ("svak", "weak", "proxy", "lav", "low")):
        base -= 3.0
    return max(2.0, min(25.0, base))


@dataclass(frozen=True)
class EvidenceItem:
    ticker: str = ""
    evidence_type: str = "Kilde"
    title: str = ""
    source: str = ""
    date: str = ""
    url: str = ""
    actor: str = ""
    actor_roles: tuple[str, ...] = field(default_factory=tuple)
    strength: str = ""
    trust_level: str = ""
    found_by: str = ""
    direction: str = ""
    value: float | None = None
    weight: float = 0.0
    marker: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        ticker = normalize_ticker(self.ticker)
        evidence_type = _clean(self.evidence_type) or "Kilde"
        weight = self.weight or _adjust_evidence_weight(
            _evidence_base_weight(evidence_type),
            self.strength,
            self.trust_level,
        )
        marker = self.marker or _hash_marker(
            (ticker, evidence_type, self.title, self.source, self.date, self.url, self.actor)
        )
        object.__setattr__(self, "ticker", ticker)
        object.__setattr__(self, "evidence_type", evidence_type)
        object.__setattr__(self, "weight", round(weight, 2))
        object.__setattr__(self, "marker", marker)

    @classmethod
    def from_mapping(
        cls,
        item: Mapping[str, Any] | None,
        *,
        ticker: str = "",
        found_by: str = "",
        default_type: str = "Kilde",
    ) -> "EvidenceItem":
        raw = dict(item or {})
        normalized: dict[str, Any] = {}
        if normalize_evidence_item is not None:
            try:
                normalized = normalize_evidence_item(raw, ticker=ticker, found_by=found_by, default_type=default_type)
            except Exception:
                normalized = {}
        evidence_type = _clean(normalized.get("type") or raw.get("type") or raw.get("kind") or default_type)
        roles = _split_text_list(normalized.get("actor_roles") or raw.get("actor_roles") or raw.get("roles"))
        strength = _clean(normalized.get("strength") or raw.get("strength") or raw.get("confidence") or raw.get("quality"))
        trust_level = _clean(normalized.get("trust_level") or raw.get("trust_level") or raw.get("tillit"))
        return cls(
            ticker=normalized.get("ticker") or raw.get("ticker") or ticker,
            evidence_type=evidence_type,
            title=_clean(normalized.get("title") or raw.get("title") or raw.get("headline") or raw.get("name") or evidence_type),
            source=_clean(normalized.get("source") or raw.get("source") or raw.get("publisher") or raw.get("site")),
            date=_clean(normalized.get("date") or raw.get("date") or raw.get("published") or raw.get("transaction_date")),
            url=_clean(normalized.get("url") or raw.get("url") or raw.get("link") or raw.get("source_url")),
            actor=_clean(normalized.get("actor") or raw.get("actor") or raw.get("person") or raw.get("investor")),
            actor_roles=roles,
            strength=strength,
            trust_level=trust_level,
            found_by=_clean(normalized.get("found_by") or raw.get("found_by") or found_by),
            direction=_clean(raw.get("direction") or raw.get("side") or raw.get("transaction_type") or raw.get("change_type")),
            value=_parse_float(raw.get("value") or raw.get("amount") or raw.get("net_value_nok"), None),
            marker=_clean(normalized.get("marker") or raw.get("marker")),
            metadata={k: v for k, v in raw.items() if k not in {
                "ticker", "type", "kind", "title", "headline", "name", "source", "publisher", "site",
                "date", "published", "transaction_date", "url", "link", "source_url", "actor", "person",
                "investor", "actor_roles", "roles", "strength", "confidence", "quality", "trust_level",
                "tillit", "found_by", "direction", "side", "transaction_type", "change_type", "value",
                "amount", "net_value_nok", "marker",
            }},
        )

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["actor_roles"] = list(self.actor_roles)
        return out


@dataclass(frozen=True)
class ScoreComponent:
    name: str
    value: float
    weight: float
    contribution: float
    reason: str = ""
    quality: str = ""
    evidence_count: int = 0
    source: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UniverseCandidate:
    ticker: str
    name: str = ""
    market: str = ""
    source: str = ""
    sector: str = ""
    base_score: float = 0.0
    evidence_score: float = 0.0
    ownership_score: float = 0.0
    catalyst_score: float = 0.0
    timing_score: float = 0.0
    quality_score: float = 0.0
    risk_score: float = 45.0
    liquidity_penalty: float = 0.0
    market_cap: float | None = None
    currency: str = ""
    signal_tags: tuple[str, ...] = field(default_factory=tuple)
    evidence_items: tuple[EvidenceItem, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        ticker = normalize_ticker(self.ticker)
        object.__setattr__(self, "ticker", ticker)
        if not self.name:
            object.__setattr__(self, "name", ticker)

    @property
    def identity_key(self) -> str:
        if self.ticker:
            return f"ticker:{self.ticker}"
        return "name:" + re.sub(r"[^a-z0-9]+", " ", self.name.lower()).strip()

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any], *, default_source: str = "") -> "UniverseCandidate":
        ticker = normalize_ticker(_first(row, ("ticker", "symbol", "Ticker", "matched_ticker"), ""))
        name = _clean(_first(row, ("name", "company", "stock_name", "Aksje", "shortName", "longName"), ticker))
        source = _clean(_first(row, ("decision_source", "source", "Kilde", "mode", "source_scope"), default_source))
        raw_evidence = _extract_evidence(row, ticker=ticker, found_by=source or default_source or "Ranking")
        has_evidence = bool(raw_evidence)
        evidence_score = max(
            _max_score(row, EVIDENCE_SCORE_KEYS, default=0.0),
            _derived_evidence_score(raw_evidence),
        )
        ownership_score = max(
            _max_score(row, OWNERSHIP_SCORE_KEYS, default=0.0),
            _ownership_score_from_evidence(raw_evidence),
        )
        quality_value = _first(row, ("data_quality_score", "quality_score", "data_quality", "quality"), None)
        return cls(
            ticker=ticker,
            name=name,
            market=_clean(_first(row, ("market", "Marked", "country", "Land"), "")),
            source=source or "Ukjent kilde",
            sector=_clean(_first(row, ("sector", "Sektor", "industry"), "")),
            base_score=_max_score(row, SCORE_KEYS, default=0.0),
            evidence_score=evidence_score,
            ownership_score=ownership_score,
            catalyst_score=_max_score(row, CATALYST_SCORE_KEYS, default=0.0),
            timing_score=_max_score(row, TIMING_SCORE_KEYS, default=0.0),
            quality_score=_quality_score(quality_value, has_evidence=has_evidence),
            risk_score=_risk_score(row),
            liquidity_penalty=score100(_first(row, ("liquidity_penalty", "liquidity_risk"), 0.0), default=0.0),
            market_cap=_parse_float(_first(row, ("market_cap", "market_value_nok", "market_value_usd"), None), None),
            currency=_clean(_first(row, ("market_cap_currency", "currency", "Valuta"), "")),
            signal_tags=_signal_tags(row),
            evidence_items=tuple(raw_evidence),
            metadata={
                "raw_keys": sorted(str(key) for key in row.keys()),
                "source_rank": _first(row, ("rank", "Rank"), None),
                "source_score": _first(row, SCORE_KEYS, None),
            },
        )

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["signal_tags"] = list(self.signal_tags)
        out["evidence_items"] = [item.as_dict() for item in self.evidence_items]
        return out


@dataclass(frozen=True)
class RankingRequest:
    max_count: int = 30
    markets: tuple[str, ...] = field(default_factory=tuple)
    sources: tuple[str, ...] = field(default_factory=tuple)
    min_score: float = 0.0
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_RANKING_WEIGHTS))
    dedupe_by_ticker: bool = True
    require_evidence: bool = False
    include_low_quality: bool = True
    label: str = "Felles ranking"
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> "RankingRequest":
        weights = dict(DEFAULT_RANKING_WEIGHTS)
        for key, value in (self.weights or {}).items():
            if key in weights:
                weights[key] = max(0.0, float(value or 0.0))
        return RankingRequest(
            max_count=max(1, min(int(self.max_count or 30), 500)),
            markets=tuple(_clean(item) for item in self.markets if _clean(item)),
            sources=tuple(_clean(item) for item in self.sources if _clean(item)),
            min_score=score100(self.min_score, default=0.0),
            weights=weights,
            dedupe_by_ticker=bool(self.dedupe_by_ticker),
            require_evidence=bool(self.require_evidence),
            include_low_quality=bool(self.include_low_quality),
            label=_clean(self.label) or "Felles ranking",
            metadata=dict(self.metadata or {}),
        )

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any] | None) -> "RankingRequest":
        raw = dict(row or {})
        return cls(
            max_count=int(raw.get("max_count") or raw.get("limit") or 30),
            markets=tuple(_as_list(raw.get("markets") or raw.get("market"))),
            sources=tuple(_as_list(raw.get("sources") or raw.get("source"))),
            min_score=float(raw.get("min_score") or 0.0),
            weights=dict(raw.get("weights") or {}),
            dedupe_by_ticker=bool(raw.get("dedupe_by_ticker", True)),
            require_evidence=bool(raw.get("require_evidence", False)),
            include_low_quality=bool(raw.get("include_low_quality", True)),
            label=_clean(raw.get("label") or "Felles ranking"),
            metadata={k: v for k, v in raw.items() if k not in {
                "max_count", "limit", "markets", "market", "sources", "source", "min_score", "weights",
                "dedupe_by_ticker", "require_evidence", "include_low_quality", "label",
            }},
        ).normalized()

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self.normalized())
        out["markets"] = list(out["markets"])
        out["sources"] = list(out["sources"])
        return out


@dataclass(frozen=True)
class RankedCandidate:
    rank: int
    candidate: UniverseCandidate
    score: float
    confidence: float
    recommended_action: str
    score_components: tuple[ScoreComponent, ...]
    evidence_summary: dict[str, int]
    risk_flags: tuple[str, ...] = field(default_factory=tuple)
    generated_at: str = field(default_factory=utc_now_iso)

    def as_dict(self) -> dict[str, Any]:
        candidate = self.candidate.as_dict()
        return {
            "rank": self.rank,
            "ticker": candidate.get("ticker"),
            "name": candidate.get("name"),
            "market": candidate.get("market"),
            "source": candidate.get("source"),
            "sector": candidate.get("sector"),
            "score": self.score,
            "confidence": self.confidence,
            "recommended_action": self.recommended_action,
            "score_components": [item.as_dict() for item in self.score_components],
            "evidence_summary": dict(self.evidence_summary),
            "risk_flags": list(self.risk_flags),
            "signal_tags": candidate.get("signal_tags", []),
            "evidence_items": candidate.get("evidence_items", []),
            "candidate": candidate,
            "generated_at": self.generated_at,
        }


@dataclass(frozen=True)
class RankingResult:
    request: RankingRequest
    ranked: tuple[RankedCandidate, ...]
    status: str = "ok"
    generated_at: str = field(default_factory=utc_now_iso)
    version: str = RANKING_SERVICE_VERSION
    summary: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "status": self.status,
            "generated_at": self.generated_at,
            "request": self.request.as_dict(),
            "summary": dict(self.summary),
            "warnings": list(self.warnings),
            "ranked": [item.as_dict() for item in self.ranked],
            "candidates": [item.as_dict() for item in self.ranked],
        }


def _extract_evidence(row: Mapping[str, Any], *, ticker: str, found_by: str) -> list[EvidenceItem]:
    raw_items: list[Mapping[str, Any]] = []
    for key in (
        "evidence_items",
        "evidence_ledger",
        "insider_evidence",
        "bjellesau_evidence",
        "news_evidence",
        "nbim_evidence",
        "finansavisen_bjellesau_evidence",
        "nordic_actor_evidence",
        "actor_registry_evidence",
    ):
        value = row.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            raw_items.extend(item for item in value if isinstance(item, Mapping))
    if build_evidence_ledger is not None:
        try:
            raw_items.extend(build_evidence_ledger(row, found_by=found_by))
        except Exception:
            pass
    seen: set[str] = set()
    out: list[EvidenceItem] = []
    for raw in raw_items:
        item = EvidenceItem.from_mapping(raw, ticker=ticker, found_by=found_by)
        if item.marker in seen:
            continue
        seen.add(item.marker)
        out.append(item)
    return out


def _signal_tags(row: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[Any] = []
    for key in ("signals", "signal", "Signal", "change_type", "recommendation", "action"):
        values.extend(_as_list(row.get(key)))
    return _split_text_list(values)


def _derived_evidence_score(items: Sequence[EvidenceItem]) -> float:
    if not items:
        return 0.0
    score = 28.0 + sum(item.weight for item in items[:12])
    return max(0.0, min(100.0, score))


def _ownership_score_from_evidence(items: Sequence[EvidenceItem]) -> float:
    score = 0.0
    for item in items:
        text = f"{item.evidence_type} {item.source} {item.actor_roles}".lower()
        if any(word in text for word in ("insider", "bjellesau", "finansavisen", "nbim", "oljefond", "institusjon")):
            score += item.weight
    if score <= 0.0:
        return 0.0
    return max(0.0, min(100.0, 36.0 + score))


def _evidence_summary(items: Sequence[EvidenceItem]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = item.evidence_type or "Kilde"
        counts[key] = counts.get(key, 0) + 1
    counts["totalt"] = len(items)
    return counts


def _source_matches(candidate: UniverseCandidate, wanted: Sequence[str]) -> bool:
    if not wanted:
        return True
    source = candidate.source.lower()
    return any(item.lower() in source for item in wanted)


def _market_matches(candidate: UniverseCandidate, wanted: Sequence[str]) -> bool:
    if not wanted:
        return True
    market = candidate.market.lower()
    return any(item.lower() == market or item.lower() in market for item in wanted)


def _merge_unique_text(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = _clean(value)
        if not text:
            continue
        marker = text.lower()
        if marker in seen:
            continue
        seen.add(marker)
        out.append(text)
    return tuple(out)


def _merge_evidence(items: Sequence[EvidenceItem]) -> tuple[EvidenceItem, ...]:
    seen: set[str] = set()
    out: list[EvidenceItem] = []
    for item in items:
        if item.marker in seen:
            continue
        seen.add(item.marker)
        out.append(item)
    return tuple(out)


def _merge_candidate_group(group: Sequence[UniverseCandidate]) -> UniverseCandidate:
    rows = list(group)
    if len(rows) == 1:
        return rows[0]
    evidence = _merge_evidence([item for row in rows for item in row.evidence_items])
    sources = _merge_unique_text([row.source for row in rows])
    signals = _merge_unique_text([tag for row in rows for tag in row.signal_tags])
    first = rows[0]
    return UniverseCandidate(
        ticker=first.ticker,
        name=next((row.name for row in rows if row.name and row.name != row.ticker), first.name),
        market=next((row.market for row in rows if row.market), first.market),
        source=" + ".join(sources) if sources else first.source,
        sector=next((row.sector for row in rows if row.sector), first.sector),
        base_score=max(row.base_score for row in rows),
        evidence_score=max(max(row.evidence_score for row in rows), _derived_evidence_score(evidence)),
        ownership_score=max(max(row.ownership_score for row in rows), _ownership_score_from_evidence(evidence)),
        catalyst_score=max(row.catalyst_score for row in rows),
        timing_score=max(row.timing_score for row in rows),
        quality_score=max(row.quality_score for row in rows),
        risk_score=max(row.risk_score for row in rows),
        liquidity_penalty=max(row.liquidity_penalty for row in rows),
        market_cap=next((row.market_cap for row in rows if row.market_cap is not None), first.market_cap),
        currency=next((row.currency for row in rows if row.currency), first.currency),
        signal_tags=signals,
        evidence_items=evidence,
        metadata={
            "merged_count": len(rows),
            "merged_sources": list(sources),
            "source_scores": [row.base_score for row in rows],
        },
    )


def _dedupe_candidates(candidates: Sequence[UniverseCandidate]) -> list[UniverseCandidate]:
    grouped: dict[str, list[UniverseCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.identity_key, []).append(candidate)
    return [_merge_candidate_group(group) for group in grouped.values()]


def _components(candidate: UniverseCandidate, request: RankingRequest) -> tuple[ScoreComponent, ...]:
    weights = request.normalized().weights
    total_weight = sum(value for value in weights.values() if value > 0.0) or 1.0
    values = {
        "base": candidate.base_score,
        "evidence": max(candidate.evidence_score, _derived_evidence_score(candidate.evidence_items)),
        "ownership": max(candidate.ownership_score, _ownership_score_from_evidence(candidate.evidence_items)),
        "catalyst": candidate.catalyst_score,
        "timing": candidate.timing_score,
        "quality": candidate.quality_score,
        "risk_inverse": max(0.0, 100.0 - max(candidate.risk_score, candidate.liquidity_penalty * 2.2)),
    }
    reasons = {
        "base": "beste innsendte radarscore/smartscore",
        "evidence": "normalisert evidens og kildeantall",
        "ownership": "insider/bjellesau/NBIM/aktor-spor",
        "catalyst": "katalysator, resultat eller vendepunkt",
        "timing": "volum, makro, momentum eller trend",
        "quality": "datakvalitet og ekte/proxy-status",
        "risk_inverse": "lav risiko gir positivt bidrag",
    }
    out: list[ScoreComponent] = []
    for name, value in values.items():
        weight = weights.get(name, 0.0)
        contribution = (value * weight / total_weight) if weight > 0.0 else 0.0
        out.append(ScoreComponent(
            name=name,
            value=round(value, 2),
            weight=round(weight, 4),
            contribution=round(contribution, 2),
            reason=reasons.get(name, ""),
            evidence_count=len(candidate.evidence_items),
            source=candidate.source,
        ))
    return tuple(out)


def _risk_flags(candidate: UniverseCandidate) -> tuple[str, ...]:
    flags: list[str] = []
    if not candidate.ticker:
        flags.append("mangler ticker")
    if not candidate.evidence_items:
        flags.append("mangler direkte evidens")
    if candidate.quality_score < 40:
        flags.append("lav datakvalitet")
    if candidate.risk_score >= 72:
        flags.append("hoy risiko")
    if candidate.liquidity_penalty >= 18:
        flags.append("likviditetsrisiko")
    return tuple(flags)


def _confidence(candidate: UniverseCandidate, score: float) -> float:
    evidence_score = max(candidate.evidence_score, _derived_evidence_score(candidate.evidence_items))
    source_bonus = min(18.0, len(candidate.evidence_items) * 3.0)
    risk_drag = max(candidate.risk_score - 55.0, 0.0) * 0.22
    confidence = 18.0 + score * 0.34 + evidence_score * 0.24 + candidate.quality_score * 0.18 + source_bonus - risk_drag
    return round(max(12.0, min(95.0, confidence)), 1)


def _action(score: float, confidence: float, candidate: UniverseCandidate) -> str:
    evidence_count = len(candidate.evidence_items)
    if candidate.risk_score >= 82 and score < 82:
        return "Lav prioritet"
    if score >= 76 and confidence >= 62 and evidence_count:
        return "Til beslutningsgrunnlag"
    if score >= 60:
        return "Analyser videre"
    if score >= 42:
        return "Folg med"
    return "Lav prioritet"


def _rank_one(candidate: UniverseCandidate, request: RankingRequest, rank: int = 0) -> RankedCandidate:
    components = _components(candidate, request)
    score = round(sum(component.contribution for component in components), 1)
    confidence = _confidence(candidate, score)
    return RankedCandidate(
        rank=rank,
        candidate=candidate,
        score=score,
        confidence=confidence,
        recommended_action=_action(score, confidence, candidate),
        score_components=components,
        evidence_summary=_evidence_summary(candidate.evidence_items),
        risk_flags=_risk_flags(candidate),
    )


def rank_candidates(
    rows: Sequence[Mapping[str, Any] | UniverseCandidate],
    request: RankingRequest | Mapping[str, Any] | None = None,
) -> RankingResult:
    req = request if isinstance(request, RankingRequest) else RankingRequest.from_mapping(request)
    req = req.normalized()
    warnings: list[str] = []
    normalized: list[UniverseCandidate] = []
    for row in rows or []:
        if isinstance(row, UniverseCandidate):
            candidate = row
        elif isinstance(row, Mapping):
            candidate = UniverseCandidate.from_mapping(row)
        else:
            continue
        if not candidate.ticker and not candidate.name:
            warnings.append("rad uten ticker/navn ble hoppet over")
            continue
        if req.require_evidence and not candidate.evidence_items:
            continue
        if not req.include_low_quality and candidate.quality_score < 40:
            continue
        if not _market_matches(candidate, req.markets):
            continue
        if not _source_matches(candidate, req.sources):
            continue
        normalized.append(candidate)

    if req.dedupe_by_ticker:
        normalized = _dedupe_candidates(normalized)

    ranked = [_rank_one(candidate, req) for candidate in normalized]
    ranked = [item for item in ranked if item.score >= req.min_score]
    ranked.sort(key=lambda item: (item.score, item.confidence, len(item.candidate.evidence_items)), reverse=True)
    limited = tuple(
        RankedCandidate(
            rank=idx,
            candidate=item.candidate,
            score=item.score,
            confidence=item.confidence,
            recommended_action=item.recommended_action,
            score_components=item.score_components,
            evidence_summary=item.evidence_summary,
            risk_flags=item.risk_flags,
            generated_at=item.generated_at,
        )
        for idx, item in enumerate(ranked[: req.max_count], start=1)
    )
    status = "ok" if limited else "empty"
    summary = {
        "input_rows": len(rows or []),
        "normalized_candidates": len(normalized),
        "ranked_candidates": len(limited),
        "dedupe_by_ticker": req.dedupe_by_ticker,
        "evidence_items": sum(len(item.candidate.evidence_items) for item in limited),
        "top_score": limited[0].score if limited else 0.0,
    }
    return RankingResult(request=req, ranked=limited, status=status, summary=summary, warnings=tuple(warnings))


__all__ = [
    "DEFAULT_RANKING_WEIGHTS",
    "EvidenceItem",
    "RankedCandidate",
    "RankingRequest",
    "RankingResult",
    "RANKING_SERVICE_VERSION",
    "ScoreComponent",
    "UniverseCandidate",
    "normalize_ticker",
    "rank_candidates",
    "score100",
]
