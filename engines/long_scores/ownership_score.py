from __future__ import annotations

from typing import Any, Mapping

from .common import clamp_score, first_value


def calculate_ownership_score(data: Mapping[str, Any] | None) -> float:
    """Return 0..10 ownership score using the existing alpha_radar_ownership module.

    Supports both:
    - already enriched candidate rows with ownership/bjellesau/insider fields
    - plain rows with latest_transactions / bjellesau_evidence
    """
    row = dict(data or {})

    explicit = first_value(
        row,
        "ownership_score",
        "long_ownership_score",
        "bjellesau_signal_score",
        "bjellesau_score",
        "smart_money_score",
        "owner_signal",
    )
    if explicit not in (None, ""):
        return clamp_score(explicit)

    try:
        from alpha_radar_ownership import ownership_signal_scores

        scores = ownership_signal_scores(row)
        combined = scores.get("combined_score")
        if combined is not None:
            return clamp_score(combined)

        # If only counts are available, produce a conservative non-neutral score.
        insider_count = int(scores.get("insider_count") or 0)
        bjellesau_count = int(scores.get("bjellesau_count") or 0)
        if insider_count or bjellesau_count:
            score = 5.0 + min(2.5, insider_count * 0.35 + bjellesau_count * 0.55)
            return clamp_score(score)
    except Exception:
        pass

    return 5.0


def ownership_score_details(data: Mapping[str, Any] | None) -> dict[str, Any]:
    row = dict(data or {})
    score = calculate_ownership_score(row)
    details: dict[str, Any] = {"score": score, "source": "alpha_radar_ownership", "status": "neutral"}
    try:
        from alpha_radar_ownership import ownership_signal_scores, ownership_summary

        signals = ownership_signal_scores(row)
        details.update(signals)
        details["summary"] = ownership_summary(row)
        details["status"] = signals.get("quality") or "ok"
    except Exception as exc:
        details["error"] = f"{type(exc).__name__}: {exc}"
    return details
