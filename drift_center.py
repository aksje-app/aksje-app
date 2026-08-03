"""Central, fail-closed operations activation center.

All staged runtime controls live in one persistent settings document. The panel
never mutates Render environment variables; it shows required variables and the
resulting effective state explicitly.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from settings_store import load_settings, save_settings
from runtime_safety import runtime_safety_snapshot

STEPS = (
    (1, "Markedsskanning", "market_scanning_enabled", "background_scanning_enabled", None),
    (2, "Scheduler", "drift_scheduler_enabled", "drift_scheduler_enabled", "REPORT_SCHEDULER_ENABLED=true"),
    (3, "Pushover", "pushover_enabled", "pushover_enabled", "PUSHOVER_APP_TOKEN + PUSHOVER_USER_KEY"),
    (4, "Paper Trading", "drift_paper_trading_enabled", "drift_paper_trading_enabled", "PAPER_TRADING_ENABLED=true"),
    (5, "Papirlager", "paper_storage_enabled", "paper_storage_enabled", "Varig DATABASE_URL eller Render Disk"),
    (6, "Bakgrunnsprosesser", "drift_background_enabled", "drift_background_enabled", "RUNTIME_BACKGROUND_ENABLED=true"),
    (7, "Autonomi", "autonomy_enabled", "autonomy_enabled", None),
    (8, "Produksjonshandel", "auto_trading_enabled", "auto_trading_enabled", "Eksplisitt produksjonsgodkjenning"),
)

_STATUS_META = {
    "PÅ": ("🟢", "Aktiv"),
    "AV": ("🔴", "Av"),
    "VENTER": ("🟡", "Venter"),
    "BLOKKERT": ("🟠", "Blokkert"),
    "UKJENT": ("⚪", "Ukjent"),
}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _append_log(settings: dict[str, Any], message: str) -> None:
    rows = list(settings.get("drift_activation_log") or [])
    rows.insert(0, {"time": _now(), "message": str(message)})
    settings["drift_activation_log"] = rows[:100]


def _apply_requested_states(requested: dict[str, bool], *, actor: str = "admin") -> dict[str, Any]:
    settings = load_settings()
    before = {key: bool(settings.get(key, False)) for _, _, key, _, _ in STEPS}
    prior_requested_ready = all(bool(requested.get(STEPS[i][2], False)) for i in range(7))
    if not prior_requested_ready:
        requested["auto_trading_enabled"] = False
    for _, _, key, mirror_key, _ in STEPS:
        value = bool(requested.get(key, False))
        settings[key] = value
        settings[mirror_key] = value
    if not settings.get("auto_trading_enabled"):
        settings["auto_trading_paused"] = False
    changed = [label for _, label, key, _, _ in STEPS if before.get(key) != bool(settings.get(key))]
    _append_log(settings, f"{actor}: " + ("Endret " + ", ".join(changed) if changed else "Ingen statusendring"))
    save_settings(settings)
    return settings


def _safe_mode(*, actor: str = "admin") -> dict[str, Any]:
    settings = load_settings()
    for _, _, key, mirror_key, _ in STEPS:
        settings[key] = False
        settings[mirror_key] = False
    settings["auto_trading_paused"] = False
    settings["auto_trading_emergency_stop"] = True
    settings["vacation_mode_enabled"] = True
    _append_log(settings, f"{actor}: Tilbake til sikker modus")
    save_settings(settings)
    try:
        from cron_control import activate_full_stop
        activate_full_stop()
    except Exception:
        pass
    return settings


def _effective_status(step: int, settings: dict[str, Any], safety: dict[str, Any], recovery: dict[str, Any]) -> tuple[str, str]:
    requested = bool(settings.get(STEPS[step - 1][2], False))
    if not requested:
        return "AV", "Ikke aktivert i Driftssenter"
    if step == 1:
        return ("PÅ", "Markedsskanning er aktivert") if settings.get("background_scanning_enabled") else ("BLOKKERT", "Skannerinnstilling er AV")
    if step == 2:
        return ("PÅ", safety.get("scheduler_reason") or "Scheduler aktiv") if safety.get("scheduler_enabled") else ("VENTER", safety.get("scheduler_reason") or "Render-innstilling mangler")
    if step == 3:
        return ("PÅ", safety.get("notification_reason") or "Pushover aktiv") if safety.get("notifications_allowed") else ("VENTER", safety.get("notification_reason") or "Pushover-nøkler mangler")
    if step == 4:
        if not bool(settings.get("paper_storage_enabled", False)):
            return "VENTER", "Papirlager steg 5 må aktiveres før Paper Trading kan brukes"
        paper = safety.get("paper_trading") or {}
        return ("PÅ", paper.get("reason") or "Paper Trading aktiv") if paper.get("allowed") else ("VENTER", paper.get("reason") or "Sikkerhetsport blokkerer")
    if step == 5:
        persistent = bool(recovery.get("paper_storage_persistent"))
        return ("PÅ", "Papirlager er varig") if persistent else ("VENTER", "Varig papirlager er ikke tilgjengelig")
    if step == 6:
        return ("PÅ", safety.get("background_reason") or "Bakgrunn aktiv") if safety.get("background_enabled") else ("VENTER", safety.get("background_reason") or "Render-innstilling mangler")
    if step == 7:
        return "PÅ", "Autonomi er tilgjengelig"
    if step == 8:
        # RC4 fail-closed rule: production can never be effective while any
        # prerequisite step 1-7 is not effectively active.
        for prior_step in range(1, 8):
            prior_status, _ = _effective_status(prior_step, settings, safety, recovery)
            if prior_status != "PÅ":
                return "BLOKKERT", f"Steg {prior_step} må være effektivt aktivt først"
        if settings.get("auto_trading_emergency_stop"):
            return "BLOKKERT", "Nødstopp er aktiv"
        return "PÅ", "Produksjonshandel er aktivert"
    return "UKJENT", ""


def _status_label(status: str) -> str:
    icon, text = _STATUS_META.get(status, _STATUS_META["UKJENT"])
    return f"{icon} {text}"


def _render_status_cards(st, rows: list[dict[str, Any]]) -> None:
    st.markdown("### Status trinn 1–8")
    for start in range(0, len(rows), 4):
        cols = st.columns(4)
        for col, row in zip(cols, rows[start:start + 4]):
            with col:
                status = str(row["Effektiv status"])
                st.markdown(f"**Steg {row['Steg']} · {row['Funksjon']}**")
                st.markdown(f"### {_status_label(status)}")
                st.caption(str(row["Detalj"]))


def _first_unavailable_prior(effective_by_step: dict[int, str], target_step: int) -> int | None:
    for step in range(1, target_step):
        if effective_by_step.get(step) != "PÅ":
            return step
    return None


def render_drift_center(st, *, current_user: dict[str, Any] | None = None) -> None:
    settings = load_settings()
    safety = runtime_safety_snapshot()
    try:
        from drift_recovery import drift_recovery_snapshot
        recovery = drift_recovery_snapshot()
    except Exception as exc:
        recovery = {"paper_storage_persistent": False, "blockers": [str(exc)]}

    st.markdown("## 🧭 Driftssenter")
    st.caption("Kontrollert aktivering av trinn 1–8. Status lagres varig, mens Render-miljøkrav vises separat.")

    requested = {key: bool(settings.get(key, False)) for _, _, key, _, _ in STEPS}
    rows: list[dict[str, Any]] = []
    effective_by_step: dict[int, str] = {}
    for number, label, key, _, requirement in STEPS:
        effective, detail = _effective_status(number, settings, safety, recovery)
        effective_by_step[number] = effective
        rows.append({
            "Steg": number,
            "Funksjon": label,
            "Ønsket": "PÅ" if requested[key] else "AV",
            "Effektiv status": effective,
            "Status": _status_label(effective),
            "Detalj": detail,
            "Eksternt krav": requirement or "Ingen",
        })

    active_count = sum(1 for status in effective_by_step.values() if status == "PÅ")
    st.progress(active_count / len(STEPS), text=f"Fremdrift: {active_count} av {len(STEPS)} trinn er effektivt aktive")
    _render_status_cards(st, rows)

    with st.expander("Detaljert status og eksterne krav", expanded=False):
        st.dataframe(rows, width="stretch", hide_index=True)

    st.markdown("### Kontrollert aktivering · steg 1–7")
    st.caption("Velg ønsket status. Senere trinn kan ikke lagres som aktive dersom et tidligere trinn er av.")
    with st.form("drift_center_activation_form_v19170rc3", clear_on_submit=False):
        values: dict[str, bool] = {}
        for number, label, key, _, requirement in STEPS[:7]:
            effective = effective_by_step[number]
            help_text = f"Steg {number}. Effektiv status: {_status_label(effective)}."
            if requirement:
                help_text += f" Krever også: {requirement}."
            values[key] = st.checkbox(
                f"{number}. {label} · {_status_label(effective)}",
                value=requested[key],
                key=f"drift_center_toggle_{key}_v19170rc3",
                help=help_text,
            )
        save = st.form_submit_button("Lagre trinn 1–7", type="primary", width="stretch")

    if save:
        values["auto_trading_enabled"] = requested.get("auto_trading_enabled", False)
        first_off = None
        for number, _, key, _, _ in STEPS[:7]:
            if not values.get(key):
                first_off = number
                break
        if first_off is not None:
            for number, _, key, _, _ in STEPS[:7]:
                if number > first_off:
                    values[key] = False
        actor = str((current_user or {}).get("username") or "admin")
        with st.status("Lagrer og kontrollerer driftsstatus …", expanded=True) as status_box:
            st.write("Kontrollerer rekkefølge og sikkerhetsporter …")
            _apply_requested_states(values, actor=actor)
            st.write("Lagrer varig konfigurasjon …")
            st.write("Oppdaterer effektiv status …")
            status_box.update(label="Driftsstatus er lagret", state="complete", expanded=True)
        st.rerun()

    left, right = st.columns(2)
    with left:
        if st.button("▶️ Aktiver neste steg", key="drift_center_next_v19170rc3", type="primary", width="stretch"):
            next_step = next((item for item in STEPS[:7] if not requested[item[2]]), None)
            if next_step is None:
                st.info("Steg 1–7 er allerede forespurt aktivert. Produksjonshandel håndteres separat nederst.")
            else:
                blocker = _first_unavailable_prior(effective_by_step, next_step[0])
                if blocker is not None:
                    st.error(f"Steg {next_step[0]} kan ikke aktiveres ennå. Steg {blocker} må først ha effektiv status Aktiv.")
                else:
                    actor = str((current_user or {}).get("username") or "admin")
                    with st.status(f"Aktiverer steg {next_step[0]} – {next_step[1]} …", expanded=True) as status_box:
                        st.write("Kontrollerer tidligere trinn … OK")
                        requested[next_step[2]] = True
                        _apply_requested_states(requested, actor=f"{actor} aktiverte steg {next_step[0]}")
                        st.write("Lagrer ønsket status … OK")
                        st.write("Kontrollerer eksterne krav …")
                        status_box.update(label=f"Steg {next_step[0]} er forespurt aktivert", state="complete", expanded=True)
                    st.rerun()
    with right:
        confirm_safe = st.checkbox("Bekreft sikker modus", key="drift_center_safe_confirm_v19170rc3")
        if st.button("🛑 Tilbake til sikker modus", key="drift_center_safe_v19170rc3", disabled=not confirm_safe, width="stretch"):
            actor = str((current_user or {}).get("username") or "admin")
            with st.status("Aktiverer sikker modus …", expanded=True) as status_box:
                st.write("Slår av trinn 1–8 …")
                _safe_mode(actor=actor)
                st.write("Aktiverer nødstopp og full stopp …")
                status_box.update(label="Sikker modus er aktivert", state="complete", expanded=True)
            st.rerun()

    st.divider()
    st.markdown("## ⚠️ Produksjonshandel · steg 8")
    st.warning("Produksjonshandel er siste trinn og skal bare aktiveres etter at steg 1–7 er testet uten 502-feil, instansrestart eller uavklarte sikkerhetsporter.")
    production_effective = effective_by_step[8]
    st.markdown(f"**Nåværende status:** {_status_label(production_effective)} — {rows[7]['Detalj']}")

    prior_ready = all(effective_by_step.get(step) == "PÅ" for step in range(1, 8))
    production_confirm = st.checkbox(
        "Jeg bekrefter at steg 1–7 er ferdig testet og at produksjonshandel kan aktiveres",
        key="drift_center_production_confirm_v19170rc3",
        disabled=not prior_ready,
    )
    prod_a, prod_b = st.columns(2)
    with prod_a:
        if st.button(
            "⚠️ Aktiver produksjonshandel",
            key="drift_center_enable_production_v19170rc3",
            type="primary",
            disabled=not (prior_ready and production_confirm) or requested.get("auto_trading_enabled", False),
            width="stretch",
        ):
            requested["auto_trading_enabled"] = True
            actor = str((current_user or {}).get("username") or "admin")
            _apply_requested_states(requested, actor=f"{actor} aktiverte produksjonshandel")
            st.success("Produksjonshandel er forespurt aktivert. Sikkerhetsporter og nødstopp er fortsatt autoritative.")
            st.rerun()
    with prod_b:
        if st.button(
            "Deaktiver produksjonshandel",
            key="drift_center_disable_production_v19170rc3",
            disabled=not requested.get("auto_trading_enabled", False),
            width="stretch",
        ):
            requested["auto_trading_enabled"] = False
            actor = str((current_user or {}).get("username") or "admin")
            _apply_requested_states(requested, actor=f"{actor} deaktiverte produksjonshandel")
            st.success("Produksjonshandel er deaktivert.")
            st.rerun()

    if not prior_ready:
        missing = [str(step) for step in range(1, 8) if effective_by_step.get(step) != "PÅ"]
        st.info("Produksjonsaktivering er låst. Følgende trinn er ikke effektivt aktive: " + ", ".join(missing))

    with st.expander("Render-krav og aktiveringshjelp", expanded=False):
        st.markdown(
            "- Scheduler: `REPORT_SCHEDULER_ENABLED=true` og i testmiljø `ALLOW_SCHEDULER_IN_TEST=true`.\n"
            "- Pushover: `PUSHOVER_APP_TOKEN`, `PUSHOVER_USER_KEY` og i testmiljø `ALLOW_NOTIFICATIONS_IN_TEST=true`.\n"
            "- Paper Trading: `PAPER_TRADING_ENABLED=true` og i testmiljø `ALLOW_PAPER_TRADING_IN_TEST=true`.\n"
            "- Bakgrunn: `RUNTIME_BACKGROUND_ENABLED=true`, `ENABLE_WEB_BACKGROUND_SERVICES=true` og i testmiljø `ALLOW_BACKGROUND_IN_TEST=true`.\n"
            "- Produksjonshandel skal ikke aktiveres før steg 1–7 er testet uten 502 eller instansrestart."
        )

    with st.expander("Endringslogg", expanded=False):
        log_rows = list(settings.get("drift_activation_log") or [])
        if log_rows:
            st.dataframe(log_rows, width="stretch", hide_index=True)
        else:
            st.info("Ingen endringer er registrert ennå.")


__all__ = ["STEPS", "render_drift_center"]
