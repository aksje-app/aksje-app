from __future__ import annotations

import html
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence

import streamlit as st

from alpha_radar_engine import ALPHA_RADAR_MODES, MARKET_CAP_FILTERS, run_alpha_radar


LAST_RESULT_KEY = "alpha_radar_last_result_v1863aq"
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
    review = html.escape(str(candidate.get("manual_review") or ""))
    reject_text = "; ".join(str(x) for x in rejects) if rejects else "ingen harde avslag, men manuell sjekk kreves"
    tags = "".join(f"<span class='alpha-radar-tag'>{html.escape(str(signal))}</span>" for signal in signals[:6])
    return f"""
    <div class="alpha-radar-row">
      <div class="alpha-radar-top">
        <div>
          <div class="alpha-radar-title">{title}</div>
          <div class="alpha-radar-sub">{name} | {market} | {horizon} | {mode}</div>
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
      <div class="alpha-radar-reject"><b>Sjekk/avslag:</b> {html.escape(reject_text)}. {review}</div>
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
    insider_provider: Callable[..., Mapping[str, Any] | None] | None = None,
    news_provider: Callable[..., Sequence[Mapping[str, Any]]] | None = None,
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
            key="alpha_radar_scope_v1863aq",
        )
    with c2:
        mode = st.selectbox("Radar-modus", ALPHA_RADAR_MODES, key="alpha_radar_mode_v1863aq")
    with c3:
        limit = st.slider("Funn", 1, 15, 10, 1, key="alpha_radar_limit_v1863aq")

    c4, c5, c6 = st.columns([0.80, 0.82, 1.38])
    with c4:
        horizon = st.radio("Horisont", ["1m", "3m", "6m", "12m"], horizontal=True, key="alpha_radar_horizon_v1863aq")
    with c5:
        market_cap_filter = st.selectbox("Borsverdi", MARKET_CAP_FILTERS, index=0, key="alpha_radar_cap_v1863aq")
    with c6:
        active_signals = st.multiselect(
            "Signal-lupe",
            ACTIVE_SIGNAL_OPTIONS,
            default=["Borsverdi", "Nyheter/katalysator", "Resultater"],
            key="alpha_radar_signal_lupe_v1863aq",
        )

    c7, c8, c9, c10 = st.columns([0.80, 0.85, 0.85, 0.95])
    with c7:
        max_scan = st.slider("Maks scan", 5, 250, 120, 5, key="alpha_radar_scan_limit_v1863aq")
    with c8:
        include_news = st.checkbox("Bruk nyheter", value=False, key="alpha_radar_news_v1863aq")
    with c9:
        include_insider = st.checkbox("Bruk insider", value=False, key="alpha_radar_insider_v1863aq")
    with c10:
        fill_low_data = st.checkbox("Fyll opp lav-data", value=True, key="alpha_radar_fill_low_data_v1863aq")

    manual_text = ""
    if scope == "Manuell liste":
        manual_text = st.text_area(
            "Manuelle tickere",
            value="",
            placeholder="EQNR.OL, VOLV-B.ST, NOVO-B.CO, NOKIA.HE, PETR4.SA",
            key="alpha_radar_manual_v1863aq",
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
        key="alpha_radar_show_mode_v1863aq",
    )

    run_clicked = st.button(
        "Kjor Alpha Radar V2",
        key="alpha_radar_run_v1863aq",
        type="primary",
        use_container_width=True,
        disabled=not bool(source_tickers),
    )

    if run_clicked and source_tickers:
        with st.spinner(f"Scanner {min(len(source_tickers), int(max_scan))} tickere med Hidden Potential Score..."):
            result = run_alpha_radar(
                source_tickers,
                horizon=horizon,
                limit=int(limit),
                max_scan=int(max_scan),
                include_news=bool(include_news),
                include_insider=bool(include_insider),
                mode=mode,
                market_cap_filter=market_cap_filter,
                active_signals=list(active_signals or []),
                fill_low_data=bool(fill_low_data),
                score_provider=score_provider,
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
        wanted = int(result.get("limit") or limit)
        shown = len(candidates)
        st.markdown(
            f"<div class='alpha-radar-note'>Siste kjoering: <b>{scope_text}</b> | {mode_text} | {created_at} | "
            f"viser <b>{shown}/{wanted}</b>, scannet {scanned}, lav-data {low_data}, hoppet over {skipped}. "
            "Dette er hypoteser for videre manuell behandling.</div>",
            unsafe_allow_html=True,
        )
    _render_candidates(candidates, grouped=(show_mode == "Gruppert per marked"))
