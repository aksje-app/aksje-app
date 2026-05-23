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


LAST_RESULT_KEY = "alpha_radar_last_result_v1863au"
ACTIVE_SIGNAL_OPTIONS = [
    "Borsverdi",
    "Insider/bjellesauer",
    "Nyheter/katalysator",
    "Ravarer/makro",
    "Arstid/syklus",
    "Uvanlig volum",
    "Resultater",
]


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


def _default_signals_for_mode(mode: str) -> list[str]:
    defaults = {
        "Skjulte small/mid caps": ["Borsverdi", "Resultater"],
        "Insider og bjellesauer": ["Insider/bjellesauer", "Nyheter/katalysator"],
        "Ravare/makro-medvind": ["Ravarer/makro", "Borsverdi"],
        "Resultat-vendepunkt": ["Resultater", "Nyheter/katalysator"],
        "Uvanlig volum": ["Uvanlig volum", "Nyheter/katalysator"],
        "Kontraer etter fall": ["Resultater", "Borsverdi"],
    }
    return defaults.get(mode, ["Borsverdi", "Nyheter/katalysator", "Resultater"])


def _signal_limit_for_precision(precision_level: str) -> int:
    return 3 if precision_level == "Streng" else 4 if precision_level == "Balansert" else 5


def _required_sources_for_signals(signals: Sequence[str]) -> dict[str, bool]:
    selected = set(str(signal) for signal in signals or [])
    return {
        "news": "Nyheter/katalysator" in selected,
        "insider": "Insider/bjellesauer" in selected,
        "macro": bool({"Ravarer/makro", "Arstid/syklus"} & selected),
        "results": "Resultater" in selected,
    }


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

    a1, a2, a3 = st.columns(3)
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
            grid-template-columns: repeat(6, minmax(82px, 1fr));
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
        }
        div[data-testid="stMultiSelect"] [data-baseweb="tag"] span {
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: clip !important;
            line-height: 1.14 !important;
        }
        div[data-testid="stMultiSelect"] > div {
            min-height: 44px !important;
            align-items: flex-start !important;
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
    cap_text = "-" if market_cap in {None, ""} else f"{float(market_cap):,.0f}".replace(",", " ")
    review = html.escape(str(candidate.get("manual_review") or ""))
    reject_text = "; ".join(str(x) for x in rejects) if rejects else "ingen harde avslag"
    warning_text = "; ".join(str(x) for x in warnings) if warnings else "ingen datavarsler"
    tags = "".join(f"<span class='alpha-radar-tag'>{html.escape(str(signal))}</span>" for signal in signals[:6])
    factor_quality = candidate.get("factor_quality") if isinstance(candidate.get("factor_quality"), Mapping) else {}

    def metric(value_key: str, label: str, quality_key: str | None = None) -> str:
        quality = str(factor_quality.get(quality_key or value_key) or "").strip()
        caption = label if not quality else f"{label} Â· {quality}"
        return f"<div class='alpha-radar-metric'><b>{_fmt_score(candidate.get(value_key))}</b><span>{html.escape(caption)}</span></div>"

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
        {metric("volume_score", "volum", "volume_accumulation")}
        {metric("macro_score", "makro", "macro_second_order")}
      </div>
      <div class="alpha-radar-why">{why_now}</div>
      <div class="alpha-radar-tags">{tags}</div>
      <div class="alpha-radar-reject"><b>Sjekk/avslag:</b> {html.escape(reject_text)}. <b>Datavarsel:</b> {html.escape(warning_text)}. {review}</div>
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
        st.caption("Contrarian / Hidden Potential Score for 1-15 manuelle aksjehypoteser.")
        st.markdown(
            "<div class='alpha-radar-note'>V2 leter etter underdekkede vendepunkter, why-now-signaler, "
            "insider/bjellesauer, uvanlig volum og andreordens makro/ravare-effekter. Kjente/overdekkede "
            "megacaps faar crowding-straff. Ingen handel starter her.</div>",
            unsafe_allow_html=True,
        )

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
        limit = st.slider("Funn", 1, 15, 10, 1, key="alpha_radar_limit_v1863au")

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
        signal_key = f"alpha_radar_signal_lupe_v1863au_{mode}_{precision_level}"
        active_signals = st.multiselect(
            "Signal-lupe",
            ACTIVE_SIGNAL_OPTIONS,
            default=_default_signals_for_mode(mode)[:signal_limit],
            key=signal_key,
            max_selections=signal_limit,
            help=f"Signal-lupe styrer vektingen. Maks {signal_limit} signaler i {precision_level} presisjon.",
        )
        st.caption(f"Signal-lupe = vekting. Maks {signal_limit} signaler i {precision_level}.")

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

    required_sources = _required_sources_for_signals(effective_signals)
    st.caption("Datakilder = datagrunnlag. Kilder som trengs av valgt signal-lupe er laast paa.")

    c7, c8, c9, c10, c11, c12 = st.columns([0.72, 0.72, 0.72, 0.72, 0.78, 0.90])
    with c7:
        max_scan = st.slider("Maks scan", 5, 250, 120, 5, key="alpha_radar_scan_limit_v1863au")
    with c8:
        include_news = st.checkbox(
            "Nyheter",
            value=True,
            key="alpha_radar_news_v1863au",
            disabled=required_sources["news"],
            help="Laast paa naar Signal-lupe bruker Nyheter/katalysator.",
        )
    with c9:
        include_insider_signal = st.checkbox(
            "Insider",
            value=True,
            key="alpha_radar_insider_v1863au",
            disabled=required_sources["insider"],
            help="Laast paa naar Signal-lupe bruker Insider/bjellesauer.",
        )
    with c10:
        include_macro = st.checkbox(
            "Ravarer/makro",
            value=True,
            key="alpha_radar_macro_v1863au",
            disabled=required_sources["macro"],
            help="Laast paa naar Signal-lupe bruker Ravarer/makro eller Arstid/syklus.",
        )
    with c11:
        include_results = st.checkbox(
            "Resultater",
            value=True,
            key="alpha_radar_results_v1863au",
            disabled=required_sources["results"],
            help="Laast paa naar Signal-lupe bruker Resultater.",
        )
    include_news = bool(include_news or required_sources["news"])
    include_insider_signal = bool(include_insider_signal or required_sources["insider"])
    include_macro = bool(include_macro or required_sources["macro"])
    include_results = bool(include_results or required_sources["results"])
    low_data_allowed = precision_level == "Utforskende" and effective_cap_filter not in {"Mikro/small", "Small/mid", "Kun large/mega"}
    with c12:
        fill_low_data = st.checkbox("Fyll opp lav-data", value=False, key="alpha_radar_fill_low_data_v1863au", disabled=not low_data_allowed)
    if not low_data_allowed:
        fill_low_data = False
        st.caption("Lav-data utfylling er blokkert i strenge borsverdi-/presisjonsvalg.")
    include_ipo = False
    if analysis_engine == "Early Warning V1":
        include_ipo = st.checkbox(
            "Merk IPO/pre-IPO som separat omraade",
            value=False,
            key="early_warning_include_ipo_v1863au",
            help="V1 blander ikke IPO/pre-IPO direkte med boersnoterte aksjer. Dette reserverer feltet for separat datadekning.",
        )

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
        if len(source_tickers) < int(max_scan):
            st.caption(
                f"Univers klart: {len(source_tickers)} tickere. Maks scan er {int(max_scan)}, "
                "men valgt univers har ikke flere tilgjengelige tickere akkurat naa. "
                f"Eksempel: {', '.join(source_tickers[:10])}"
            )
        else:
            st.caption(f"Skannes ved neste Kjor: {len(source_tickers)} tickere av maks {int(max_scan)}. Eksempel: {', '.join(source_tickers[:10])}")
    else:
        st.info("Univers-preview er ikke hentet for gjeldende valg. Menyvalg starter ingen scan; trykk Oppdater univers-preview eller Kjor.")

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
        if not source_tickers:
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
        if not source_tickers:
            st.warning("Fant ingen tickere aa skanne for gjeldende valg.")
            return
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
            )
        progress_bar.progress(100, text=f"{analysis_engine} ferdig")
        result["scope"] = scope
        result["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        result["input_context"] = dict(input_context)
        result["input_fingerprint"] = input_fingerprint
        result["source_tickers"] = list(source_tickers)
        result["analysis_engine"] = analysis_engine
        st.session_state[LAST_RESULT_KEY] = result
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
        if result.get("parameter_warnings"):
            st.warning("Parameterdisiplin: " + " | ".join(str(x) for x in result.get("parameter_warnings") or []))
        _render_result_actions(result, disabled=result_is_stale)
    if result_is_stale:
        _render_candidates([], grouped=(show_mode == "Gruppert per marked"), empty_label=analysis_engine)
    else:
        _render_candidates(candidates, grouped=(show_mode == "Gruppert per marked"), empty_label=analysis_engine)
