from __future__ import annotations

import html
import hashlib
import json
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence

import streamlit as st

from alpha_radar_engine import ALPHA_RADAR_MODES, MARKET_CAP_FILTERS, PRECISION_LEVELS, normalize_alpha_radar_parameters, run_alpha_radar
from early_warning_engine import run_early_warning
from alpha_radar_results import (
    alpha_radar_candidate_tickers,
    alpha_radar_result_basename,
    alpha_radar_result_to_active_universe_payload,
    alpha_radar_result_to_csv,
    alpha_radar_result_to_json,
    alpha_radar_result_to_print_html,
    alpha_radar_result_to_ticker_text,
    alpha_radar_result_to_xlsx,
    save_alpha_radar_observation_list,
    save_alpha_radar_snapshot,
)
from alpha_radar_currency import market_cap_display
from data_source_diagnostics import build_data_source_status, horizon_to_months, probe_market_data_sources
from decision_engine import DECISION_QUEUE_KEY, add_decision_rows, decision_source_rows_from_radar_result
from source_budget import estimate_source_budget, source_budget_text


RADAR_UI_STATE_VERSION = "v1863ba"
LAST_RESULT_KEY = f"alpha_radar_last_result_{RADAR_UI_STATE_VERSION}"
ACTIVE_SIGNAL_OPTIONS = [
    "Borsverdi",
    "Insider/bjellesauer",
    "Nyheter/katalysator",
    "Ravarer/makro",
    "Arstid/syklus",
    "Uvanlig volum",
    "Resultater",
]

SOURCE_LABELS = {
    "news": "Nyheter",
    "insider": "Insider",
    "macro": "Ravarer/makro",
    "results": "Resultater",
}

MARKET_DISPLAY_ORDER = ["USA/annet", "USA", "Norge", "Sverige", "Finland", "Danmark", "Brasil"]

SIGNAL_SOURCE_REQUIREMENTS = {
    "Nyheter/katalysator": {"news": "Signal-lupe: Nyheter/katalysator"},
    "Insider/bjellesauer": {"insider": "Signal-lupe: Insider/bjellesauer"},
    "Ravarer/makro": {"macro": "Signal-lupe: Ravarer/makro"},
    "Arstid/syklus": {"macro": "Signal-lupe: Arstid/syklus"},
    "Resultater": {"results": "Signal-lupe: Resultater"},
}

MODE_RULES = {
    "Skjulte small/mid caps": {
        "default_signals": ["Borsverdi"],
        "required_signals": ["Borsverdi"],
        "required_sources": {},
        "recommended_sources": {"results": "Valgfritt stottebevis: resultatvendepunkt"},
        "allowed_signals": ["Borsverdi", "Resultater", "Uvanlig volum", "Insider/bjellesauer"],
        "summary": "Fokus paa underdekket boersverdi og mindre selskaper.",
    },
    "Insider og bjellesauer": {
        "default_signals": ["Insider/bjellesauer"],
        "required_signals": ["Insider/bjellesauer"],
        "required_sources": {"insider": "Radar-modus: Insider og bjellesauer"},
        "recommended_sources": {"news": "Valgfritt stottebevis: nyhetskatalysator rundt insiderbevegelse"},
        "allowed_signals": ["Insider/bjellesauer", "Nyheter/katalysator", "Uvanlig volum"],
        "summary": "Fokus paa insider-/bjellesauspor. Nyheter er bare stotte hvis du legger det til.",
    },
    "Ravare/makro-medvind": {
        "default_signals": ["Ravarer/makro"],
        "required_signals": ["Ravarer/makro"],
        "required_sources": {"macro": "Radar-modus: Ravare/makro-medvind"},
        "allowed_signals": ["Ravarer/makro", "Arstid/syklus", "Nyheter/katalysator"],
        "summary": "Fokus paa makro, ravare og andreordens effekter.",
    },
    "Resultat-vendepunkt": {
        "default_signals": ["Resultater"],
        "required_signals": ["Resultater"],
        "required_sources": {"results": "Radar-modus: Resultat-vendepunkt"},
        "recommended_sources": {"news": "Valgfritt stottebevis: guiding, kontrakter eller revisjoner"},
        "allowed_signals": ["Resultater", "Nyheter/katalysator", "Uvanlig volum"],
        "summary": "Fokus paa earnings, revisjoner og fundamental akselerasjon.",
    },
    "Uvanlig volum": {
        "default_signals": ["Uvanlig volum"],
        "required_signals": ["Uvanlig volum"],
        "required_sources": {},
        "recommended_sources": {"news": "Valgfritt stottebevis: mulig katalysator bak volumet"},
        "allowed_signals": ["Uvanlig volum", "Nyheter/katalysator", "Insider/bjellesauer"],
        "summary": "Fokus paa volum/teknisk akkumulering uten aa kreve nyheter.",
    },
    "Kontraer etter fall": {
        "default_signals": ["Resultater", "Borsverdi"],
        "required_signals": ["Borsverdi"],
        "required_sources": {},
        "recommended_sources": {"results": "Valgfritt stottebevis: vendepunkt i resultater"},
        "allowed_signals": ["Borsverdi", "Resultater", "Uvanlig volum", "Nyheter/katalysator"],
        "summary": "Fokus paa underprising etter fall, med resultatbevis som stotte.",
    },
}

ENGINE_RULES = {
    "Alpha Radar": {
        "default_signals": ["Borsverdi", "Nyheter/katalysator", "Resultater"],
        "required_signals": [],
        "required_sources": {},
        "recommended_sources": {},
        "allowed_signals": list(ACTIVE_SIGNAL_OPTIONS),
        "summary": "Finner skjulte hypoteser og underdekkede vendepunkter.",
    },
    "Early Warning V1": {
        "default_signals": ["Nyheter/katalysator", "Insider/bjellesauer", "Resultater"],
        "required_signals": ["Nyheter/katalysator", "Insider/bjellesauer"],
        "required_sources": {
            "news": "Sokemotor: Early Warning trenger ferske nyhetsspor",
            "insider": "Sokemotor: Early Warning trenger insider-/bjellesau-spor",
        },
        "recommended_sources": {"results": "Anbefalt for Early Warning: earnings/revisions"},
        "allowed_signals": ["Nyheter/katalysator", "Insider/bjellesauer", "Resultater", "Uvanlig volum"],
        "summary": "Tidlig varsling krever ferske nyhets- og insider-/bjellesauspor.",
    },
}


def _fmt_score(value: Any) -> str:
    if value is None or value == "":
        return "N/A"
    try:
        return f"{float(value):.1f}"
    except Exception:
        return "N/A"


def _market_options(no_selection_label: str, market_options: Sequence[str] | None) -> list[str]:
    options = [no_selection_label, "Aktivt univers"]
    options.extend([str(x) for x in market_options or [] if str(x or "").strip()])
    options.extend(["Watchlist", "Manuell liste"])
    out: list[str] = []
    seen: set[str] = set()
    for option in options:
        if option not in seen:
            seen.add(option)
            out.append(option)
    return out


def _cap_options_for_mode(mode: str) -> list[str]:
    if mode == "Skjulte small/mid caps":
        return ["Mikro/small", "Small/mid"]
    return list(MARKET_CAP_FILTERS)


def _signal_limit_for_precision(precision_level: str) -> int:
    return 3 if precision_level == "Streng" else 4 if precision_level == "Balansert" else 5


