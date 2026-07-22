"""Mandatory freshness and decision-validity contract for candidate engines."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, MutableMapping, Sequence

from autonomi_core.configuration.policy import AutonomyPolicy, load_policy


@dataclass(frozen=True)
class DataContract:
    source: str
    fetched_at: str
    max_age_seconds: int
    delivery: str
    age_seconds: float | None
    quality_score: float
    quality_label: str
    missing_data: tuple[str, ...]
    validity: str
    action: str
    valid_for_decision: bool
    critical_stale: bool
    reason: str
    confidence_penalty: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["missing_data"] = list(self.missing_data)
        return value


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def evaluate_candidate_data(
    candidate: Mapping[str, Any], *, policy: AutonomyPolicy | None = None,
    now: datetime | None = None,
) -> DataContract:
    policy = policy or load_policy()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    merged = dict(raw)
    merged.update({key: value for key, value in candidate.items() if value is not None})

    source = str(merged.get("data_source") or merged.get("source") or candidate.get("source") or "UKJENT")
    status = str(merged.get("data_fetch_status") or "UKJENT").upper()
    proof = str(merged.get("refresh_proof") or "").upper()
    delivery = "CACHE" if ("cache" in source.casefold() or proof == "CACHE_USED" or merged.get("cache_hit")) else (
        "LIVE" if ("live" in source.casefold() or proof.startswith("LIVE_") or status in {"OK", "NO_DATA"}) else "UKJENT"
    )
    fetched_at = str(merged.get("fetch_completed_at") or merged.get("enriched_at") or merged.get("fetched_at") or "")
    fetched_dt = _parse_timestamp(fetched_at)
    age = max(0.0, (now - fetched_dt).total_seconds()) if fetched_dt else None
    if delivery == "CACHE" and merged.get("cache_age_seconds") is not None:
        age = max(age or 0.0, _number(merged.get("cache_age_seconds")))

    quality = _number(candidate.get("data_quality", merged.get("data_quality", 0.0)))
    quality_label = "GOD" if quality >= 75 else "BEGRENSET" if quality >= policy.minimum_data_quality else "SVAK"
    missing = list(merged.get("numeric_fields_missing_or_invalid") or [])
    loader = merged.get("loader_diagnostics") if isinstance(merged.get("loader_diagnostics"), Mapping) else {}
    missing.extend(loader.get("missing_or_invalid_numeric_fields") or [])
    if not fetched_at:
        missing.append("hentetidspunkt")
    if source == "UKJENT":
        missing.append("datakilde")
    if status in {"ERROR", "NO_DATA"} or merged.get("data_fetch_error"):
        missing.append("kritisk_markedsdata")
    missing = tuple(sorted({str(item) for item in missing if str(item).strip()}))

    stale = age is None or age > policy.market_data_max_age_seconds
    beyond_fallback = age is None or age > policy.fallback_max_age_seconds
    weak = quality < policy.minimum_data_quality
    critical_stale = bool(stale)

    if weak or "kritisk_markedsdata" in missing or beyond_fallback:
        validity, action, valid = "UGYLDIG", "STOPP_BESLUTNING", False
        reason = "Kritiske markedsdata er manglende, for gamle eller har for lav kvalitet"
        penalty = 100.0
    elif stale and delivery == "CACHE":
        validity, action, valid = "FALLBACK_MERKET", "BRUK_FALLBACK", False
        reason = "Cache er eldre enn normalgrensen; kandidaten kan vises, men ikke anbefales"
        penalty = policy.confidence_penalty_fallback
    elif stale:
        validity, action, valid = "KREVER_NY_HENTING", "HENT_PÅ_NYTT", False
        reason = "Kritiske markedsdata har passert maksimal alder og må hentes på nytt"
        penalty = policy.confidence_penalty_fallback
    elif missing:
        validity, action, valid = "GYLDIG_MED_MANGLER", "REDUSER_KONFIDENS", True
        reason = "Ikke-kritiske data mangler; konfidensen reduseres og manglene merkes"
        penalty = policy.confidence_penalty_missing
    else:
        validity, action, valid = "GYLDIG", "FORTSETT", True
        reason = "Datakilden er fersk og oppfyller kvalitetskravene"
        penalty = 0.0

    return DataContract(
        source=source, fetched_at=fetched_at or "MANGLER",
        max_age_seconds=int(policy.market_data_max_age_seconds), delivery=delivery,
        age_seconds=round(age, 1) if age is not None else None,
        quality_score=round(quality, 1), quality_label=quality_label,
        missing_data=missing, validity=validity, action=action,
        valid_for_decision=valid, critical_stale=critical_stale,
        reason=reason, confidence_penalty=float(penalty),
    )


def apply_data_contracts(
    candidates: Sequence[MutableMapping[str, Any]], *, policy: AutonomyPolicy | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    policy = policy or load_policy()
    counts: dict[str, int] = {}
    blocked: list[str] = []
    fallback: list[str] = []
    for candidate in candidates:
        contract = evaluate_candidate_data(candidate, policy=policy, now=now)
        candidate["data_contract"] = contract.to_dict()
        original = _number(candidate.get("confidence_score"))
        candidate["confidence_before_data_contract"] = round(original, 2)
        candidate["confidence_score"] = round(max(0.0, original - contract.confidence_penalty), 2)
        candidate["valid_for_decision"] = contract.valid_for_decision
        counts[contract.action] = counts.get(contract.action, 0) + 1
        ticker = str(candidate.get("ticker") or "UKJENT")
        if not contract.valid_for_decision:
            candidate["status_before_data_contract"] = candidate.get("status")
            candidate["status"] = "IKKE ANBEFALT – DATA MÅ FORNYES"
            blocked.append(ticker)
        if contract.action == "BRUK_FALLBACK":
            fallback.append(ticker)
    return {
        "version": "v18.8.1", "evaluated": len(candidates), "actions": counts,
        "valid_for_decision": sum(1 for item in candidates if item.get("valid_for_decision")),
        "blocked": blocked, "fallback": fallback,
        "approval_rule": "Ingen anbefaling på kritiske, foreldede data",
    }
