"""Renderer module extracted from app.py in v19.2.0.

Business calculations remain in the established services; this module owns only
the Streamlit presentation workflow and uses a compatibility context during the
transition away from the legacy monolith.
"""
from __future__ import annotations
from ui.legacy_context import bind_legacy_context

_PRESERVE = {'render_watchlist_alerts_workspace', 'render_auto_trading_workspace'}

def render_auto_trading_workspace(_legacy_context):
    """Hovedområde for Auto trading / Auto-kjøp parametere. Erstatter stor sidebar-meny."""
    bind_legacy_context(globals(), _legacy_context, preserve=_PRESERVE)
    _settings = load_settings()
    _markets_settings = _settings.get("markets", {}) or {}
    with st.expander("Innstillinger Auto trading-oppsett", expanded=False):
        st.caption("Samlet arbeidsflate for Auto trading. Full stopp / ferie og nødstopp overstyrer alltid disse innstillingene.")
        _render_pushover_test_panel_v18595()
        with st.form("auto_trading_settings_form_v17", clear_on_submit=False):
            st.markdown("<div class='v1863d-auto-form-start'></div>", unsafe_allow_html=True)
            drift_col, buy_col = st.columns(2)
            with drift_col:
                st.markdown("#### Drift")
                _auto_enabled = st.checkbox(
                    "Auto trading aktiv",
                    value=bool(_settings.get("auto_trading_enabled", False)),
                    key="main_auto_enabled_v155",
                )
                _safe_edit = st.checkbox(
                    "Pause når parametere lagres",
                    value=bool(_settings.get("auto_trading_safe_edit_mode", True)),
                    key="main_auto_safe_edit_v155",
                    help="Ved lagring settes auto trading i pause slik at du kan kontrollere parametere før ny start.",
                )
                _top_only = st.checkbox(
                    "Kun Top Picks",
                    value=bool(_settings.get("scan_top_picks_only", True)),
                    key="main_auto_top_only_v155",
                )
                st.markdown("**Markeder**")
                _m_usa = st.checkbox("USA", value=bool(_markets_settings.get("USA", True)), key="main_auto_market_usa_v155")
                _m_no = st.checkbox("Norge", value=bool(_markets_settings.get("NORGE", True)), key="main_auto_market_no_v155")
                _m_se = st.checkbox("Sverige", value=bool(_markets_settings.get("SVERIGE", True)), key="main_auto_market_se_v155")
                _m_fi = st.checkbox("Finland", value=bool(_markets_settings.get("FINLAND", True)), key="main_auto_market_fi_v1863t")
                _m_dk = st.checkbox("Danmark", value=bool(_markets_settings.get("DANMARK", True)), key="main_auto_market_dk_v1863t")
                _m_br = st.checkbox("Brasil", value=bool(_markets_settings.get("BRASIL", False)), key="main_auto_market_br_v1863t")
            with buy_col:
                st.markdown("#### Kjøpsgrenser")
                _min_conf = st.number_input(
                    "Min confidence for BUY",
                    0,
                    100,
                    int(_settings.get("min_buy_confidence", 70)),
                    1,
                    key="main_auto_min_conf_v155",
                )
                _min_score = st.number_input(
                    "Min score for BUY",
                    0.0,
                    10.0,
                    float(_settings.get("min_buy_score", 7.2)),
                    0.1,
                    key="main_auto_min_score_v155",
                )
                _pos_size = st.number_input(
                    "Posisjonsstørrelse %",
                    1.0,
                    100.0,
                    float(_settings.get("position_size_pct", 10.0)),
                    1.0,
                    key="main_auto_pos_size_v155",
                )
                _cooldown = st.number_input(
                    "Cooldown mellom kjøp (min)",
                    0,
                    1440,
                    int(_settings.get("cooldown_minutes", 60)),
                    5,
                    key="main_auto_cooldown_v155",
                )
                try:
                    _rules_for_cooldown = load_rules()
                except Exception:
                    _rules_for_cooldown = {}
                _stop_loss_cooldown_days = st.number_input(
                    "Re-entry etter stop-loss (dager)",
                    0,
                    30,
                    int(_rules_for_cooldown.get("stop_loss_cooldown_days", _settings.get("stop_loss_cooldown_days", 5))),
                    1,
                    key="main_auto_stop_loss_cooldown_days_v1870",
                    help="Blokkerer nytt kjøp i samme ticker etter salg på stop-loss. 0 = av.",
                )
                st.caption("Cooldown mellom kjøp gjelder nye kjøp generelt. Re-entry gjelder samme ticker etter stop-loss.")
            risk_col, safe_col = st.columns(2)
            with risk_col:
                st.markdown("#### Kapasitet / risiko")
                _max_tickers = st.number_input(
                    "Maks aksjer per marked",
                    1,
                    100,
                    int(_settings.get("max_tickers_per_market", 20)),
                    1,
                    key="main_auto_max_tickers_v155",
                )
                _max_pos = st.number_input(
                    "Maks åpne posisjoner",
                    1,
                    30,
                    int(_settings.get("max_open_positions", 5)),
                    1,
                    key="main_auto_max_pos_v155",
                )
                _max_buys = st.number_input(
                    "Maks kjøp per dag",
                    1,
                    50,
                    int(_settings.get("max_buys_per_day", _settings.get("max_trades_per_day", 3))),
                    1,
                    key="main_auto_max_buys_v155",
                )
            with safe_col:
                st.markdown("#### Sikkerhet / varsling")
                _safety_mode = st.checkbox(
                    "Sikkerhetsmodus",
                    value=bool(_settings.get("auto_buy_safety_mode", True)),
                    key="main_auto_safety_mode_v155",
                    help="Når på: nye kjøp stoppes ved dårlig/ugyldig data eller grensebrudd. Salg/exit skal fortsatt få gå.",
                )
                if _safety_mode:
                    st.markdown("<div class='visual-truth-safe-note'>✅ <b>Sikkerhetsmodus er aktiv</b><br/>Blokkerer nye kjøp ved lav cash, dagsgrense, lav confidence eller svak datakvalitet. Salg/exit og nødstopp prioriteres fortsatt.</div>", unsafe_allow_html=True)
                else:
                    st.markdown("<div class='visual-truth-safe-note'>! <b>Sikkerhetsmodus er AV</b><br/>Cash- og dagsgrenser gjelder fortsatt. Ekstra blokkering på confidence/datakvalitet er av.</div>", unsafe_allow_html=True)
                _push = st.checkbox(
                    "Pushover aktiv",
                    value=bool(_settings.get("pushover_enabled", True)),
                    key="main_auto_push_v155",
                )
                st.caption("Full stopp / ferie og nødstopp har alltid høyest prioritet.")
            b1, b2 = st.columns(2)
            with b1:
                save_auto_btn = st.form_submit_button("💾 Lagre auto-innstillinger som ventende", width="stretch")
            with b2:
                reset_auto_btn = st.form_submit_button("Standard Standard auto-innstillinger", width="stretch")
        if save_auto_btn:
            _mark_pending_manual_change("Auto trading-innstillinger endret")
            _current = load_settings()
            _current.update({
                "auto_trading_enabled": bool(_auto_enabled) and not bool(_safe_edit),
                "auto_trading_paused": bool(_safe_edit) if bool(_auto_enabled) else False,
                "auto_trading_emergency_stop": False,
                "auto_trading_safe_edit_mode": bool(_safe_edit),
                "markets": {"USA": bool(_m_usa), "NORGE": bool(_m_no), "SVERIGE": bool(_m_se), "FINLAND": bool(_m_fi), "DANMARK": bool(_m_dk), "BRASIL": bool(_m_br)},
                "max_tickers_per_market": int(_max_tickers),
                "min_buy_confidence": int(_min_conf),
                "min_buy_score": float(_min_score),
                "max_open_positions": int(_max_pos),
                "max_trades_per_day": int(_max_buys),
                "max_buys_per_day": int(_max_buys),
                "position_size_pct": float(_pos_size),
                "cooldown_minutes": int(_cooldown),
                "stop_loss_cooldown_days": int(_stop_loss_cooldown_days),
                "scan_top_picks_only": bool(_top_only),
                "pushover_enabled": bool(_push),
                "auto_buy_safety_mode": bool(_safety_mode),
            })
            save_settings(_current)
            try:
                _r = load_rules()
                _r["max_trades_per_day"] = int(_max_buys)
                _r["max_open_positions"] = int(_max_pos)
                _r["min_buy_confidence"] = int(_min_conf)
                _r["min_buy_score"] = float(_min_score)
                _r["position_size_pct"] = float(_pos_size)
                _r["stop_loss_cooldown_days"] = int(_stop_loss_cooldown_days)
                save_rules(_r)
            except Exception as e:
                logging.warning("Silenced exception restored in v18.6.3: %s", e)
            st.success("Auto-innstillinger lagret som ventende ✅")
        if reset_auto_btn:
            reset_settings()
            st.success("Auto-innstillinger tilbakestilt ✅")
            st.rerun()


