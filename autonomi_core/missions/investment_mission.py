"""Versioned Investment Mission Contract shared by every Autonomy engine."""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from autonomi_core.configuration.registry import status as configuration_status

STRATEGY_PROFILES = {
    "Kvalitet til rimelig pris": {"focus": ["quality", "fundamental", "valuation"], "description": "Robust kvalitet uten å betale enhver pris."},
    "Strukturell vekst": {"focus": ["growth", "market_position", "research"], "description": "Varige vekstdrivere og konkurransefortrinn."},
    "Midlertidig feilprising": {"focus": ["event", "recovery", "valuation"], "description": "Midlertidig problem der inntjeningskraften kan bestå."},
    "Bærekraftig utbytte": {"focus": ["cashflow", "dividend", "balance_sheet"], "description": "Utbytte støttet av kontantstrøm og soliditet."},
    "Insiderbekreftet verdi": {"focus": ["insider", "valuation", "fundamental"], "description": "Verdi støttet av verifiserte insiderkjøp."},
    "Momentum med fundamental støtte": {"focus": ["momentum", "earnings", "quality"], "description": "Prisrelativ styrke støttet av fundamentale forbedringer."},
    "Porteføljediversifisering": {"focus": ["portfolio_fit", "correlation", "risk"], "description": "Kandidater som forbedrer samlet porteføljerisiko."},
}
MISSION_PREFIX = "autonomi_core/investment_missions"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class InvestmentMission:
    mission_id: str
    configuration_version: str
    search_for: str
    markets: tuple[str, ...]
    sectors: tuple[str, ...]
    strategy: str
    horizon: str
    risk: str
    risk_ceiling: float
    portfolio_need: str
    minimum_data_quality: float
    candidate_count: int
    exclusions: tuple[str, ...]
    objective: str
    created_at: str
    theoretical_only: bool = True
    schema_version: int = 1

    def validate(self) -> None:
        if not self.mission_id or not self.configuration_version:
            raise ValueError("Oppdrags-ID og konfigurasjonsversjon er påkrevd")
        if not self.markets:
            raise ValueError("Minst ett marked er påkrevd")
        if self.strategy not in STRATEGY_PROFILES:
            raise ValueError("Ukjent strategiprofil")
        if not 0 <= self.minimum_data_quality <= 100:
            raise ValueError("Minimum datakvalitet må være mellom 0 og 100")
        if not 1 <= self.candidate_count <= 250:
            raise ValueError("Antall kandidater må være mellom 1 og 250")
        if not self.theoretical_only:
            raise ValueError("Kun teoretiske oppdrag er tillatt")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("markets", "sectors", "exclusions"):
            value[key] = list(value[key])
        value["strategy_profile"] = STRATEGY_PROFILES[self.strategy]
        return value

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "InvestmentMission":
        allowed = cls.__dataclass_fields__
        clean = {key: item for key, item in dict(value).items() if key in allowed}
        for key in ("markets", "sectors", "exclusions"):
            clean[key] = tuple(clean.get(key) or ())
        mission = cls(**clean); mission.validate(); return mission


def create_investment_mission(*, search_for: str, markets: Sequence[str], sectors: Sequence[str],
                              strategy: str, horizon: str, risk: str, risk_ceiling: float,
                              portfolio_need: str, minimum_data_quality: float,
                              candidate_count: int, exclusions: Sequence[str], objective: str) -> InvestmentMission:
    mission = InvestmentMission(
        mission_id=f"IM-{uuid.uuid4().hex[:14].upper()}",
        configuration_version=str(configuration_status()["config_version"]),
        search_for=str(search_for), markets=tuple(str(x) for x in markets), sectors=tuple(str(x) for x in sectors),
        strategy=str(strategy), horizon=str(horizon), risk=str(risk), risk_ceiling=float(risk_ceiling),
        portfolio_need=str(portfolio_need), minimum_data_quality=float(minimum_data_quality),
        candidate_count=int(candidate_count),
        exclusions=tuple(sorted({str(x).strip().upper() for x in exclusions if str(x).strip()})),
        objective=str(objective), created_at=_now(), theoretical_only=True,
    )
    mission.validate(); payload = mission.to_dict()
    from services.storage_service import get_storage_service
    storage = get_storage_service()
    storage.write_json(f"{MISSION_PREFIX}/{mission.mission_id}.json", payload)
    storage.write_json(f"{MISSION_PREFIX}/latest.json", payload)
    return mission


def load_investment_mission(mission_id: str = "") -> dict[str, Any]:
    from services.storage_service import get_storage_service
    key = f"{MISSION_PREFIX}/{mission_id}.json" if mission_id else f"{MISSION_PREFIX}/latest.json"
    value = get_storage_service().read_json(key, default={})
    return dict(value) if isinstance(value, Mapping) else {}


def engine_handoff(mission: Mapping[str, Any], engines: Sequence[str]) -> dict[str, Any]:
    return {str(engine): {"mission_id": mission.get("mission_id"), "configuration_version": mission.get("configuration_version")} for engine in engines}