def _unique_signals(values: Sequence[str], limit: int | None = None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text in ACTIVE_SIGNAL_OPTIONS and text not in out:
            out.append(text)
        if limit is not None and len(out) >= int(limit):
            break
    return out


def _rule_for_engine_and_mode(analysis_engine: str, mode: str) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    return ENGINE_RULES.get(analysis_engine, ENGINE_RULES["Alpha Radar"]), MODE_RULES.get(mode, {})


def _required_signals_for_rules(analysis_engine: str, mode: str) -> list[str]:
    engine_rule, mode_rule = _rule_for_engine_and_mode(analysis_engine, mode)
    return _unique_signals(
        list(engine_rule.get("required_signals") or []) + list(mode_rule.get("required_signals") or [])
    )


def _signal_options_for_rules(analysis_engine: str, mode: str) -> list[str]:
    engine_rule, mode_rule = _rule_for_engine_and_mode(analysis_engine, mode)
    engine_allowed = set(engine_rule.get("allowed_signals") or ACTIVE_SIGNAL_OPTIONS)
    mode_allowed = set(mode_rule.get("allowed_signals") or ACTIVE_SIGNAL_OPTIONS)
    required = _required_signals_for_rules(analysis_engine, mode)
    allowed = [signal for signal in ACTIVE_SIGNAL_OPTIONS if signal in engine_allowed and signal in mode_allowed]
    return _unique_signals(required + allowed)


def _optional_signal_defaults(analysis_engine: str, mode: str, precision_level: str) -> list[str]:
    required = set(_required_signals_for_rules(analysis_engine, mode))
    return [signal for signal in _default_signals_for_rules(analysis_engine, mode, precision_level) if signal not in required]


def _default_signals_for_rules(analysis_engine: str, mode: str, precision_level: str) -> list[str]:
    limit = _signal_limit_for_precision(precision_level)
    engine_rule, mode_rule = _rule_for_engine_and_mode(analysis_engine, mode)
    allowed = set(_signal_options_for_rules(analysis_engine, mode))
    defaults = list(mode_rule.get("default_signals") or engine_rule.get("default_signals") or [])
    required = _required_signals_for_rules(analysis_engine, mode)
    return _unique_signals(required + [signal for signal in defaults if signal in allowed], limit)


def _alpha_radar_rule_state(
    *,
    analysis_engine: str,
    mode: str,
    precision_level: str,
    market_cap_filter: str,
    selected_signals: Sequence[str],
    manual_sources: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Single source of truth for signal/source constraints.

    Override order:
    1. Search engine can require core sources/signals.
    2. Radar mode can require mode-specific signals/sources.
    3. Precision and market-cap gates cap signal count and low-data.
    4. Signal-lupe requires matching data sources.
    5. Manual data-source choices are allowed only for optional sources.
    """

    limit = _signal_limit_for_precision(precision_level)
    engine_rule, mode_rule = _rule_for_engine_and_mode(analysis_engine, mode)
    allowed_signals = _signal_options_for_rules(analysis_engine, mode)
    required_signals = _required_signals_for_rules(analysis_engine, mode)
    clean_selected = [signal for signal in selected_signals or [] if signal in allowed_signals]
    blocked_signals = [
        str(signal)
        for signal in selected_signals or []
        if str(signal or "").strip() and str(signal or "").strip() not in allowed_signals
    ]
    effective_signals = _unique_signals(required_signals + clean_selected, limit)
    required_sources: dict[str, list[str]] = {key: [] for key in SOURCE_LABELS}
    recommended_sources: dict[str, list[str]] = {key: [] for key in SOURCE_LABELS}

    for source, reason in dict(engine_rule.get("required_sources") or {}).items():
        if source in required_sources:
            required_sources[source].append(str(reason))
    for source, reason in dict(mode_rule.get("required_sources") or {}).items():
        if source in required_sources:
            required_sources[source].append(str(reason))
    for signal in effective_signals:
        for source, reason in SIGNAL_SOURCE_REQUIREMENTS.get(signal, {}).items():
            required_sources[source].append(reason)
    for source, reason in dict(engine_rule.get("recommended_sources") or {}).items():
        if source in recommended_sources:
            recommended_sources[source].append(str(reason))
    for source, reason in dict(mode_rule.get("recommended_sources") or {}).items():
        if source in recommended_sources:
            recommended_sources[source].append(str(reason))

    manual_sources = dict(manual_sources or {})
    source_values: dict[str, bool] = {}
    source_locked: dict[str, bool] = {}
    source_status: dict[str, str] = {}
    source_reasons: dict[str, list[str]] = {}
    for source in SOURCE_LABELS:
        reasons = [x for x in required_sources[source] if str(x).strip()]
        recommended = [x for x in recommended_sources[source] if str(x).strip()]
        locked = bool(reasons)
        if locked:
            value = True
            status = "Paakrevd"
        elif source in manual_sources:
            value = bool(manual_sources[source])
            status = "Valgfri pa" if value else "Valgfri av"
        elif recommended:
            value = False
            status = "Anbefalt"
        else:
            value = False
            status = "Valgfri av"
        source_values[source] = value
        source_locked[source] = locked
        source_status[source] = status
        source_reasons[source] = reasons or recommended or ["Valgfri datakilde"]

    low_data_allowed = precision_level == "Utforskende" and market_cap_filter not in {"Mikro/small", "Small/mid", "Kun large/mega"}
    low_data_reason = "Tillatt: Presisjon Utforskende og ingen hard boersverdi-gate" if low_data_allowed else "Blokkert av presisjon/boersverdi: krever Utforskende og ingen hard small/large-gate"
    return {
        "signal_limit": limit,
        "allowed_signals": allowed_signals,
        "required_signals": required_signals,
        "blocked_signals": blocked_signals,
        "effective_signals": effective_signals,
        "engine_summary": str(engine_rule.get("summary") or ""),
        "mode_summary": str(mode_rule.get("summary") or ""),
        "source_values": source_values,
        "source_locked": source_locked,
        "source_status": source_status,
        "source_reasons": source_reasons,
        "low_data_allowed": low_data_allowed,
        "low_data_reason": low_data_reason,
        "override_order": [
            "Sokemotor",
            "Radar-modus",
            "Presisjon og borsverdi",
            "Signal-lupe",
            "Manuelle datakilder",
        ],
    }


def _render_source_rule_summary(rule_state: Mapping[str, Any]) -> None:
    values = rule_state.get("source_values") if isinstance(rule_state.get("source_values"), Mapping) else {}
    statuses = rule_state.get("source_status") if isinstance(rule_state.get("source_status"), Mapping) else {}
    reasons = rule_state.get("source_reasons") if isinstance(rule_state.get("source_reasons"), Mapping) else {}
    parts: list[str] = []
    for source, label in SOURCE_LABELS.items():
        status = str(statuses.get(source) or "-")
        reason_list = reasons.get(source) if isinstance(reasons.get(source), list) else []
        reason = "; ".join(str(x) for x in reason_list[:2]) if reason_list else "Valgfri datakilde"
        state = "PAA" if bool(values.get(source)) else "AV"
        parts.append(f"<b>{html.escape(label)}:</b> {html.escape(state)} · {html.escape(status)} · {html.escape(reason)}")
    st.markdown(
        "<div class='alpha-radar-rule-note'>" + "<br>".join(parts) + "</div>",
        unsafe_allow_html=True,
    )


def _render_signal_rule_summary(rule_state: Mapping[str, Any]) -> None:
    required = [str(x) for x in rule_state.get("required_signals") or []]
    effective = [str(x) for x in rule_state.get("effective_signals") or []]
    allowed = [str(x) for x in rule_state.get("allowed_signals") or []]
    optional_active = [signal for signal in effective if signal not in required]
    optional_available = [signal for signal in allowed if signal not in required]
    blocked = [str(x) for x in rule_state.get("blocked_signals") or []]
    mode_summary = str(rule_state.get("mode_summary") or rule_state.get("engine_summary") or "")

    def _chips(values: Sequence[str], cls: str) -> str:
        if not values:
            return "<span class='alpha-radar-rule-muted'>Ingen</span>"
        return "".join(f"<span class='alpha-radar-rule-chip {cls}'>{html.escape(str(value))}</span>" for value in values)

    blocked_html = ""
    if blocked:
        blocked_html = (
            "<div class='alpha-radar-rule-line'><b>Avvist av modus:</b> "
            + _chips(blocked, "blocked")
            + "</div>"
        )

    st.markdown(
        f"""
        <div class='alpha-radar-signal-rule'>
          <div><b>Modusprofil:</b> {html.escape(mode_summary or "Blandet regelsett")}</div>
          <div class='alpha-radar-rule-line'><b>Laast signal-lupe:</b> {_chips(required, "locked")}</div>
          <div class='alpha-radar-rule-line'><b>Ekstra signaler:</b> {_chips(optional_active, "optional")}</div>
          <div class='alpha-radar-rule-line'><b>Kan legges til:</b> {_chips(optional_available, "available")}</div>
          {blocked_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_run_preview(
    *,
    analysis_engine: str,
    scope: str,
    max_scan: int,
    source_tickers: Sequence[str],
    rule_state: Mapping[str, Any],
) -> None:
    source_values = rule_state.get("source_values") if isinstance(rule_state.get("source_values"), Mapping) else {}
    planned = len(source_tickers or []) if source_tickers else int(max_scan or 0)
    ticker_text = f"{len(source_tickers)} preview-tickere klare" if source_tickers else f"ikke hentet ennaa, maks {planned} planlagt"
    budget = estimate_source_budget(planned_tickers=planned, source_values=source_values)
    budget_text = source_budget_text(budget)
    st.markdown(
        f"""
        <div class='alpha-radar-run-preview'>
          <b>Kjoringsbudsjett / Run Preview</b><br>
          Motor: {html.escape(str(analysis_engine))} · Univers: {html.escape(str(scope))} · Tickere: {html.escape(ticker_text)}<br>
          <b>0 tunge kall naa.</b> Ved Kjor: {html.escape(budget_text)}. finans-/aktorsok opptil styres av kildeko/cache.
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_data_source_status(
    *,
    horizon: str,
    insider_provider: Callable[..., Mapping[str, Any] | None] | None,
    news_provider: Callable[..., Any] | None,
    earnings_provider: Callable[..., Mapping[str, Any] | None] | None,
) -> None:
    months = horizon_to_months(horizon)
    rows = build_data_source_status(horizon)
    with st.expander("Datakilde-status / markedstest", expanded=False):
        st.caption(
            f"Valgt horisont bruker {months} mnd datavindu for insider og earnings, "
            "og tilsvarende datoperiode for nyheter der kilden stoetter det. Nokler vises aldri her."
        )
        try:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        except Exception:
            st.write(rows)

        if st.button(
            "Test datakilder per marked",
            key=f"alpha_radar_probe_sources_{RADAR_UI_STATE_VERSION}_{horizon}",
            use_container_width=True,
            help="Kjorer en liten manuell API-sjekk for USA, Norge, Sverige, Danmark og Finland.",
        ):
            st.session_state[f"alpha_radar_source_probe_{RADAR_UI_STATE_VERSION}"] = probe_market_data_sources(
                horizon=horizon,
                insider_provider=insider_provider,
                earnings_provider=earnings_provider,
                news_provider=news_provider,
            )
        probe = st.session_state.get(f"alpha_radar_source_probe_{RADAR_UI_STATE_VERSION}")
        if probe:
            try:
                st.dataframe(probe, use_container_width=True, hide_index=True)
            except Exception:
                st.write(probe)


def _infer_market_from_ticker(ticker: str) -> str:
    value = str(ticker or "").strip().upper()
    if value.endswith(".OL"):
        return "Norge"
    if value.endswith(".ST"):
        return "Sverige"
    if value.endswith(".HE"):
        return "Finland"
    if value.endswith(".CO"):
        return "Danmark"
    if value.endswith(".SA"):
        return "Brasil"
    return "USA/annet"


def _market_counts(values: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ticker in values or []:
        market = _infer_market_from_ticker(str(ticker or ""))
        counts[market] = counts.get(market, 0) + 1
    return counts


def _ordered_market_items(counts: Mapping[str, int]) -> list[tuple[str, int]]:
    known = [(market, int(counts.get(market) or 0)) for market in MARKET_DISPLAY_ORDER if int(counts.get(market) or 0) > 0]
    other = sorted((str(market), int(count)) for market, count in counts.items() if market not in MARKET_DISPLAY_ORDER and int(count or 0) > 0)
    return known + other


def _format_market_counts(counts: Mapping[str, int]) -> str:
    items = _ordered_market_items(counts)
    if not items:
        return "ingen tickere"
    return ", ".join(f"{market} {count}" for market, count in items)


def _should_balance_markets(scope: str, tickers: Sequence[str]) -> bool:
    counts = _market_counts(tickers)
    return str(scope or "") in {"Alle", "Norden"} and len([count for count in counts.values() if count > 0]) > 1


def _scan_default_for_scope(scope: str, fallback: int = 120) -> int:
    value = str(scope or "").strip()
    if value == "Alle":
        return 250
    if value == "Norden":
        return 177
    if value in {"USA", "Norge", "Sverige", "Finland", "Danmark", "Brasil"}:
        return 177
    return int(fallback)


def _attach_universe_metadata(
    result: dict[str, Any],
    *,
    scope: str,
    source_tickers: Sequence[str],
    balance_markets: bool,
    fresh_universe: bool,
) -> dict[str, Any]:
    counts = _market_counts(source_tickers)
    result["universe_total"] = len(source_tickers or [])
    result["universe_market_counts"] = counts
    result["universe_fresh_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    result["universe_fresh_run"] = bool(fresh_universe)
    result["market_balance_enabled"] = bool(balance_markets or result.get("market_balance_enabled"))
    result["market_balance_note"] = (
        "Alle/Norden bruker balansert sluttliste: beste funn per marked tas med foer resten fylles etter score."
        if balance_markets
        else "Enkeltmarked eller ubalansert kilde: vanlig global score-sortering."
    )
    result["scope"] = scope
    return result


def _render_market_audit(result: Mapping[str, Any]) -> None:
    scan = result.get("market_scan_counts") if isinstance(result.get("market_scan_counts"), Mapping) else {}
    scored = result.get("market_scored_counts") if isinstance(result.get("market_scored_counts"), Mapping) else {}
    excluded = result.get("market_excluded_counts") if isinstance(result.get("market_excluded_counts"), Mapping) else {}
    found = result.get("market_candidate_counts") if isinstance(result.get("market_candidate_counts"), Mapping) else {}
    universe = result.get("universe_market_counts") if isinstance(result.get("universe_market_counts"), Mapping) else {}
    markets = {str(market) for market in list(universe) + list(scan) + list(scored) + list(excluded) + list(found)}
    if not markets:
        return
    order = [market for market in MARKET_DISPLAY_ORDER if market in markets] + sorted(market for market in markets if market not in MARKET_DISPLAY_ORDER)
    rows = []
    for market in order:
        rows.append(
            "<tr>"
            f"<td>{html.escape(market)}</td>"
            f"<td>{int(universe.get(market) or scan.get(market) or 0)}</td>"
            f"<td>{int(scan.get(market) or 0)}</td>"
            f"<td>{int(scored.get(market) or 0)}</td>"
            f"<td>{int(excluded.get(market) or 0)}</td>"
            f"<td>{int(found.get(market) or 0)}</td>"
            "</tr>"
        )
    st.markdown(
        f"""
        <div class='alpha-radar-market-audit'>
          <b>Markedskontroll</b><br>
          Univers: {int(result.get('universe_total') or result.get('scanned_count') or 0)} tickere ·
          {html.escape(str(result.get('market_balance_note') or ''))}<br>
          <table>
            <thead><tr><th>Marked</th><th>Univers</th><th>Skannet</th><th>Scoret</th><th>Ekskludert</th><th>Funn</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _ticker_digest(tickers: Sequence[str]) -> str:
    joined = "|".join(str(ticker).strip().upper() for ticker in tickers or [])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def _alpha_radar_input_context(
    *,
    scope: str,
    horizon: str,
    mode: str,
    market_cap_filter: str,
    precision_level: str,
    active_signals: Sequence[str],
    include_news: bool,
    include_insider: bool,
    include_macro: bool,
    include_results: bool,
    fill_low_data: bool,
    limit: int,
    max_scan: int,
    source_tickers: Sequence[str],
    manual_text: str,
    analysis_engine: str = "Alpha Radar",
    include_ipo: bool = False,
) -> dict[str, Any]:
    return {
        "analysis_engine": analysis_engine,
        "scope": scope,
        "horizon": horizon,
        "mode": mode,
        "market_cap_filter": market_cap_filter,
        "precision_level": precision_level,
        "active_signals": list(active_signals or []),
        "include_news": bool(include_news),
        "include_insider": bool(include_insider),
        "include_macro": bool(include_macro),
        "include_results": bool(include_results),
        "fill_low_data": bool(fill_low_data),
        "limit": int(limit),
        "max_scan": int(max_scan),
        "source_count": len(source_tickers or []),
        "source_digest": _ticker_digest(source_tickers),
        "manual_digest": hashlib.sha256(str(manual_text or "").encode("utf-8")).hexdigest()[:12],
        "include_ipo": bool(include_ipo),
    }


def _alpha_radar_fingerprint(context: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(context or {}), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _persist_active_universe_from_alpha(result: Mapping[str, Any]) -> int:
    payload = alpha_radar_result_to_active_universe_payload(result)
    tickers = list(payload.get("tickers") or [])
    st.session_state["active_universe"] = payload
    st.session_state["active_universe_tickers"] = tickers
    st.session_state["smart_universe_picker_active_v18517"] = payload
    try:
        from services.service_registry import build_service_registry

        services = build_service_registry(st.session_state)
        services.storage.write_json("active_universe.json", payload)
        services.storage.write_json("smart_universe_picker_active.json", payload)
    except Exception:
        pass
    return len(tickers)


def _render_result_actions(result: Mapping[str, Any], *, disabled: bool) -> None:
    candidates = result.get("candidates") or []
    if not candidates:
        return

    basename = alpha_radar_result_basename(result)
    tickers = alpha_radar_candidate_tickers(result)
    st.markdown("**Resultat / eksport**")
    st.caption("HTML-rapporten er printvennlig og kan lagres som PDF fra nettleserens utskriftsdialog.")

    d1, d2, d3, d4, d5 = st.columns(5)
    with d1:
        st.download_button(
            "Last ned CSV",
            data=alpha_radar_result_to_csv(result),
            file_name=f"{basename}.csv",
            mime="text/csv",
            disabled=disabled,
            use_container_width=True,
            key=f"alpha_radar_csv_v1863au_{basename}",
        )
    with d2:
        st.download_button(
            "Print/PDF HTML",
            data=alpha_radar_result_to_print_html(result),
            file_name=f"{basename}_rapport.html",
            mime="text/html",
            disabled=disabled,
            use_container_width=True,
            key=f"alpha_radar_html_v1863au_{basename}",
        )
    with d3:
        st.download_button(
            "JSON snapshot",
            data=alpha_radar_result_to_json(result),
            file_name=f"{basename}.json",
            mime="application/json",
            disabled=disabled,
            use_container_width=True,
            key=f"alpha_radar_json_v1863au_{basename}",
        )
    with d4:
        st.download_button(
            "Excel XLSX",
            data=alpha_radar_result_to_xlsx(result),
            file_name=f"{basename}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=disabled,
            use_container_width=True,
            key=f"alpha_radar_xlsx_v1863au_{basename}",
        )
    with d5:
        st.download_button(
            "Tickerliste",
            data=alpha_radar_result_to_ticker_text(result),
            file_name=f"{basename}_tickers.txt",
            mime="text/plain",
            disabled=disabled,
            use_container_width=True,
            key=f"alpha_radar_tickers_v1863au_{basename}",
        )

    a1, a2, a3, a4 = st.columns(4)
    with a1:
        if st.button("Lagre snapshot", key="alpha_radar_save_snapshot_v1863au", disabled=disabled, use_container_width=True):
            saved = save_alpha_radar_snapshot(result)
            st.success(f"Snapshot lagret med {saved} tickere.")
    with a2:
        if st.button("Send til observasjonsliste", key="alpha_radar_observation_list_v1863au", disabled=disabled, use_container_width=True):
            saved = save_alpha_radar_observation_list(result)
            st.success(f"Observasjonsliste oppdatert med {saved} tickere.")
    with a3:
        if st.button("Bruk som aktivt Analyseunivers", key="alpha_radar_active_universe_v1863au", disabled=disabled, use_container_width=True):
            saved = _persist_active_universe_from_alpha(result)
            st.success(f"Alpha Radar-resultatet er satt som aktivt analyseunivers med {saved} tickere.")
    with a4:
        default_decision = tickers[: min(8, len(tickers))]
        decision_tickers = st.multiselect(
            "Til beslutning",
            tickers,
            default=default_decision,
            key=f"alpha_radar_decision_tickers_v1863ba_{basename}",
            disabled=disabled,
            max_selections=min(20, len(tickers)) if tickers else None,
        )
        if st.button("Send til Beslutningsgrunnlag", key=f"alpha_radar_decision_queue_v1863ba_{basename}", disabled=disabled or not decision_tickers, use_container_width=True):
            rows = decision_source_rows_from_radar_result(result, decision_tickers)
            current = st.session_state.get(DECISION_QUEUE_KEY, [])
            st.session_state[DECISION_QUEUE_KEY] = add_decision_rows(current, rows)
            st.success(f"Sendte {len(rows)} kandidater til Beslutningsgrunnlag.")

    if tickers:
        st.caption("Tickere i resultatet: " + ", ".join(tickers[:20]))


def _render_alpha_radar_css() -> None:
    st.markdown(
        """
        <style>
        .alpha-radar-note {
            border: 1px solid rgba(102, 174, 255, 0.26);
            background: rgba(20, 30, 42, 0.72);
            border-radius: 8px;
            padding: 0.70rem 0.85rem;
            margin: 0.45rem 0 0.72rem 0;
            color: rgba(245, 248, 255, 0.92);
        }
        .alpha-radar-row {
            border: 1px solid rgba(120, 160, 210, 0.30);
            background: rgba(14, 20, 30, 0.86);
            border-radius: 8px;
            padding: 0.72rem 0.82rem;
            margin: 0.45rem 0;
            color: rgba(245, 248, 255, 0.92);
        }
        .alpha-radar-top {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 0.8rem;
            margin-bottom: 0.48rem;
        }
        .alpha-radar-title {
            font-size: 0.98rem;
            font-weight: 800;
            line-height: 1.18;
            color: #f6f8ff;
        }
        .alpha-radar-sub {
            color: rgba(230, 238, 255, 0.67);
            font-size: 0.76rem;
            margin-top: 0.12rem;
        }
        .alpha-radar-score {
            min-width: 4.8rem;
            text-align: right;
            color: #7de2b8;
            font-size: 1.26rem;
            font-weight: 850;
        }
        .alpha-radar-metrics {
            display: grid;
            grid-template-columns: repeat(7, minmax(76px, 1fr));
            gap: 0.32rem;
            margin: 0.42rem 0 0.50rem 0;
        }
        .alpha-radar-metric {
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 7px;
            padding: 0.30rem 0.36rem;
            min-height: 2.65rem;
        }
        .alpha-radar-metric b {
            display: block;
            font-size: 0.82rem;
            color: #f5f8ff;
            line-height: 1.05;
        }
        .alpha-radar-metric span {
            display: block;
            font-size: 0.66rem;
            color: rgba(230, 238, 255, 0.62);
            line-height: 1.12;
            margin-top: 0.10rem;
        }
        .alpha-radar-why {
            font-size: 0.84rem;
            line-height: 1.34;
            color: rgba(245, 248, 255, 0.88);
            margin: 0.44rem 0;
        }
        .alpha-radar-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 0.28rem;
            margin-top: 0.42rem;
        }
        .alpha-radar-tag {
            border: 1px solid rgba(125, 226, 184, 0.24);
            color: rgba(238, 255, 248, 0.9);
            border-radius: 999px;
            padding: 0.10rem 0.40rem;
            font-size: 0.68rem;
        }
        .alpha-radar-reject {
            color: rgba(255, 229, 178, 0.90);
            font-size: 0.74rem;
            margin-top: 0.42rem;
            line-height: 1.28;
            overflow-wrap: anywhere;
            max-height: 3.9rem;
            overflow: hidden;
        }
        .alpha-radar-rule-note,
        .alpha-radar-signal-rule,
        .alpha-radar-market-audit,
        .alpha-radar-run-preview {
            border: 1px solid rgba(125, 211, 252, 0.28);
            background: rgba(8, 47, 73, 0.30);
            border-radius: 8px;
            padding: 0.58rem 0.72rem;
            margin: 0.40rem 0 0.62rem 0;
            color: rgba(226, 242, 254, 0.92);
            font-size: 0.78rem;
            line-height: 1.32;
        }
        .alpha-radar-run-preview {
            border-color: rgba(74, 222, 128, 0.32);
            background: rgba(6, 78, 59, 0.24);
        }
        .alpha-radar-market-audit {
            border-color: rgba(125, 211, 252, 0.34);
            background: rgba(8, 47, 73, 0.22);
        }
        .alpha-radar-market-audit table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 0.42rem;
            font-size: 0.74rem;
        }
        .alpha-radar-market-audit th,
        .alpha-radar-market-audit td {
            border: 1px solid rgba(125, 211, 252, 0.16);
            padding: 0.22rem 0.34rem;
            text-align: left;
        }
        .alpha-radar-market-audit th {
            color: #bae6fd;
            font-weight: 900;
            background: rgba(15, 23, 42, 0.62);
        }
        .alpha-radar-signal-rule {
            border-color: rgba(125, 211, 252, 0.40);
            background: rgba(15, 23, 42, 0.72);
            margin-top: 0.22rem;
        }
        .alpha-radar-rule-line {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.28rem;
            margin-top: 0.30rem;
        }
        .alpha-radar-rule-chip {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 0.12rem 0.46rem;
            font-size: 0.70rem;
            font-weight: 850;
            line-height: 1.15;
            border: 1px solid rgba(148, 163, 184, 0.34);
            background: rgba(15, 23, 42, 0.88);
            color: #e2e8f0;
        }
        .alpha-radar-rule-chip.locked {
            border-color: rgba(34, 197, 94, 0.56);
            background: rgba(16, 65, 52, 0.56);
            color: #dcfce7;
        }
        .alpha-radar-rule-chip.optional {
            border-color: rgba(56, 189, 248, 0.50);
            background: rgba(8, 47, 73, 0.62);
            color: #e0f2fe;
        }
        .alpha-radar-rule-chip.available {
            border-color: rgba(148, 163, 184, 0.34);
            background: rgba(30, 41, 59, 0.62);
            color: #cbd5e1;
        }
        .alpha-radar-rule-chip.blocked {
            border-color: rgba(250, 204, 21, 0.50);
            background: rgba(120, 53, 15, 0.42);
            color: #fde68a;
        }
        .alpha-radar-rule-muted {
            color: rgba(203, 213, 225, 0.74);
            font-size: 0.72rem;
        }
        @media (max-width: 980px) {
            .alpha-radar-metrics { grid-template-columns: repeat(3, minmax(0, 1fr)); }
        }
        @media (max-width: 640px) {
            .alpha-radar-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .alpha-radar-score { min-width: 3.8rem; font-size: 1.05rem; }
        }
        div[data-testid="stMultiSelect"] [data-baseweb="tag"] {
            max-width: 100% !important;
            white-space: normal !important;
            overflow: visible !important;
            height: auto !important;
            min-height: 30px !important;
            border: 1px solid rgba(56, 189, 248, 0.58) !important;
            background: rgba(8, 47, 73, 0.76) !important;
            color: #e0f2fe !important;
        }
        div[data-testid="stMultiSelect"] [data-baseweb="tag"] span {
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: clip !important;
            line-height: 1.14 !important;
            color: #e0f2fe !important;
            -webkit-text-fill-color: #e0f2fe !important;
        }
        div[data-testid="stMultiSelect"] [data-baseweb="tag"] svg {
            color: #bae6fd !important;
            fill: #bae6fd !important;
        }
        div[data-testid="stMultiSelect"] > div {
            min-height: 44px !important;
            align-items: flex-start !important;
        }
        div[data-testid="stCheckbox"] label:has(input:checked) {
            border-color: rgba(34, 197, 94, 0.46) !important;
            background: rgba(16, 65, 52, 0.14) !important;
        }
        div[data-testid="stCheckbox"] label:has(input:disabled) {
            opacity: 0.88 !important;
        }
        @media (max-width: 700px) {
            div[data-testid="stMultiSelect"] [data-baseweb="tag"] {
                width: auto !important;
                max-width: calc(100vw - 92px) !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _candidate_row(candidate: Mapping[str, Any]) -> str:
    title = html.escape(f"#{candidate.get('rank', '-')} {candidate.get('ticker', '-')}")
    name = html.escape(str(candidate.get("name") or ""))
    market = html.escape(str(candidate.get("market") or "-"))
    horizon = html.escape(str(candidate.get("horizon") or "-"))
    mode = html.escape(str(candidate.get("mode") or "-"))
    why_now = html.escape(str(candidate.get("why_now") or candidate.get("thesis") or ""))
    signals = candidate.get("signals") if isinstance(candidate.get("signals"), list) else []
    rejects = candidate.get("reject_reasons") if isinstance(candidate.get("reject_reasons"), list) else []
    warnings = candidate.get("warning_reasons") if isinstance(candidate.get("warning_reasons"), list) else []
    data_quality = html.escape(str(candidate.get("data_quality") or "OK"))
    market_cap = candidate.get("market_cap")
    cap_text = str(candidate.get("market_cap_display") or market_cap_display(market_cap, candidate.get("market_cap_currency")) or "-")
    cap_nok = candidate.get("market_cap_nok_estimate")
    if cap_nok not in {None, ""} and str(candidate.get("market_cap_currency") or "").upper() != "NOK":
        cap_text = f"{cap_text} (ca. {market_cap_display(cap_nok, 'NOK')})"
    tags = "".join(f"<span class='alpha-radar-tag'>{html.escape(str(signal))}</span>" for signal in signals[:6])
    factor_quality = candidate.get("factor_quality") if isinstance(candidate.get("factor_quality"), Mapping) else {}

    def compact_list(values: Sequence[Any], fallback: str, *, max_items: int = 4, max_chars: int = 180) -> str:
        seen: set[str] = set()
        clean: list[str] = []
        for value in values or []:
            text = " ".join(str(value or "").split())
            if not text or text in seen:
                continue
            seen.add(text)
            if len(text) > 78:
                text = text[:75].rstrip() + "..."
            clean.append(text)
            if len(clean) >= max_items:
                break
        out = "; ".join(clean) if clean else fallback
        if len(out) > max_chars:
            out = out[: max_chars - 3].rstrip() + "..."
        return out

    def compact_text(value: Any, *, max_chars: int = 190) -> str:
        text = " ".join(str(value or "").split())
        if len(text) > max_chars:
            return text[: max_chars - 3].rstrip() + "..."
        return text

    def metric(value_key: str, label: str, quality_key: str | None = None) -> str:
        quality = str(factor_quality.get(quality_key or value_key) or "").strip()
        caption = label if not quality else f"{label} Â· {quality}"
        return f"<div class='alpha-radar-metric'><b>{_fmt_score(candidate.get(value_key))}</b><span>{html.escape(caption)}</span></div>"

    reject_text = compact_list(rejects, "ingen harde avslag")
    warning_text = compact_list(warnings, "ingen datavarsler")
    review = compact_text(candidate.get("manual_review"))

    return f"""
    <div class="alpha-radar-row">
      <div class="alpha-radar-top">
        <div>
          <div class="alpha-radar-title">{title}</div>
          <div class="alpha-radar-sub">{name} | {market} | {horizon} | {mode} | data: {data_quality} | cap: {html.escape(cap_text)}</div>
        </div>
        <div class="alpha-radar-score">{_fmt_score(candidate.get("hidden_potential_score", candidate.get("alpha_score")))}</div>
      </div>
      <div class="alpha-radar-metrics">
        {metric("underfollowed_score", "oversett", "underfollowed")}
        {metric("inflection_score", "vendepunkt", "inflection")}
        {metric("catalyst_score", "katalysator", "catalyst")}
        {metric("insider_score", "insider", "insider_bjellesau")}
        {metric("bjellesau_score", "bjellesau", "insider_bjellesau")}
        {metric("volume_score", "volum", "volume_accumulation")}
        {metric("macro_score", "makro", "macro_second_order")}
      </div>
      <div class="alpha-radar-why">{why_now}</div>
      <div class="alpha-radar-tags">{tags}</div>
      <div class="alpha-radar-reject"><b>Sjekk/avslag:</b> {html.escape(reject_text)}. <b>Datavarsel:</b> {html.escape(warning_text)}. {html.escape(review)}</div>
    </div>
    """


def _render_candidates(candidates: Sequence[Mapping[str, Any]], grouped: bool, empty_label: str = "Alpha Radar") -> None:
    if not candidates:
        st.info(f"Ingen {empty_label}-funn ennaa. Velg univers og trykk Kjor.")
        return

    if grouped:
        markets: dict[str, list[Mapping[str, Any]]] = {}
        for candidate in candidates:
            market = str(candidate.get("market") or "Ukjent")
            markets.setdefault(market, []).append(candidate)
        for market, rows in markets.items():
            st.markdown(f"**{html.escape(market)} ({len(rows)})**")
            for row in rows:
                st.markdown(_candidate_row(row), unsafe_allow_html=True)
    else:
        for row in candidates:
            st.markdown(_candidate_row(row), unsafe_allow_html=True)


def render_alpha_radar_panel(
    *,
    resolve_tickers: Callable[[str, int, str], Sequence[str]],
    score_provider: Callable[..., Mapping[str, Any] | None],
    data_enricher: Callable[..., Mapping[str, Any]] | None = None,
    insider_provider: Callable[..., Mapping[str, Any] | None] | None = None,
    news_provider: Callable[..., Sequence[Mapping[str, Any]]] | None = None,
    earnings_provider: Callable[..., Mapping[str, Any] | None] | None = None,
    market_options: Sequence[str] | None = None,
    no_selection_label: str = "Velg marked",
) -> None:
    """Render the explicit-run Alpha Radar V2 panel."""

    _render_alpha_radar_css()
    analysis_engine = st.radio(
        "Sokemotor",
        ["Alpha Radar", "Early Warning V1"],
        horizontal=True,
        key="alpha_radar_engine_v1863au",
        help="Alpha Radar leter etter skjulte hypoteser. Early Warning V1 rangerer forventningsendring, earnings, fundamental akselerasjon og markedsbekreftelse.",
    )
    if analysis_engine == "Early Warning V1":
        st.subheader("Early Warning V1")
        st.caption("Tidligvarslingsmotor for ferske insider-/bjellesau-spor, nyheter, forventningsendring og tidlig bekreftelse.")
        st.markdown(
            "<div class='alpha-radar-note'>Early Warning skal finne andre ting enn Alpha Radar: tidlige kildespor, "
            "konkrete insider-/bjellesauhendelser, nyhetskatalysatorer, revisjoner og svake signaler som maa "
            "bekreftes manuelt. Den er ikke en hidden-potential score og starter ingen handel.</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "Early Warning V1 jakter andre signaler enn Alpha Radar: ferske insider-/bjellesau-spor, nyhetskatalysatorer, "
            "forventningsendring og tidlig markedsbekreftelse. Euronext/Norden tas med via .OL, .ST, .HE og .CO naar universet inneholder disse markedene."
        )
    else:
        st.subheader("Alpha Radar V2")
        st.caption("Contrarian / Hidden Potential Score for inntil 60 manuelle aksjehypoteser.")
        st.markdown(
            "<div class='alpha-radar-note'>V2 leter etter underdekkede vendepunkter, why-now-signaler, "
            "insider/bjellesauer, uvanlig volum og andreordens makro/ravare-effekter. Kjente/overdekkede "
            "megacaps faar crowding-straff. Ingen handel starter her.</div>",
            unsafe_allow_html=True,
        )

    def _pipeline_input_count(stage_id: str) -> int:
        try:
            from services.analysis_pipeline_service import get_analysis_pipeline_service
            from services.state_service import get_state_service
            from services.storage_service import get_storage_service

            pipeline = get_analysis_pipeline_service(
                state_service=get_state_service(st.session_state),
                storage_service=get_storage_service(),
            )
            return len(pipeline.candidates_for_stage(stage_id))
        except Exception:
            return 0

    c1, c2, c3 = st.columns([1.30, 0.88, 0.72])
    with c1:
        scope = st.selectbox(
            "Univers / marked",
            _market_options(no_selection_label, market_options),
            key="alpha_radar_scope_v1863au",
        )
    with c2:
        mode = st.selectbox("Radar-modus", ALPHA_RADAR_MODES, key="alpha_radar_mode_v1863au")
    with c3:
        limit_default = 30 if scope not in {no_selection_label, "Manuell liste"} else 15
        limit_scope_key = hashlib.sha256(str(scope or "").encode("utf-8")).hexdigest()[:8]
        pipeline_stage_id = "early_warning" if analysis_engine == "Early Warning V1" else "alpha_radar"
        pipeline_input_count = _pipeline_input_count(pipeline_stage_id) if scope == "Analyseflyt input" else 0
        limit_max = max(1, pipeline_input_count) if pipeline_input_count > 0 else 60
        limit_default = min(limit_default, limit_max)
        limit_key = f"alpha_radar_limit_{RADAR_UI_STATE_VERSION}_{limit_scope_key}"
        if int(st.session_state.get(limit_key, limit_default) or limit_default) > int(limit_max):
            st.session_state[limit_key] = int(limit_default)
        limit = st.slider("Funn", 1, limit_max, limit_default, 1, key=limit_key)
        if pipeline_input_count > 0:
            st.caption(f"Maks er låst til inputpakken fra forrige test: {pipeline_input_count} kandidater.")

    c4, c5, c6, c6b = st.columns([0.78, 0.82, 0.82, 1.28])
    with c4:
        horizon = st.radio("Horisont", ["1m", "3m", "6m", "12m"], horizontal=True, key="alpha_radar_horizon_v1863au")
    with c5:
        cap_options = _cap_options_for_mode(mode)
        market_cap_filter = st.selectbox("Borsverdi", cap_options, index=min(1, len(cap_options) - 1) if mode == "Skjulte small/mid caps" else 0, key="alpha_radar_cap_v1863au")
    with c6:
        precision_level = st.selectbox("Presisjon", PRECISION_LEVELS, index=0, key="alpha_radar_precision_v1863au")
    with c6b:
        signal_limit = _signal_limit_for_precision(precision_level)
        required_signals = _required_signals_for_rules(analysis_engine, mode)
        signal_options = [signal for signal in _signal_options_for_rules(analysis_engine, mode) if signal not in required_signals]
        optional_limit = max(0, signal_limit - len(required_signals))
        signal_key = f"alpha_radar_signal_lupe_optional_{RADAR_UI_STATE_VERSION}_{analysis_engine}_{mode}_{precision_level}"
        default_optional_signals = _optional_signal_defaults(analysis_engine, mode, precision_level)[:optional_limit]
        reset_key = f"alpha_radar_signal_reset_{RADAR_UI_STATE_VERSION}_{analysis_engine}_{mode}_{precision_level}"
        if st.button("Bruk modusprofil", key=reset_key, use_container_width=True, help="Nullstiller ekstra signaler til det valgt sokemotor og radar-modus krever."):
            st.session_state[signal_key] = list(default_optional_signals)
        stored_signals = st.session_state.get(signal_key)
        if signal_key not in st.session_state:
            st.session_state[signal_key] = list(default_optional_signals)
        elif isinstance(stored_signals, list):
            normalized_stored = [
                signal
                for signal in _alpha_radar_rule_state(
                    analysis_engine=analysis_engine,
                    mode=mode,
                    precision_level=precision_level,
                    market_cap_filter=market_cap_filter,
                    selected_signals=stored_signals,
                )["effective_signals"]
                if signal not in required_signals and signal in signal_options
            ][:optional_limit]
            if list(stored_signals) != list(normalized_stored):
                st.session_state[signal_key] = list(normalized_stored)
        if optional_limit <= 0:
            st.caption(f"Signal-lupe er laast av {analysis_engine}/{mode}.")
            active_optional_signals = []
        else:
            active_optional_signals = st.multiselect(
                "Signal-lupe: ekstra",
                signal_options,
                default=list(st.session_state.get(signal_key) or default_optional_signals),
                key=signal_key,
                max_selections=optional_limit,
                help=f"Modus har {len(required_signals)} laaste signaler. Du kan legge til maks {optional_limit} ekstra i {precision_level}.",
            )
        active_signals = _alpha_radar_rule_state(
                analysis_engine=analysis_engine,
                mode=mode,
                precision_level=precision_level,
                market_cap_filter=market_cap_filter,
                selected_signals=list(active_optional_signals or []),
            )["effective_signals"]
        st.caption(f"Signal-lupe = vekting. {len(required_signals)} laast av modus, maks {signal_limit} totalt i {precision_level}.")

    normalized_preview = normalize_alpha_radar_parameters(
        mode=mode,
        market_cap_filter=market_cap_filter,
        precision_level=precision_level,
        active_signals=list(active_signals or []),
        fill_low_data=False,
    )
    effective_cap_filter = normalized_preview["market_cap_filter"]
    effective_signals = list(normalized_preview["active_signals"] or [])
    if not effective_signals:
        st.info("Signal-lupe er tom: Standard/bred vekting brukes. Datakilder kan fortsatt brukes som stotte, men faar ikke ekstra vekt.")
    if normalized_preview.get("parameter_warnings"):
        st.warning(" | ".join(normalized_preview["parameter_warnings"]))

    source_keys = {source: f"alpha_radar_source_{source}_{RADAR_UI_STATE_VERSION}" for source in SOURCE_LABELS}
    source_profile_key = f"alpha_radar_source_profile_{RADAR_UI_STATE_VERSION}"
    source_profile = f"{analysis_engine}|{mode}"
    if st.session_state.get(source_profile_key) != source_profile:
        for source_key in source_keys.values():
            st.session_state.pop(source_key, None)
        st.session_state[source_profile_key] = source_profile
    manual_source_state = {
        source: True
        for source in SOURCE_LABELS
        if bool(st.session_state.get(source_keys[source], False))
    }
    rule_state = _alpha_radar_rule_state(
        analysis_engine=analysis_engine,
        mode=mode,
        precision_level=precision_level,
        market_cap_filter=effective_cap_filter,
        selected_signals=effective_signals,
        manual_sources=manual_source_state,
    )
    effective_signals = list(rule_state["effective_signals"])
    source_values = dict(rule_state["source_values"])
    source_locked = dict(rule_state["source_locked"])
    source_reasons = dict(rule_state["source_reasons"])
    _render_signal_rule_summary(rule_state)
    st.caption("Datakilder = datagrunnlag. Paa/låst-status styres av sokemotor, modus, presisjon/borsverdi og Signal-lupe i den rekkefolgen.")

    c7, c8, c9, c10, c11, c12 = st.columns([0.72, 0.72, 0.72, 0.72, 0.78, 0.90])
    with c7:
        scan_scope_key = hashlib.sha256(str(scope or "").encode("utf-8")).hexdigest()[:8]
        scan_max = max(1, pipeline_input_count) if scope == "Analyseflyt input" and pipeline_input_count > 0 else 250
        scan_min = 1 if scan_max < 5 else 5
        scan_default = min(max(_scan_default_for_scope(scope), scan_min), scan_max)
        scan_key = f"alpha_radar_scan_limit_{RADAR_UI_STATE_VERSION}_{scan_scope_key}"
        stored_scan = int(st.session_state.get(scan_key, scan_default) or scan_default)
        if stored_scan < int(scan_min) or stored_scan > int(scan_max):
            st.session_state[scan_key] = int(scan_default)
        max_scan = st.slider("Maks scan", scan_min, scan_max, scan_default, 1, key=scan_key)
    with c8:
        if source_locked["news"]:
            locked_news_key = f"{source_keys['news']}_locked"
            st.session_state[locked_news_key] = True
            include_news = st.checkbox(
                "Nyheter",
                value=True,
                key=locked_news_key,
                disabled=True,
                help=" | ".join(str(x) for x in source_reasons["news"]),
            )
        else:
            if source_keys["news"] not in st.session_state:
                st.session_state[source_keys["news"]] = source_values["news"]
            include_news = st.checkbox(
                "Nyheter",
                value=source_values["news"],
                key=source_keys["news"],
                disabled=False,
                help=" | ".join(str(x) for x in source_reasons["news"]),
            )
    with c9:
        if source_locked["insider"]:
            locked_insider_key = f"{source_keys['insider']}_locked"
            st.session_state[locked_insider_key] = True
            include_insider_signal = st.checkbox(
                "Insider",
                value=True,
                key=locked_insider_key,
                disabled=True,
                help=" | ".join(str(x) for x in source_reasons["insider"]),
            )
        else:
            if source_keys["insider"] not in st.session_state:
                st.session_state[source_keys["insider"]] = source_values["insider"]
            include_insider_signal = st.checkbox(
                "Insider",
                value=source_values["insider"],
                key=source_keys["insider"],
                disabled=False,
                help=" | ".join(str(x) for x in source_reasons["insider"]),
            )
    with c10:
        if source_locked["macro"]:
            locked_macro_key = f"{source_keys['macro']}_locked"
            st.session_state[locked_macro_key] = True
            include_macro = st.checkbox(
                "Ravarer/makro",
                value=True,
                key=locked_macro_key,
                disabled=True,
                help=" | ".join(str(x) for x in source_reasons["macro"]),
            )
        else:
            if source_keys["macro"] not in st.session_state:
                st.session_state[source_keys["macro"]] = source_values["macro"]
            include_macro = st.checkbox(
                "Ravarer/makro",
                value=source_values["macro"],
                key=source_keys["macro"],
                disabled=False,
                help=" | ".join(str(x) for x in source_reasons["macro"]),
            )
    with c11:
        if source_locked["results"]:
            locked_results_key = f"{source_keys['results']}_locked"
            st.session_state[locked_results_key] = True
            include_results = st.checkbox(
                "Resultater",
                value=True,
                key=locked_results_key,
                disabled=True,
                help=" | ".join(str(x) for x in source_reasons["results"]),
            )
        else:
            if source_keys["results"] not in st.session_state:
                st.session_state[source_keys["results"]] = source_values["results"]
            include_results = st.checkbox(
                "Resultater",
                value=source_values["results"],
                key=source_keys["results"],
                disabled=False,
                help=" | ".join(str(x) for x in source_reasons["results"]),
            )
    manual_source_state = {
        source: True
        for source, value in {
            "news": bool(include_news),
            "insider": bool(include_insider_signal),
            "macro": bool(include_macro),
            "results": bool(include_results),
        }.items()
        if value
    }
    rule_state = _alpha_radar_rule_state(
        analysis_engine=analysis_engine,
        mode=mode,
        precision_level=precision_level,
        market_cap_filter=effective_cap_filter,
        selected_signals=effective_signals,
        manual_sources=manual_source_state,
    )
    source_values = dict(rule_state["source_values"])
    include_news = bool(source_values["news"])
    include_insider_signal = bool(source_values["insider"])
    include_macro = bool(source_values["macro"])
    include_results = bool(source_values["results"])
    low_data_allowed = bool(rule_state["low_data_allowed"])
    with c12:
        if not low_data_allowed:
            st.session_state[f"alpha_radar_fill_low_data_{RADAR_UI_STATE_VERSION}"] = False
        fill_low_data = st.checkbox(
            "Fyll opp lav-data",
            value=False,
            key=f"alpha_radar_fill_low_data_{RADAR_UI_STATE_VERSION}",
            disabled=not low_data_allowed,
            help=str(rule_state.get("low_data_reason") or ""),
        )
    if not low_data_allowed:
        fill_low_data = False
        st.caption(str(rule_state.get("low_data_reason") or "Lav-data utfylling er blokkert."))
    _render_source_rule_summary(rule_state)
    include_ipo = False
    if analysis_engine == "Early Warning V1":
        include_ipo = st.checkbox(
            "Merk IPO/pre-IPO som separat omraade",
            value=False,
            key="early_warning_include_ipo_v1863au",
            help="Dette er ikke en ekstra tickerkilde i denne V1-rangeringen. IPO/pre-IPO maa behandles som separat omraade fordi mange mangler ticker/boershistorikk.",
        )
        if include_ipo:
            st.caption("IPO/pre-IPO markeres separat og legges ikke oppaa de boersnoterte tickerne i 177-universet. Egen IPO-motor maa brukes for kalender/rykter uten ticker.")

    manual_text = ""
    if scope == "Manuell liste":
        manual_text = st.text_area(
            "Manuelle tickere",
            value="",
            placeholder="EQNR.OL, VOLV-B.ST, NOVO-B.CO, NOKIA.HE, PETR4.SA",
            key="alpha_radar_manual_v1863au",
            height=88,
        )

    universe_request = {
        "scope": scope,
        "max_scan": int(max_scan),
        "manual_digest": hashlib.sha256(str(manual_text or "").encode("utf-8")).hexdigest()[:12],
    }
    universe_request_key = _alpha_radar_fingerprint(universe_request)
    preview_key = "alpha_radar_universe_preview_v1863au"
    preview = st.session_state.get(preview_key) if isinstance(st.session_state.get(preview_key), Mapping) else {}
    source_tickers = list(preview.get("tickers") or []) if preview.get("request_key") == universe_request_key else []

    refresh_universe = st.button(
        "Oppdater univers-preview",
        key="alpha_radar_refresh_universe_v1863au",
        use_container_width=True,
        disabled=(scope == no_selection_label or (scope == "Manuell liste" and not manual_text.strip())),
        help="Henter tickerlisten for valgte marked. Dette er eneste univershenting foer Kjor.",
    )
    if refresh_universe:
        try:
            source_tickers = list(resolve_tickers(scope, int(max_scan), manual_text) or [])
            st.session_state[preview_key] = {
                "request_key": universe_request_key,
                "tickers": source_tickers,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
        except Exception as exc:
            source_tickers = []
            st.warning(f"Kunne ikke hente univers: {exc}")

    if source_tickers:
        market_count_text = _format_market_counts(_market_counts(source_tickers))
        if len(source_tickers) < int(max_scan):
            st.caption(
                f"Univers klart: {len(source_tickers)} tickere. Maks scan er {int(max_scan)}, "
                f"men universkilden har bare {len(source_tickers)} tickere for dette valget akkurat naa. Enkeltmarked bruker ikke Alle-kvoten. "
                f"Fordeling: {market_count_text}. Eksempel: {', '.join(source_tickers[:10])}"
            )
        else:
            st.caption(f"Skannes ved neste Kjor: {len(source_tickers)} tickere av maks {int(max_scan)}. Enkeltmarked bruker egen grense, ikke Alle-kvote. Fordeling: {market_count_text}. Eksempel: {', '.join(source_tickers[:10])}")
    else:
        st.info("Univers-preview er ikke hentet for gjeldende valg. Menyvalg starter ingen scan; trykk Oppdater univers-preview eller Kjor.")
    st.caption("Kjor henter alltid ferskt run-univers og nuller gammel tickerliste/teller foer scan. Preview-cache brukes bare til visning.")

    _render_run_preview(
        analysis_engine=analysis_engine,
        scope=scope,
        max_scan=int(max_scan),
        source_tickers=source_tickers,
        rule_state=rule_state,
    )
    _render_data_source_status(
        horizon=horizon,
        insider_provider=insider_provider,
        news_provider=news_provider,
        earnings_provider=earnings_provider,
    )

    input_context = _alpha_radar_input_context(
        scope=scope,
        horizon=horizon,
        mode=mode,
        market_cap_filter=effective_cap_filter,
        precision_level=precision_level,
        active_signals=effective_signals,
        include_news=include_news,
        include_insider=include_insider_signal,
        include_macro=include_macro,
        include_results=include_results,
        fill_low_data=fill_low_data,
        limit=int(limit),
        max_scan=int(max_scan),
        source_tickers=source_tickers,
        manual_text=manual_text,
        analysis_engine=analysis_engine,
        include_ipo=include_ipo,
    )
    input_fingerprint = _alpha_radar_fingerprint(input_context)

    show_mode = st.radio(
        "Visning",
        ["Samlet rangering", "Gruppert per marked"],
        horizontal=True,
        key="alpha_radar_show_mode_v1863au",
    )

    run_clicked = st.button(
        "Kjor Early Warning V1" if analysis_engine == "Early Warning V1" else "Kjor Alpha Radar V2",
        key="alpha_radar_run_v1863au",
        type="primary",
        use_container_width=True,
        disabled=(scope == no_selection_label or (scope == "Manuell liste" and not manual_text.strip())),
    )

    if run_clicked:
        st.session_state[LAST_RESULT_KEY] = {}
        source_tickers = []
        try:
            source_tickers = list(resolve_tickers(scope, int(max_scan), manual_text) or [])
            st.session_state[preview_key] = {
                "request_key": universe_request_key,
                "tickers": source_tickers,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "fresh_run": True,
            }
        except Exception as exc:
            source_tickers = []
            st.warning(f"Kunne ikke hente univers: {exc}")
        if not source_tickers:
            st.warning("Fant ingen tickere aa skanne for gjeldende valg.")
            return
        balance_markets = _should_balance_markets(scope, source_tickers)
        st.caption(
            f"Ferskt run-univers: {len(source_tickers)} tickere. "
            + (f"Universkilden har bare {len(source_tickers)} tickere under maks {int(max_scan)}. " if len(source_tickers) < int(max_scan) else "")
            + f"Fordeling: {_format_market_counts(_market_counts(source_tickers))}."
        )
        input_context = _alpha_radar_input_context(
            scope=scope,
            horizon=horizon,
            mode=mode,
            market_cap_filter=effective_cap_filter,
            precision_level=precision_level,
            active_signals=effective_signals,
            include_news=include_news,
            include_insider=include_insider_signal,
            include_macro=include_macro,
            include_results=include_results,
            fill_low_data=fill_low_data,
            limit=int(limit),
            max_scan=int(max_scan),
            source_tickers=source_tickers,
            manual_text=manual_text,
            analysis_engine=analysis_engine,
            include_ipo=include_ipo,
        )
        input_fingerprint = _alpha_radar_fingerprint(input_context)
        progress_bar = st.progress(0, text=f"Starter {analysis_engine}: 0/{len(source_tickers)}")
        progress_line = st.empty()

        def _progress_callback(event: Mapping[str, Any]) -> None:
            total = max(1, int(event.get("total") or len(source_tickers) or 1))
            completed = max(0, min(total, int(event.get("completed") or 0)))
            pct = int(round((completed / total) * 100))
            ticker_now = str(event.get("ticker") or "")
            status = str(event.get("status") or "scanner")
            progress_bar.progress(
                min(100, pct),
                text=f"{completed}/{total} tickere | {status}" + (f" | {ticker_now}" if ticker_now else ""),
            )
            progress_line.caption(
                f"Scoret {int(event.get('scored_count') or 0)} | "
                f"ekskludert {int(event.get('excluded_count') or 0)} | "
                f"lav-data {int(event.get('low_data_count') or 0)} | "
                f"hoppet over {int(event.get('skipped_count') or 0)}"
            )

        def enriched_score_provider(ticker: str, use_news: bool = False, include_insider: bool = False):
            row = score_provider(ticker, use_news=use_news, include_insider=include_insider)
            if data_enricher is None:
                return row
            return data_enricher(
                row,
                ticker=ticker,
                include_news=bool(include_news),
                include_insider=bool(include_insider_signal),
                include_macro=bool(include_macro),
                include_results=bool(include_results),
                mode="Early Warning V1" if analysis_engine == "Early Warning V1" else mode,
                active_signals=list(effective_signals or []),
                news_provider=news_provider,
                insider_provider=insider_provider,
                earnings_provider=earnings_provider,
                horizon=horizon,
            )

        if analysis_engine == "Early Warning V1":
            result = run_early_warning(
                source_tickers,
                horizon=horizon,
                limit=int(limit),
                max_scan=int(max_scan),
                include_news=bool(include_news),
                include_insider=bool(include_insider_signal),
                include_macro=bool(include_macro),
                include_results=bool(include_results),
                include_ipo=bool(include_ipo),
                score_provider=enriched_score_provider,
                progress_callback=_progress_callback,
                balance_markets=balance_markets,
                data_window_months=horizon_to_months(horizon),
            )
        else:
            result = run_alpha_radar(
                source_tickers,
                horizon=horizon,
                limit=int(limit),
                max_scan=int(max_scan),
                include_news=bool(include_news),
                include_insider=bool(include_insider_signal),
                mode=mode,
                market_cap_filter=effective_cap_filter,
                precision_level=precision_level,
                active_signals=list(effective_signals or []),
                fill_low_data=bool(fill_low_data),
                score_provider=enriched_score_provider,
                insider_provider=insider_provider,
                news_provider=news_provider,
                progress_callback=_progress_callback,
                balance_markets=balance_markets,
                data_window_months=horizon_to_months(horizon),
            )
        progress_bar.progress(100, text=f"{analysis_engine} ferdig")
        result = _attach_universe_metadata(
            result,
            scope=scope,
            source_tickers=source_tickers,
            balance_markets=balance_markets,
            fresh_universe=True,
        )
        result["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        result["input_context"] = dict(input_context)
        result["input_fingerprint"] = input_fingerprint
        result["source_tickers"] = list(source_tickers)
        result["analysis_engine"] = analysis_engine
        result["data_source_status"] = build_data_source_status(horizon)
        result["data_window_months"] = horizon_to_months(horizon)
        st.session_state[LAST_RESULT_KEY] = result
        try:
            from services.analysis_pipeline_service import get_analysis_pipeline_service
            from services.state_service import get_state_service
            from services.storage_service import get_storage_service

            stage_id = "early_warning" if analysis_engine == "Early Warning V1" else "alpha_radar"
            get_analysis_pipeline_service(
                state_service=get_state_service(st.session_state),
                storage_service=get_storage_service(),
            ).save_stage_output(
                stage_id,
                result.get("candidates") or [],
                source_label=str(analysis_engine or stage_id),
                context={"scope": scope, "horizon": horizon, "mode": mode, "scanned": result.get("scanned_count")},
                max_items=len(result.get("candidates") or []) or int(limit or 30),
                auto_handoff=True,
            )
        except Exception:
            pass
        st.success(
            f"{analysis_engine} ferdig: viser {len(result.get('candidates') or [])} funn "
            f"av {int(limit)} onsket fra {result.get('scanned_count', 0)} tickere."
        )

    result = st.session_state.get(LAST_RESULT_KEY) or {}
    candidates = result.get("candidates") or []
    result_is_stale = bool(result and result.get("input_fingerprint") != input_fingerprint)
    if result:
        scope_text = html.escape(str(result.get("scope") or scope))
        mode_text = html.escape(str(result.get("mode") or mode))
        created_at = html.escape(str(result.get("created_at") or ""))
        scanned = int(result.get("scanned_count") or 0)
        skipped = int(result.get("skipped_count") or 0)
        low_data = int(result.get("low_data_count") or 0)
        scored = int(result.get("scored_count") or 0)
        excluded = int(result.get("excluded_count") or 0)
        reason_counts = result.get("excluded_reason_counts") if isinstance(result.get("excluded_reason_counts"), dict) else {}
        top_reasons = ", ".join(f"{html.escape(str(reason))}: {count}" for reason, count in list(reason_counts.items())[:4])
        wanted = int(result.get("limit") or limit)
        shown = len(candidates)
        if result_is_stale:
            rerun_label = "Kjor Early Warning V1" if analysis_engine == "Early Warning V1" else "Kjor Alpha Radar V2"
            st.warning(
                f"Valgene er endret siden siste {analysis_engine}-kjoering. "
                f"Resultatet under er gammelt og skjules som aktiv kandidatvisning. Trykk {rerun_label} for ny scan."
            )
        st.markdown(
            f"<div class='alpha-radar-note'>Siste kjoering: <b>{scope_text}</b> | {mode_text} | {created_at} | "
            f"viser <b>{shown}/{wanted}</b>, scannet {scanned}, scoret {scored}, ekskludert {excluded}, lav-data {low_data}, hoppet over {skipped}. "
            "Dette er hypoteser for videre manuell behandling.</div>",
            unsafe_allow_html=True,
        )
        if top_reasons:
            st.caption(f"Viktigste ekskluderinger: {top_reasons}")
        _render_market_audit(result)
        if result.get("parameter_warnings"):
            st.warning("Parameterdisiplin: " + " | ".join(str(x) for x in result.get("parameter_warnings") or []))
        _render_result_actions(result, disabled=result_is_stale)
    if result_is_stale:
        _render_candidates([], grouped=(show_mode == "Gruppert per marked"), empty_label=analysis_engine)
    else:
        _render_candidates(candidates, grouped=(show_mode == "Gruppert per marked"), empty_label=analysis_engine)