def render_watchlist_alerts_workspace(_legacy_context, dynamic_watchlist, pushover_enabled_runtime=False):
    """Returnerer (watchlist_tickers, auto_watchlist_alerts, watchlist_scan_limit, manual_watchlist_scan)."""
    bind_legacy_context(globals(), _legacy_context, preserve=_PRESERVE)
    _settings = load_settings()
    _pushover_env_ok = bool(PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY)
    _pushover_setting_on = bool(_settings.get("pushover_enabled", True))
    _pushover_ready = _pushover_env_ok and _pushover_setting_on

    _default_use_dynamic = bool(_settings.get("use_dynamic_watchlist_from_market", True))
    _default_auto_scan = bool(_settings.get("auto_watchlist_alerts_refresh", False))
    _default_limit = int(_settings.get("watchlist_scan_limit", min(30, max(5, len(dynamic_watchlist or [])))))
    _default_limit = max(5, min(100, _default_limit))
    _watchlist_tickers = list(dynamic_watchlist or [])
    _auto_scan = _default_auto_scan
    _scan_limit = _default_limit
    _manual_scan = False

    with st.expander("🔔 Varsler og dynamisk watchlist", expanded=False):
        st.caption("Fase 2: Watchlist- og varselinnstillinger er flyttet hit fra venstremenyen, nær signalene de styrer.")
        st.caption("Bruk dynamisk liste, manuelle tickere eller begge deler. Pushover-/paper-varselkontroll ligger i Paper Trading.")
        wl_tab, alert_tab = st.tabs(["Watchlist", "Paper-varsel flyttet"])
        with wl_tab:
            c1, c2 = st.columns([1.2, 1])
            with c1:
                _use_dynamic = st.checkbox(
                    "Bruk dynamisk watchlist fra markedet",
                    value=_default_use_dynamic,
                    key="main_use_dynamic_watchlist_v156",
                    help="Når aktiv: watchlisten følger valgt marked og appens egne score/rangeringer.",
                )
                if _use_dynamic:
                    _watchlist_tickers = list(dynamic_watchlist or [])
                    _extra_watchlist_text = st.text_area(
                        "Manuelle tilleggstickere",
                        value=str(_settings.get("manual_watchlist_extra_text_v18611", "")),
                        help="Tickere her blir med selv om dynamisk watchlist er tom. Skill med komma eller linjeskift.",
                        key="main_watchlist_extra_text_v18611",
                    )
                    _extra_watchlist = parse_watchlist(_extra_watchlist_text)
                    if _extra_watchlist:
                        _watchlist_tickers = _dedupe_text_list(list(_watchlist_tickers or []) + list(_extra_watchlist))
                    st.info(f"Dynamisk watchlist aktiv: {len(_watchlist_tickers)} aksjer")
                    with st.expander("Vis dynamisk watchlist", expanded=False):
                        st.write(", ".join(_watchlist_tickers) if _watchlist_tickers else "Ingen tickere i listen ennå.")
                else:
                    _watchlist_text = st.text_area(
                        "Aksjer å overvåke",
                        value=str(_settings.get("manual_watchlist_text_v18611") or ", ".join(list(dynamic_watchlist or [])[:30])),
                        help="Skriv tickere separert med komma. Norske aksjer må ofte ha .OL og svenske .ST",
                        key="main_watchlist_text_v156",
                    )
                    _watchlist_tickers = parse_watchlist(_watchlist_text)
            with c2:
                _auto_scan = st.checkbox(
                    "Auto-scan watchlist ved refresh",
                    value=_default_auto_scan,
                    key="main_auto_watchlist_scan_v156",
                    help="Sender varsel bare når BUY/SELL-signalet endrer seg.",
                )
                _scan_limit = st.slider(
                    "Maks aksjer å scanne for varsler",
                    5,
                    100,
                    _default_limit,
                    key="main_watchlist_scan_limit_v156",
                )
                _manual_scan = st.button("Scan watchlist nå", key="main_scan_watchlist_now_v156")
                if _global_apply_requested_v161():
                    _save = load_settings()
                    _save["use_dynamic_watchlist_from_market"] = bool(_use_dynamic)
                    _save["auto_watchlist_alerts_refresh"] = bool(_auto_scan)
                    _save["watchlist_scan_limit"] = int(_scan_limit)
                    _save["manual_watchlist_extra_text_v18611"] = str(st.session_state.get("main_watchlist_extra_text_v18611", "") or "")
                    _save["manual_watchlist_text_v18611"] = str(st.session_state.get("main_watchlist_text_v156", "") or "")
                    save_settings(_save)
                    st.success("Watchlist-innstillinger oppdatert via Global oppdatering ✅")

        with alert_tab:
            st.info("Varselkontroll for Pushover, paper-handler og antispam er flyttet til Paper Trading og kontroll.")
        if False:
            st.markdown(
                f"""
                <div class="alert-status-pill {'ok' if _pushover_ready else 'bad'}">
                    <div class="alert-status-title">Pushover: {'Aktiv ✅' if _pushover_ready else 'Ikke klar Feil'}</div>
                    <div class="alert-status-sub">Åpne markeder nå: {open_markets()}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            ac1, ac2 = st.columns(2)
            with ac1:
                _pushover_setting_on = st.checkbox(
                    "Pushover aktiv",
                    value=bool(_settings.get("pushover_enabled", True)),
                    key="main_alert_pushover_enabled_v156",
                )
                _notify_trades = st.checkbox(
                    "Varsle ved faktisk paper BUY/SELL",
                    value=bool(_settings.get("notify_paper_trades", True)),
                    key="main_alert_notify_paper_v156",
                )
                _notify_watchlist = st.checkbox(
                    "Varsle ved watchlist signalendring",
                    value=bool(_settings.get("notify_watchlist_signal_changes", True)),
                    key="main_alert_notify_watchlist_v156",
                )
            with ac2:
                _high_conf_only = st.checkbox(
                    "Varsle kun høy confidence",
                    value=bool(_settings.get("notify_high_confidence_only", True)),
                    key="main_alert_high_conf_only_v156",
                )
                _min_alert_conf = st.slider(
                    "Confidence-grense",
                    50,
                    95,
                    int(_settings.get("notify_min_confidence", 80)),
                    1,
                    key="main_alert_min_conf_v156",
                )
                st.caption("Watchlist-varsler bruker denne grensen når høy confidence er aktivert.")

            b1, b2, b3, b4 = st.columns([1, 0.9, 0.9, 0.7])
            with b1:
                if _global_apply_requested_v161():
                    _merged = load_settings()
                    _merged["pushover_enabled"] = bool(_pushover_setting_on)
                    _merged["notify_paper_trades"] = bool(_notify_trades)
                    _merged["notify_watchlist_signal_changes"] = bool(_notify_watchlist)
                    _merged["notify_high_confidence_only"] = bool(_high_conf_only)
                    _merged["notify_min_confidence"] = int(_min_alert_conf)
                    save_settings(_merged)
                    st.success("Varselkontroll oppdatert via Global oppdatering ✅")
            with b2:
                if st.button("Verifiser Verifiser token/user", key="main_alert_verify_pushover_v18585", disabled=not _pushover_env_ok, width="stretch"):
                    verify_info = verify_pushover_credentials_v18585()
                    st.session_state["pushover_last_check_v18585"] = {"type": "verify", **verify_info}
                    if verify_info.get("ok"):
                        st.success(f"Pushover-verifisering OK ✅ HTTP {verify_info.get('status_code')}")
                    else:
                        st.error(f"Pushover-verifisering feilet Feil {verify_info.get('response_text')}")
            with b3:
                if st.button("📣 Send testvarsel", key="main_alert_send_test_v18585", disabled=not _pushover_env_ok, width="stretch"):
                    ok, err = _send_pushover_safe_v1863af("✅ Testvarsel fra AI Aksje Analyzer Pro", "Testvarsel")
                    st.session_state["pushover_last_check_v18585"] = {"type": "send_test", "ok": ok, "error": err}
                    if ok:
                        st.success("Test sendt ✅")
                    else:
                        st.error(f"Feil: {err}")
            with b4:
                if st.button("Nullstill", key="main_alert_reset_antispam_v156", width="stretch"):
                    reset_alert_state()
                    st.success("Signalhistorikk nullstilt ✅")
            with st.expander("Varselinfo / Pushover-status", expanded=False):
                st.caption("Paper BUY/SELL-varsler sendes bare når en faktisk paper-handel utføres.")
                st.caption("Watchlist-varsler sendes ved signalendring, og bruker confidence-grensen hvis høy confidence er aktivert.")
                st.write("TOKEN:", _mask_secret_v18585(PUSHOVER_APP_TOKEN))
                st.write("USER:", _mask_secret_v18585(PUSHOVER_USER_KEY))
                _last = st.session_state.get("pushover_last_check_v18585")
                if _last:
                    st.write("Siste Pushover-sjekk:", _last)
                else:
                    st.caption("Ingen API-verifisering kjørt i denne sesjonen ennå.")

    st.session_state["latest_watchlist_tickers_v156"] = list(_watchlist_tickers or [])
    return _watchlist_tickers, bool(_auto_scan), int(_scan_limit), bool(_manual_scan)
