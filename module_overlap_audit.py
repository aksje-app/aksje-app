from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple


MODULE_OVERLAP_AUDIT_VERSION = "v18.6.3bu"


@dataclass(frozen=True)
class ModuleRole:
    name: str
    role: str
    trigger: str
    heavy_call_boundary: str
    input_kind: str
    output_kind: str
    owns_data_fetch: bool
    owns_universe_selection: bool
    owns_shortlist: bool
    owns_validation: bool
    shared_layer: str
    valuable_checks: Tuple[str, ...]
    should_merge_engine: bool
    merge_note: str

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def get_module_roles() -> List[ModuleRole]:
    """Static role map for the overlapping ranking/test modules.

    This module is intentionally pure and static. It must never fetch market,
    news, insider or file data; the goal is to document which modules can share
    services without accidentally reintroducing slow menu-triggered runs.
    """
    return [
        ModuleRole(
            name="Marked/rangering",
            role="Bred markedsscanner",
            trigger="Eksplisitt Kjor-rangering-knapp",
            heavy_call_boundary="Henter/oppdaterer score bare naar bruker starter rangering",
            input_kind="Valgt marked/univers og maks antall",
            output_kind="Rangerte markedsrader og felles ranking snapshot",
            owns_data_fetch=True,
            owns_universe_selection=False,
            owns_shortlist=False,
            owns_validation=False,
            shared_layer="ranking_service + ranking_universe_adapters",
            valuable_checks=(
                "bred score over valgt marked",
                "grunnscore og teknisk styrke",
                "begrenset insider/nyhetsberikelse etter budsjett",
                "cachet resultat som andre paneler kan lese",
            ),
            should_merge_engine=False,
            merge_note="Del rankingformatet, men behold egen markedsskanner.",
        ),
        ModuleRole(
            name="Top Picks",
            role="Shortlist og visning av beste kandidater",
            trigger="Eksplisitt Kjor Top Picks eller allerede lagrede rankingrader",
            heavy_call_boundary="Skal lese eksisterende ranking og bare bygge shortlist naar bruker ber om det",
            input_kind="Eksisterende rangerte rader, terskel og maks antall",
            output_kind="Konsentrert liste med beste kandidater",
            owns_data_fetch=False,
            owns_universe_selection=False,
            owns_shortlist=True,
            owns_validation=False,
            shared_layer="ranking_service shortlist over eksisterende rader",
            valuable_checks=(
                "terskelbasert utvalg",
                "beste kandidater paa tvers av kilder",
                "kort vei til paper trading og beslutningsgrunnlag",
                "gjenbruker markedsresultat uten nye tunge kall",
            ),
            should_merge_engine=False,
            merge_note="Kan ligge tett paa Marked/rangering i UI, men er ikke en datainnhentingsmotor.",
        ),
        ModuleRole(
            name="Smart AI",
            role="Streng universvelger og raffinering",
            trigger="Eksplisitt Smart AI-kjoring",
            heavy_call_boundary="Score-provider kalles bare for tickere i valgt Smart AI-univers",
            input_kind="Kildeunivers, filtre, sektorer, risiko og minimumsscore",
            output_kind="Filtrerte kandidater med smart_score og felles ranking",
            owns_data_fetch=True,
            owns_universe_selection=True,
            owns_shortlist=False,
            owns_validation=False,
            shared_layer="ranking_service + source-scoped universe adapter",
            valuable_checks=(
                "stram avgrensing av univers",
                "sektor- og risikofiltre",
                "smart_score-blanding av AI-score, styrke, risiko, sentiment og insider",
                "forklarer hvorfor kandidater er med eller ute",
            ),
            should_merge_engine=False,
            merge_note="Del scoring og evidens, men behold Smart AI som egen streng universmotor.",
        ),
        ModuleRole(
            name="Auto Test Lab",
            role="Testbenk og validering av kandidater",
            trigger="Eksplisitt Kjor Auto Test Lab-knapp",
            heavy_call_boundary="Tester bare valgt kandidatsett etter brukerstart",
            input_kind="Kandidater fra marked, Top Picks, Smart AI, watchlist, paper trading eller manuell liste",
            output_kind="Beslutningskvalitet, testkombinasjoner, forkastede kandidater og felles ranking",
            owns_data_fetch=True,
            owns_universe_selection=False,
            owns_shortlist=False,
            owns_validation=True,
            shared_layer="ranking_service som downstream testbenk-output",
            valuable_checks=(
                "decision_quality",
                "event risk",
                "laeringsstatistikk",
                "datakvalitet",
                "kombinasjonstester og no-trade grunner",
            ),
            should_merge_engine=False,
            merge_note="Skal konsumere kandidater fra de andre, ikke erstatte dem.",
        ),
    ]


