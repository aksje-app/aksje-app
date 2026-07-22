from dataclasses import dataclass, field


@dataclass(frozen=True)
class DiscoveryRequest:
    markets: tuple[str, ...] = ("Alle",)
    candidates_per_market: int = 25
    force_refresh: bool = False
    required_sources: tuple[str, ...] = field(default_factory=tuple)
