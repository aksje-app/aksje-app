from __future__ import annotations

from typing import Any, Mapping, Sequence

from ranking_service import RankingRequest, RankingResult, rank_candidates, score100


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _ticker(value: Any) -> str:
    return _clean(value).upper().replace(" ", "")


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value is None or value == "":
        return []
    return [value]


def _unique_text(values: Sequence[Any]) -> list[str]:
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
    return out


def _max_score(row: Mapping[str, Any], keys: Sequence[str], default: float = 0.0) -> float:
    values = [score100(row.get(key), default=-1.0) for key in keys if row.get(key) not in {None, ""}]
    values = [value for value in values if value >= 0.0]
    return max(values) if values else float(default)


def _infer_radar_source(result: Mapping[str, Any], candidate: Mapping[str, Any] | None = None) -> str:
    text = " ".join(
        _clean(value)
        for value in (
            (candidate or {}).get("source"),
            result.get("analysis_engine"),
            result.get("mode"),
            result.get("engine"),
        )
    )
    if "Early Warning" in text:
        return "Early Warning"
    return "Alpha Radar"


def _radar_primary_score(row: Mapping[str, Any], source: str) -> float:
    if source == "Early Warning":
        return _max_score(row, ("early_warning_score", "hidden_potential_score", "alpha_score", "score"), default=0.0)
    return _max_score(row, ("hidden_potential_score", "alpha_score", "score", "early_warning_score"), default=0.0)


def _radar_evidence_ledger(row: Mapping[str, Any], source: str) -> list[dict[str, Any]]:
    existing = row.get("evidence_ledger")
    if isinstance(existing, list):
        return [dict(item) for item in existing if isinstance(item, Mapping)]
    try:
        from evidence_ledger import build_evidence_ledger

        return build_evidence_ledger(row, found_by=source)
    except Exception:
        return []