def assess_module_overlap() -> Dict[str, Any]:
    roles = get_module_roles()
    return {
        "version": MODULE_OVERLAP_AUDIT_VERSION,
        "recommendation": (
            "Ikke sla Top Picks, Smart AI, Marked/rangering og Auto Test Lab sammen til en tung motor. "
            "Del datamodeller, evidensformat, ranking_service og adaptere; behold separate entrypoints."
        ),
        "can_merge_single_engine": False,
        "should_share_services": True,
        "roles": [role.as_dict() for role in roles],
        "merge_actions": [
            "ranking_service er felles kjerne for score, evidens og anbefalt handling.",
            "Marked/rangering eier bred skanning og kan produsere felles ranking snapshot.",
            "Top Picks skal vaere shortlist/visning over felles ranking, ikke egen tung motor.",
            "Smart AI skal vaere streng universmotor med egne filtre, men samme rankingformat.",
            "Auto Test Lab skal vaere downstream testbenk som validerer kandidater fra de andre.",
            "Gammel overlappende kode kan ryddes bare etter at felles service er testet gronn.",
        ],
        "overlap_pairs": [
            {
                "modules": ("Marked/rangering", "Top Picks"),
                "overlap": "begge viser rangerte aksjer",
                "difference": "Marked finner bredt; Top Picks kutter ned til beste kandidater",
                "merge_level": "del resultater og UI-narhet, ikke datamotor",
            },
            {
                "modules": ("Marked/rangering", "Smart AI"),
                "overlap": "begge scorer aksjer",
                "difference": "Marked scanner valgt marked; Smart AI bruker strengere kildeunivers og filtre",
                "merge_level": "del ranking_service, behold egne kontrollflater",
            },
            {
                "modules": ("Top Picks", "Smart AI"),
                "overlap": "begge kan lage kandidatkortliste",
                "difference": "Top Picks er shortlist fra eksisterende resultat; Smart AI bygger eget filtrert univers",
                "merge_level": "del shortlistformat og beslutningsgrunnlag",
            },
            {
                "modules": ("Auto Test Lab", "alle de andre"),
                "overlap": "bruker samme kandidater og scorefelt",
                "difference": "Auto Test Lab tester kvalitet, kombinasjoner og forkastelsesgrunner",
                "merge_level": "Auto Test Lab er downstream validering",
            },
        ],
        "flow": [
            "1. Finn eller hent kandidater i Marked/rangering eller Smart AI.",
            "2. Lag Top Picks som shortlist over samme felles ranking.",
            "3. Send kandidater til Auto Test Lab for validering.",
            "4. Send beste validerte kandidater videre til Beslutningsgrunnlag eller Paper Trading.",
        ],
    }


def format_overlap_markdown(audit: Dict[str, Any] | None = None) -> str:
    data = audit or assess_module_overlap()
    lines = [
        f"**Konklusjon ({data.get('version', MODULE_OVERLAP_AUDIT_VERSION)}):** {data.get('recommendation', '')}",
        "",
        "**Roller:**",
    ]
    for role in data.get("roles", []):
        checks = ", ".join(str(item) for item in role.get("valuable_checks", [])[:3])
        lines.append(
            f"- **{role.get('name')}:** {role.get('role')}. "
            f"Tunge kall: {role.get('heavy_call_boundary')}. "
            f"Verdifulle tester: {checks}."
        )
    lines.extend(["", "**Praktisk sammenslaing:**"])
    for action in data.get("merge_actions", []):
        lines.append(f"- {action}")
    return "\n".join(lines)
