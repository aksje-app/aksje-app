from __future__ import annotations

import html
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence

import streamlit as st

from alpha_radar_engine import ALPHA_RADAR_MODES, MARKET_CAP_FILTERS, PRECISION_LEVELS, normalize_alpha_radar_parameters, run_alpha_radar


LAST_RESULT_KEY = "alpha_radar_last_result_v1863as"
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
    try:
        return f"{float(value):.1f}"
    except Exception:
        return "-"


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
        <div class="alpha-radar-metric"><b>{_fmt_score(candidate.get("underfollowed_score"))}</b><span>oversett</span></div>
        <div class="alpha-radar-metric"><b>{_fmt_score(candidate.get("inflection_score"))}</b><span>vendepunkt</span></div>
        <div class="alpha-radar-metric"><b>{_fmt_score(candidate.get("catalyst_score"))}</b><span>katalysator</span></div>
        <div class="alpha-radar-metric"><b>{_fmt_score(candidate.get("insider_score"))}</b><span>insider</span></div>
        <div class="alpha-radar-metric"><b>{_fmt_score(candidate.get("volume_score"))}</b><span>volum</span></div>
        <div class="alpha-radar-metric"><b>{_fmt_score(candidate.get("macro_score"))}</b><span>makro</span></div>
      </div>
      <div class="alpha-radar-why">{why_now}</div>
      <div class="alpha-radar-tags">{tags}</div>
      <div class="alpha-radar-reject"><b>Sjekk/avslag:</b> {html.escape(reject_text)}. <b>Datavarsel:</b> {html.escape(warning_text)}. {review}</div>
    </div>
    """


def _render_candidates(candidates: Sequence[Mapping[str, Any]], grouped: bool) -> None:
    if not candidates:
        st.info("Ingen Alpha Radar-funn ennaa. Velg univers og trykk Kjor Alpha Radar.")
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
            key="alpha_radar_scope_v1863as",
        )
    with c2:
        mode = st.selectbox("Radar-modus", ALPHA_RADAR_MODES, key="alpha_radar_mode_v1863as")
    with c3:
        limit = st.slider("Funn", 1, 15, 10, 1, key="alpha_radar_limit_v1863as")

    c4, c5, c6, c6b = st.columns([0.78, 0.82, 0.82, 1.28])
    with c4:
        horizon = st.radio("Horisont", ["1m", "3m", "6m", "12m"], horizontal=True, key="alpha_radar_horizon_v1863as")
    with c5:
        cap_options = _cap_options_for_mode(mode)
        market_cap_filter = st.selectbox("Borsverdi", cap_options, index=min(1, len(cap_options) - 1) if mode == "Skjulte small/mid caps" else 0, key="alpha_radar_cap_v1863as")
    with c6:
        precision_level = st.selectbox("Presisjon", PRECISION_LEVELS, index=0, key="alpha_radar_precision_v1863as")
    with c6b:
        active_signals = st.multiselect(
            "Signal-lupe",
            ACTIVE_SIGNAL_OPTIONS,
            default=_default_signals_for_mode(mode),
            key=f"alpha_radar_signal_lupe_v1863as_{mode}",
        )

    normalized_preview = normalize_alpha_radar_parameters(
        mode=mode,
        market_cap_filter=market_cap_filter,
        precision_level=precision_level,
        active_signals=list(active_signals or []),
        fill_low_data=False,
    )
    effective_cap_filter = normalized_preview["market_cap_filter"]
    effective_signals = list(normalized_preview["active_signals"] or [])
    if normalized_preview.get("parameter_warnings"):
        st.warning(" | ".join(normalized_preview["parameter_warnings"]))

    c7, c8, c9, c10, c11, c12 = st.columns([0.72, 0.72, 0.72, 0.72, 0.78, 0.90])
    with c7:
        max_scan = st.slider("Maks scan", 5, 250, 120, 5, key="alpha_radar_scan_limit_v1863as")
    with c8:
        include_news = st.checkbox("Nyheter", value=True, key="alpha_radar_news_v1863as")
    with c9:
        include_insider_signal = st.checkbox("Insider", value=True, key="alpha_radar_insider_v1863as")
    with c10:
        include_macro = st.checkbox("Ravarer/makro", value=True, key="alpha_radar_macro_v1863as")
    with c11:
        include_results = st.checkbox("Resultater", value=True, key="alpha_radar_results_v1863as")
    low_data_allowed = precision_level == "Utforskende" and effective_cap_filter not in {"Mikro/small", "Small/mid", "Kun large/mega"}
    with c12:
        fill_low_data = st.checkbox("Fyll opp lav-data", value=False, key="alpha_radar_fill_low_data_v1863as", disabled=not low_data_allowed)
    if not low_data_allowed:
        fill_low_data = False
        st.caption("Lav-data utfylling er blokkert i strenge borsverdi-/presisjonsvalg.")

    manual_text = ""
    if scope == "Manuell liste":
        manual_text = st.text_area(
            "Manuelle tickere",
            value="",
            placeholder="EQNR.OL, VOLV-B.ST, NOVO-B.CO, NOKIA.HE, PETR4.SA",
            key="alpha_radar_manual_v1863as",
            height=88,
        )

    try:
        source_tickers = list(resolve_tickers(scope, int(max_scan), manual_text) or [])
    except Exception as exc:
        source_tickers = []
        st.warning(f"Kunne ikke hente univers: {exc}")

    if source_tickers:
        st.caption(f"Univers klart: {len(source_tickers)} tickere. Eksempel: {', '.join(source_tickers[:10])}")
    else:
        st.info("Velg univers/marked eller manuell liste. Alpha Radar scorer ingenting foer du trykker Kjor.")

    show_mode = st.radio(
        "Visning",
        ["Samlet rangering", "Gruppert per marked"],
        horizontal=True,
        key="alpha_radar_show_mode_v1863as",
    )

    run_clicked = st.button(
        "Kjor Alpha Radar V2",
        key="alpha_radar_run_v1863as",
        type="primary",
        use_container_width=True,
        disabled=not bool(source_tickers),
    )

    if run_clicked and source_tickers:
        with st.spinner(f"Scanner {min(len(source_tickers), int(max_scan))} tickere med Hidden Potential Score..."):
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
                    mode=mode,
                    active_signals=list(effective_signals or []),
                    news_provider=news_provider,
                    insider_provider=insider_provider,
                    earnings_provider=earnings_provider,
                )

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
            )
        result["scope"] = scope
        result["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        st.session_state[LAST_RESULT_KEY] = result
        st.success(
            f"Alpha Radar V2 ferdig: viser {len(result.get('candidates') or [])} funn "
            f"av {int(limit)} onsket fra {result.get('scanned_count', 0)} tickere."
        )

    result = st.session_state.get(LAST_RESULT_KEY) or {}
    candidates = result.get("candidates") or []
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
    _render_candidates(candidates, grouped=(show_mode == "Gruppert per marked"))
