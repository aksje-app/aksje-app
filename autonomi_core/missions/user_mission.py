"""Persistent user-facing mission contract for simple Autonomy mode."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, MutableMapping, Sequence

from persistent_config_store import read_persistent_json, write_persistent_json


MISSION_KEY = "autonomi_core/user_mission.json"
RISK_CEILINGS = {"Forsiktig": 40.0, "Balansert": 65.0, "Offensiv": 100.0}
SECTOR_ALIASES = {
    "Teknologi": ("technology", "teknologi", "semiconductor", "software"),
    "Finans": ("financial", "finans", "bank", "insurance"),
    "Energi": ("energy", "energi", "oil", "gas"),
    "Industri": ("industrial", "industri"),
    "Helse": ("health", "helse", "biotech", "pharma"),
    "Forbruksvarer": ("consumer", "forbruk"),
    "Kommunikasjon": ("communication", "kommunikasjon", "telecom"),
    "Eiendom": ("real estate", "eiendom"),
    "Materialer": ("materials", "materialer", "mining"),
    "Forsyning": ("utilities", "forsyning"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_user_mission() -> dict[str, Any]:
    value = read_persistent_json(MISSION_KEY, default={})
    return dict(value) if isinstance(value, Mapping) else {}


def save_user_mission(*, goal: str, horizon: str, risk: str,
                      markets: Sequence[str], sectors: Sequence[str]) -> dict[str, Any]:
    if not markets:
        raise ValueError("Velg minst ett marked")
    if risk not in RISK_CEILINGS:
        raise ValueError("Ukjent risikonivå")
    mission = {
        "mission_id": f"UM-{uuid.uuid4().hex[:12].upper()}", "schema_version": 1,
        "created_at": _now(), "goal": str(goal), "horizon": str(horizon),
        "risk": risk, "risk_ceiling": RISK_CEILINGS[risk],
        "markets": [str(item) for item in markets],
        "sectors": [str(item) for item in sectors],
        "theoretical_only": True,
    }
    write_persistent_json(MISSION_KEY, mission)
    return mission


def _sector_matches(candidate_sector: str, requested: Sequence[str]) -> bool:
    if not requested:
        return True
    value = str(candidate_sector or "").casefold()
    terms = [term for item in requested for term in SECTOR_ALIASES.get(str(item), (str(item).casefold(),))]
    return any(str(term).casefold() in value or value in str(term).casefold() for term in terms)


def apply_user_mission(candidates: Sequence[MutableMapping[str, Any]],
                       mission: Mapping[str, Any] | None) -> dict[str, Any]:
    """Apply only explicit risk/sector gates; goal/horizon remain traceable context."""
    profile = dict(mission or {})
    if not profile.get("mission_id"):
        for candidate in candidates:
            candidate["mission_eligible"] = True
        return {"active": False, "eligible": len(candidates), "excluded": 0, "reasons": {}}
    risk_ceiling = float(profile.get("risk_ceiling", 100.0))
    sectors = list(profile.get("sectors") or [])
    exclusions = {str(item).strip().upper() for item in profile.get("exclusions", []) if str(item).strip()}
    counts: dict[str, int] = {}
    eligible = 0
    for candidate in candidates:
        reasons: list[str] = []
        if str(candidate.get("ticker") or "").strip().upper() in exclusions:
            reasons.append("Ekskludert i oppdraget")
            counts["EXCLUSION"] = counts.get("EXCLUSION", 0) + 1
        try:
            candidate_risk = float(candidate.get("risk_score", candidate.get("risk", 0)) or 0)
        except (TypeError, ValueError):
            candidate_risk = 0.0
        if candidate_risk > risk_ceiling:
            reasons.append(f"Risiko {candidate_risk:.1f} over grense {risk_ceiling:.1f}")
            counts["RISK"] = counts.get("RISK", 0) + 1
        sector = str(candidate.get("sector") or candidate.get("industry") or "")
        if not _sector_matches(sector, sectors):
            reasons.append("Utenfor valgte bransjer")
            counts["SECTOR"] = counts.get("SECTOR", 0) + 1
        allowed = not reasons
        candidate["mission_eligible"] = allowed
        candidate["mission_fit"] = {
            "mission_id": profile.get("mission_id"), "eligible": allowed,
            "goal": profile.get("goal"), "horizon": profile.get("horizon"),
            "risk": profile.get("risk"), "reasons": reasons,
        }
        if allowed:
            eligible += 1
        elif candidate.get("valid_for_decision"):
            candidate["status_before_mission"] = candidate.get("status")
            candidate["status"] = "UTENFOR VALGT OPPDRAG"
    return {
        "active": True, "mission_id": profile.get("mission_id"),
        "goal": profile.get("goal"), "horizon": profile.get("horizon"),
        "risk": profile.get("risk"), "risk_ceiling": risk_ceiling,
        "sectors": sectors, "eligible": eligible,
        "excluded": len(candidates) - eligible, "reasons": counts,
    }
