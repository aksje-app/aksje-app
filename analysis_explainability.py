"""AI explainability contracts for v19.21.0 RC1.

Presentation/audit only. This module must not alter ranking, candidate selection,
trading thresholds, portfolio rules, scheduler behaviour or execution decisions.
"""
from __future__ import annotations
from typing import Any, Mapping


def _m(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean(values: Any, limit: int = 5) -> list[str]:
    out=[]
    for value in values or []:
        text=str(value or "").strip()
        if text and text not in out:
            out.append(text)
        if len(out)>=limit:
            break
    return out


def build_candidate_explainability(candidate: Mapping[str, Any], transparency: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build a stable, human-readable explanation without changing decisions."""
    transparency=_m(transparency or candidate.get("analysis_transparency"))
    ranking=_m(transparency.get("ranking_explanation"))
    confidence=_m(transparency.get("confidence_breakdown"))
    components=list(ranking.get("components") or [])
    positives=_clean(candidate.get("positives") or transparency.get("positive_arguments"), 5)
    negatives=_clean(candidate.get("risks") or transparency.get("counter_arguments"), 5)
    gaps=[]
    for row in transparency.get("critical_gaps") or []:
        if isinstance(row, Mapping):
            area=str(row.get("area") or "ukjent område")
            reason=str(row.get("reason") or row.get("status") or "ikke fullt dokumentert")
            gaps.append(f"{area}: {reason}")
    gaps=_clean(gaps, 5)

    # Add transparent score contributors when explicit prose is sparse.
    for row in components:
        if not isinstance(row, Mapping):
            continue
        factor=str(row.get("factor") or "").replace("_", " ").strip()
        value=_f(row.get("contribution"))
        if value>0 and factor and len(positives)<5:
            positives.append(f"{factor}: positivt scorebidrag {value:.2f}")
        elif value<0 and factor and len(negatives)<5:
            negatives.append(f"{factor}: negativt scorebidrag {value:.2f}")

    score=_f(candidate.get("investment_score") or ranking.get("total_score"))
    decision=_f(confidence.get("transparent_decision_confidence") or _m(candidate.get("confidence_profile")).get("decision_confidence"))
    status=str(candidate.get("portfolio_action") or candidate.get("status") or "vurderes")
    rank=int(_f(candidate.get("shared_rank") or candidate.get("rank") or candidate.get("priority_rank"), 0))
    rank_text=f"rangert som nummer {rank}" if rank>0 else "rangert blant toppkandidatene"
    lead=positives[0] if positives else "samlet modellscore og porteføljetilpasning"
    restraint=negatives[0] if negatives else (gaps[0] if gaps else "ingen dominerende motfaktor registrert")
    summary=(f"{candidate.get('ticker') or 'Kandidaten'} er {rank_text} med score {score:.2f}/100. "
             f"Viktigste positive driver er {lead}. Viktigste begrensning er {restraint}. "
             f"Gjeldende handling er {status}; dokumentert beslutningsstyrke er {decision:.1f}/100.")

    change_positive=_clean(candidate.get("what_would_make_it_selected") or candidate.get("selection_triggers"), 4)
    change_negative=_clean(candidate.get("what_would_make_model_reject_it") or candidate.get("rejection_triggers"), 4)
    if not change_positive:
        change_positive=["Høyere dokumentasjonsdekning og flere uavhengige bekreftelser", "Bedre risikojustert score eller tydeligere positiv katalysator"]
    if not change_negative:
        change_negative=["Ny negativ primærkilde eller tydelig kildekonflikt", "Svekket score, datakvalitet eller beslutningsstyrke"]

    return {
        "schema_version":"19.21.0-rc1",
        "summary":summary,
        "why_selected":positives or ["Samlet score kvalifiserte kandidaten til videre vurdering"],
        "positive_drivers":positives,
        "negative_drivers":negatives,
        "key_risks":negatives,
        "documentation_gaps":gaps,
        "rank_explanation":{
            "rank":rank or None,
            "score":round(score,2),
            "reason":f"Plasseringen følger den kanoniske rangeringen; score, evidens og beslutningsstyrke vises separat.",
            "not_recalculated":True,
        },
        "what_can_improve_recommendation":change_positive,
        "what_can_weaken_recommendation":change_negative,
        "separation":{
            "model_score":round(score,2),
            "decision_strength":round(decision,2),
            "evidence_is_separate":True,
            "not_profit_probability":True,
        },
    }

__all__=["build_candidate_explainability"]
