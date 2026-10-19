"""Read-only live ranking of owned Superfond positions from the frozen scan snapshot."""
from math import isfinite

def _number(value):
    try:
        n = float(value)
        return n if isfinite(n) else None
    except (TypeError, ValueError):
        return None

def owned_rankings(snapshot):
    """Score is recomputed from current candidate evidence, never from score_at_buy."""
    positions = snapshot.get("model", {}).get("positions", {})
    candidates = {str(row.get("id")): row for row in snapshot.get("candidates", [])}
    out = []
    group_sizes = {}
    for candidate in snapshot.get("candidates", []):
        group = (candidate.get("category"), candidate.get("returns_currency"))
        if candidate.get("rank") is not None:
            group_sizes[group] = group_sizes.get(group, 0) + 1
    for key, pos in positions.items():
        row = candidates.get(str(key), {})
        returns = row.get("returns") or {}
        week, month, quarter = (_number(returns.get(k)) for k in ("yield_1w", "yield_1m", "yield_3m"))
        score = (0.60 * week + 0.25 * month + 0.15 * quarter) if None not in (week, month, quarter) else None
        cost = _number(pos.get("cost_nok"))
        value = float(pos["quantity"]) * float(pos["last_nok"])
        out.append({"id": key, "name": pos["name"], "isin": pos.get("isin"),
                    "score_now": score, "score_at_buy": _number(pos.get("score_at_buy")),
                    "category_rank": row.get("rank") if score is not None else None,
                    "category_total": group_sizes.get((row.get("category"), row.get("returns_currency"))),
                    "category": row.get("category"), "returns_currency": row.get("returns_currency"),
                    "return_pct": (value / cost - 1) * 100 if cost and cost > 0 else None,
                    "value_nok": value, "price_at": row.get("price_at"),
                    "score_available": score is not None,
                    "reason": "" if score is not None else "Mangler gyldige 1 uke, 1 måned eller 3 måneder-data"})
    ranked = sorted((r for r in out if r["score_available"]), key=lambda r: (-r["score_now"], r["id"]))
    for index, row in enumerate(ranked, 1):
        row["owned_rank"] = index
    for row in out:
        row.setdefault("owned_rank", None)
    return out