def radar_result_to_ranking_rows(
    result: Mapping[str, Any],
    *,
    selected_tickers: Sequence[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    selected = {_ticker(ticker) for ticker in selected_tickers or [] if _clean(ticker)}
    out: list[dict[str, Any]] = []
    for candidate in result.get("candidates") or []:
        if not isinstance(candidate, Mapping):
            continue
        ticker = _ticker(candidate.get("ticker"))
        if not ticker:
            continue
        if selected and ticker not in selected:
            continue
        source = _infer_radar_source(result, candidate)
        row = dict(candidate)
        row["ticker"] = ticker
        row["source"] = source
        row["decision_source"] = source
        row["radar_source"] = source
        row["source_result_created_at"] = result.get("created_at")
        row["source_scope"] = result.get("scope")
        row["source_horizon"] = result.get("horizon") or candidate.get("horizon")
        row["source_precision"] = result.get("precision_level") or result.get("precision")
        row["radar_mode"] = result.get("mode")
        row["radar_rank"] = candidate.get("rank")
        row["score"] = _radar_primary_score(row, source)
        if source == "Early Warning":
            row["early_warning_score"] = _max_score(row, ("early_warning_score", "hidden_potential_score", "score"), default=row["score"])
        else:
            row["alpha_score"] = _max_score(row, ("alpha_score", "hidden_potential_score", "score"), default=row["score"])
        row["evidence_ledger"] = _radar_evidence_ledger(row, source)
        row["signals"] = _unique_text([source, *_as_list(row.get("signals"))])
        if not row.get("data_quality"):
            row["data_quality"] = "radarresultat med evidens" if row.get("evidence_ledger") or row.get("evidence_items") else "radarresultat"
        out.append(row)
        if limit is not None and len(out) >= int(limit):
            break
    return out


def radar_results_to_ranking_result(
    results: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    request: RankingRequest | Mapping[str, Any] | None = None,
    selected_tickers: Sequence[str] | None = None,
) -> RankingResult:
    source_results = [results] if isinstance(results, Mapping) else list(results or [])
    rows: list[dict[str, Any]] = []
    for result in source_results:
        if isinstance(result, Mapping):
            rows.extend(radar_result_to_ranking_rows(result, selected_tickers=selected_tickers))
    return rank_candidates(rows, request)


def _strength_from_value(value: float) -> str:
    amount = abs(float(value or 0.0))
    if amount >= 25_000_000:
        return "Sterk"
    if amount >= 2_500_000:
        return "Normal"
    return "Svak"


def _strength_score(strength: Any, trust_level: Any = "") -> float:
    text = f"{strength} {trust_level}".lower()
    score = 62.0
    if "sterk" in text or "bekreftet" in text:
        score = 84.0
    elif "svak" in text or "usikker" in text:
        score = 44.0
    if "importert" in text:
        score += 4.0
    return max(0.0, min(100.0, score))


def _format_nok(value: Any) -> str:
    try:
        from finansavisen_bjellesau import format_nok

        return format_nok(value)
    except Exception:
        number = _float(value, 0.0)
        return f"{number:,.0f} NOK".replace(",", ".")


def _finansavisen_transaction_evidence(row: Mapping[str, Any]) -> dict[str, Any]:
    side = _clean(row.get("side")).lower()
    side_label = "kjop" if side == "buy" else "salg" if side == "sell" else "handel"
    signed_value = _float(row.get("transaction_value_nok"), 0.0)
    evidence_value = abs(signed_value)
    actor = _clean(row.get("investor"))
    stock_name = _clean(row.get("stock_name"))
    ticker = _ticker(row.get("matched_ticker"))
    periods = _unique_text(row.get("source_periods") or [row.get("source_period")])
    date = _clean(row.get("estimated_date") or row.get("date") or row.get("imported_at"))
    detail_parts = [
        f"{actor} {side_label} {stock_name}".strip(),
        f"verdi {_format_nok(evidence_value)}" if evidence_value else "",
        f"endring aksjer {int(_float(row.get('change_shares'), 0.0)):,}".replace(",", ".")
        if row.get("change_shares") not in {None, ""}
        else "",
        f"ny eierandel {row.get('new_ownership_pct')}%" if row.get("new_ownership_pct") not in {None, ""} else "",
        f"utfort av {row.get('performed_by')}" if _clean(row.get("performed_by")) else "",
        f"perioder {', '.join(periods)}" if periods else "",
    ]
    return {
        "type": f"Bjellesau-{side_label}",
        "title": f"{actor} - {stock_name}".strip(" -"),
        "source": "Finansavisen Bjellesauer",
        "date": date,
        "published": date,
        "url": "https://www.finansavisen.no/bjellesauer/siste-handler",
        "detail": " | ".join(part for part in detail_parts if part),
        "actor": actor,
        "actor_roles": ["Bjellesau"],
        "direction": side_label,
        "value": evidence_value,
        "amount_nok": evidence_value,
        "strength": _strength_from_value(evidence_value),
        "trust_level": "Importert",
        "ticker": ticker,
        "found_by": "Finansavisen import",
        "source_periods": periods,
    }


def finansavisen_to_ranking_rows(
    rows: Sequence[Mapping[str, Any]] | None = None,
    *,
    selected_tickers: Sequence[str] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    from finansavisen_bjellesau import aggregate_finansavisen_by_stock

    selected = {_ticker(ticker) for ticker in selected_tickers or [] if _clean(ticker)}
    out: list[dict[str, Any]] = []
    for item in aggregate_finansavisen_by_stock(rows):
        ticker = _ticker(item.get("matched_ticker"))
        if not ticker:
            continue
        if selected and ticker not in selected:
            continue
        score = score100(item.get("score"), default=0.0)
        transactions = [dict(row) for row in item.get("transactions") or [] if isinstance(row, Mapping)]
        evidence = [_finansavisen_transaction_evidence(row) for row in transactions]
        signal = _clean(item.get("signal") or "Finansavisen Bjellesauer")
        row = {
            "ticker": ticker,
            "name": item.get("stock_name") or ticker,
            "market": "Norge" if ticker.endswith(".OL") else "",
            "source": "Finansavisen Bjellesauer",
            "decision_source": "Finansavisen Bjellesauer",
            "score": score,
            "alpha_score": score,
            "bjellesau_score": score,
            "smart_money_score": score,
            "owner_signal": score,
            "evidence_score": min(100.0, 45.0 + score / 2.0),
            "data_quality": "ekte lokal import",
            "signals": _unique_text([signal, item.get("notes"), "Finansavisen Bjellesauer"]),
            "why_now": (
                f"{signal}; netto {_format_nok(item.get('net_value_nok'))}; "
                f"{item.get('unique_investors')} investorer; {item.get('transaction_count')} handler."
            ),
            "finansavisen_bjellesau_periods": list(item.get("periods") or []),
            "finansavisen_bjellesau_latest_date": item.get("latest_date"),
            "finansavisen_bjellesau_buy_value_nok": item.get("buy_value_nok"),
            "finansavisen_bjellesau_sell_value_nok": item.get("sell_value_nok"),
            "finansavisen_bjellesau_net_value_nok": item.get("net_value_nok"),
            "finansavisen_bjellesau_transaction_count": item.get("transaction_count"),
            "finansavisen_bjellesau_investors": list(item.get("investors") or []),
            "finansavisen_bjellesau_evidence": evidence,
            "bjellesau_evidence": evidence,
            "source_diagnostics": [{
                "type": "lokal import",
                "source": "Finansavisen Bjellesauer",
                "detail": f"{item.get('transaction_count')} handler, perioder {', '.join(item.get('periods') or [])}, score {score}.",
                "url": "https://www.finansavisen.no/bjellesauer/siste-handler",
            }],
        }
        out.append(row)
        if len(out) >= limit:
            break
    return out


def _match_nbim_change_ticker(change: Mapping[str, Any], alias_lookup: Any = None) -> str:
    explicit = _ticker(change.get("matched_ticker") or change.get("ticker"))
    if explicit:
        return explicit
    try:
        from nbim_radar import match_nbim_holding_to_ticker

        match = match_nbim_holding_to_ticker(change, alias_lookup)
        return _ticker(match.get("ticker"))
    except Exception:
        return ""


def nbim_to_ranking_rows(
    changes: Sequence[Mapping[str, Any]] | None = None,
    *,
    overlay: Mapping[str, Mapping[str, Any]] | None = None,
    ticker_aliases: Mapping[str, Sequence[str]] | None = None,
    limit: int = 150,
) -> list[dict[str, Any]]:
    source_changes = [dict(row) for row in changes or [] if isinstance(row, Mapping)]
    if overlay is None:
        from nbim_radar import build_nbim_overlay

        overlay = build_nbim_overlay(source_changes, ticker_aliases=ticker_aliases)
    try:
        from nbim_radar import build_ticker_alias_lookup

        alias_lookup = build_ticker_alias_lookup(ticker_aliases)
    except Exception:
        alias_lookup = None

    change_by_ticker: dict[str, dict[str, Any]] = {}
    for change in source_changes:
        matched = _match_nbim_change_ticker(change, alias_lookup)
        if matched:
            change_by_ticker.setdefault(matched, change)

    out: list[dict[str, Any]] = []
    for ticker, raw_data in (overlay or {}).items():
        if not isinstance(raw_data, Mapping):
            continue
        ticker = _ticker(ticker)
        data = dict(raw_data)
        change = change_by_ticker.get(ticker, {})
        score = score100(data.get("nbim_signal_score") or data.get("nbim_conviction_score"), default=0.0)
        evidence = []
        for item in data.get("nbim_evidence") or []:
            if not isinstance(item, Mapping):
                continue
            enriched = dict(item)
            enriched.setdefault("ticker", ticker)
            enriched.setdefault("actor", "Norges Bank Investment Management")
            enriched.setdefault("actor_roles", ["Institusjon", "Oljefond"])
            enriched.setdefault("trust_level", "Offentlig NBIM-fil")
            enriched.setdefault("strength", "Sterk" if score >= 75 else "Normal")
            enriched.setdefault("direction", data.get("nbim_change_type") or change.get("change_type"))
            enriched.setdefault("value", data.get("nbim_market_value_nok") or change.get("market_value_nok"))
            evidence.append(enriched)
        row = {
            **data,
            "ticker": ticker,
            "name": change.get("name") or ticker,
            "market": change.get("country") or change.get("market") or "",
            "source": "Oljefond/NBIM",
            "decision_source": "Oljefond/NBIM",
            "score": score,
            "alpha_score": score,
            "nbim_signal_score": score,
            "ownership_score": score,
            "evidence_score": min(100.0, 50.0 + score * 0.45),
            "data_quality": "ekte offentlig NBIM-fil",
            "market_cap": data.get("nbim_market_value_nok") or change.get("market_value_nok"),
            "market_cap_currency": "NOK",
            "signals": _unique_text([data.get("nbim_change_type"), *(data.get("nbim_signals") or []), "Oljefond/NBIM"]),
            "why_now": (
                f"NBIM/Oljefond {data.get('nbim_change_type') or change.get('change_type') or 'holding'}; "
                f"verdi {_format_nok(data.get('nbim_market_value_nok') or change.get('market_value_nok'))}; "
                f"ticker-match {data.get('nbim_ticker_match_quality') or '-'}."
            ),
            "nbim_evidence": evidence,
            "source_diagnostics": [{
                "type": "offentlig beholdningsfil",
                "source": "NBIM/Oljefondet",
                "detail": f"{data.get('nbim_change_type') or '-'}; score {score}; ticker-match {data.get('nbim_ticker_match_quality') or '-'}",
                "url": "https://www.nbim.no/en/the-fund/investments/",
            }],
        }
        out.append(row)
        if len(out) >= limit:
            break
    return out


def _row_text(row: Mapping[str, Any], fields: Sequence[str] | None = None) -> str:
    keys = fields or (
        "ticker",
        "name",
        "company",
        "stock_name",
        "why_now",
        "thesis",
        "notes",
        "signals",
        "source",
        "decision_source",
    )
    parts: list[str] = []
    for key in keys:
        value = row.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            parts.extend(_clean(item) for item in value)
        elif isinstance(value, Mapping):
            parts.append(" ".join(_clean(item) for item in value.values()))
        else:
            parts.append(_clean(value))
    for evidence_key in ("evidence_items", "insider_evidence", "bjellesau_evidence", "news_evidence", "nbim_evidence", "finansavisen_bjellesau_evidence"):
        for item in _as_list(row.get(evidence_key)):
            if isinstance(item, Mapping):
                parts.extend(_clean(item.get(key)) for key in ("title", "detail", "actor", "matched_actor", "source"))
    return " ".join(part for part in parts if part)


def _actor_evidence(match: Mapping[str, Any], *, ticker: str, source: str) -> dict[str, Any]:
    roles = list(match.get("matched_roles") or match.get("actor_roles") or [])
    if isinstance(match.get("actor_roles"), str):
        roles = [part.strip() for part in str(match.get("actor_roles")).replace(",", ";").split(";") if part.strip()]
    if not roles:
        roles = [match.get("actor_type") or "Bjellesau"]
    return {
        "type": " + ".join(roles),
        "title": match.get("name") or match.get("matched_alias"),
        "source": "Lokalt aktorregister",
        "date": "",
        "url": match.get("links") or "",
        "detail": (
            f"Matchet alias: {match.get('matched_alias')}. Roller: {', '.join(roles)}. "
            f"Tillit: {match.get('trust_level')}. Styrke: {match.get('strength')}."
        ),
        "actor": match.get("name") or match.get("matched_alias"),
        "actor_roles": roles,
        "strength": match.get("strength") or "Normal",
        "trust_level": match.get("trust_level") or "Manuelt lagt inn",
        "ticker": ticker,
        "found_by": source or "Aktorregister",
    }


def apply_actor_registry_to_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    actor_rows: Sequence[Mapping[str, Any]] | None = None,
    text_fields: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    from actor_registry import match_actor_text, normalize_actor_row

    registry_rows = [normalize_actor_row(row) for row in actor_rows] if actor_rows is not None else None
    out: list[dict[str, Any]] = []
    for raw in rows or []:
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        ticker = _ticker(row.get("ticker") or row.get("matched_ticker"))
        market = _clean(row.get("market") or row.get("country"))
        text = _row_text(row, text_fields)
        matches = match_actor_text(text, market=market, ticker=ticker, rows=registry_rows)
        if not matches:
            out.append(row)
            continue
        evidence = [_actor_evidence(match, ticker=ticker, source=_clean(row.get("source") or row.get("decision_source"))) for match in matches]
        existing_actor = [dict(item) for item in row.get("actor_registry_evidence") or [] if isinstance(item, Mapping)]
        row["actor_registry_evidence"] = (existing_actor + evidence)[:20]
        existing_bj = [dict(item) for item in row.get("bjellesau_evidence") or [] if isinstance(item, Mapping)]
        existing_in = [dict(item) for item in row.get("insider_evidence") or [] if isinstance(item, Mapping)]
        bj_add = [item for item in evidence if any("Bjellesau" == role for role in item.get("actor_roles") or [])]
        in_add = [item for item in evidence if any("Insider" in role for role in item.get("actor_roles") or [])]
        if bj_add:
            row["bjellesau_evidence"] = (existing_bj + bj_add)[:20]
            row["bjellesau_score"] = max(score100(row.get("bjellesau_score"), default=0.0), max(_strength_score(item.get("strength"), item.get("trust_level")) for item in bj_add))
        if in_add:
            row["insider_evidence"] = (existing_in + in_add)[:20]
            row["insider_score"] = max(score100(row.get("insider_score"), default=0.0), max(_strength_score(item.get("strength"), item.get("trust_level")) for item in in_add))
        row["evidence_score"] = max(score100(row.get("evidence_score"), default=0.0), min(100.0, 45.0 + len(evidence) * 12.0))
        signals = _unique_text([*_as_list(row.get("signals")), "Aktorregister-match"])
        row["signals"] = signals
        out.append(row)
    return out


def rank_local_evidence_sources(
    *,
    base_rows: Sequence[Mapping[str, Any]] | None = None,
    radar_results: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    finansavisen_rows: Sequence[Mapping[str, Any]] | None = None,
    nbim_changes: Sequence[Mapping[str, Any]] | None = None,
    nbim_overlay: Mapping[str, Mapping[str, Any]] | None = None,
    actor_rows: Sequence[Mapping[str, Any]] | None = None,
    request: RankingRequest | Mapping[str, Any] | None = None,
) -> RankingResult:
    combined: list[dict[str, Any]] = [dict(row) for row in base_rows or [] if isinstance(row, Mapping)]
    if radar_results is not None:
        source_results = [radar_results] if isinstance(radar_results, Mapping) else list(radar_results or [])
        for result in source_results:
            if isinstance(result, Mapping):
                combined.extend(radar_result_to_ranking_rows(result))
    if finansavisen_rows is not None:
        combined.extend(finansavisen_to_ranking_rows(finansavisen_rows, limit=500))
    if nbim_changes is not None or nbim_overlay is not None:
        combined.extend(nbim_to_ranking_rows(nbim_changes or [], overlay=nbim_overlay, limit=500))
    if actor_rows is not None:
        combined = apply_actor_registry_to_rows(combined, actor_rows=actor_rows)
    return rank_candidates(combined, request)


__all__ = [
    "apply_actor_registry_to_rows",
    "finansavisen_to_ranking_rows",
    "nbim_to_ranking_rows",
    "radar_result_to_ranking_rows",
    "radar_results_to_ranking_result",
    "rank_local_evidence_sources",
]
