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


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _append_log(settings: dict[str, Any], message: str) -> None:
    rows = list(settings.get("drift_activation_log") or [])
    rows.insert(0, {"time": _now(), "message": str(message)})
    settings["drift_activation_log"] = rows[:100]


def _apply_requested_states(requested: dict[str, bool], *, actor: str = "admin") -> dict[str, Any]:
    settings = load_settings()
    before = {key: bool(settings.get(key, False)) for _, _, key, _, _ in STEPS}
    for _, _, key, mirror_key, _ in STEPS:
        value = bool(requested.get(key, False))
        settings[key] = value
        settings[mirror_key] = value
    # Existing safety semantics remain authoritative.
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
        if settings.get("auto_trading_emergency_stop"):
            return "BLOKKERT", "Nødstopp er aktiv"
        return "PÅ", "Produksjonshandel er aktivert"
    return "UKJENT", ""


def render_drift_center(st, *, current_user: dict[str, Any] | None = None) -> None:
    settings = load_settings()
    safety = runtime_safety_snapshot()
    try:
        from drift_recovery import drift_recovery_snapshot
        recovery = drift_recovery_snapshot()
    except Exception as exc:
        recovery = {"paper_storage_persistent": False, "blockers": [str(exc)]}

    st.markdown("## 🧭 Driftssenter")
    st.caption("Alle aktiveringstrinn 1–8 er samlet her. Status lagres varig. Render-miljøvariabler kan ikke endres fra appen og vises derfor som egne krav.")

    requested = {key: bool(settings.get(key, False)) for _, _, key, _, _ in STEPS}
    rows = []
    for number, label, key, _, requirement in STEPS:
        effective, detail = _effective_status(number, settings, safety, recovery)
        rows.append({
            "Steg": number,
            "Funksjon": label,
            "Ønsket": "PÅ" if requested[key] else "AV",
            "Effektiv status": effective,
            "Detalj": detail,
            "Eksternt krav": requirement or "Ingen",
        })
    st.dataframe(rows, width="stretch", hide_index=True)

    with st.form("drift_center_activation_form_v19168", clear_on_submit=False):
        st.markdown("### Aktivering 1–8")
        values: dict[str, bool] = {}
        for number, label, key, _, requirement in STEPS:
            help_text = f"Steg {number}."
            if requirement:
                help_text += f" Krever også: {requirement}."
            if number == 8:
                help_text += " Aktiveres alltid sist."
            values[key] = st.checkbox(
                f"{number}. {label}",
                value=requested[key],
                key=f"drift_center_toggle_{key}_v19168",
                help=help_text,
            )
        production_confirm = st.checkbox(
            "Jeg bekrefter at steg 8 bare skal brukes etter fullført test av steg 1–7",
            value=False,
            key="drift_center_production_confirm_v19168",
        )
        save = st.form_submit_button("Lagre valgte statuser", type="primary", width="stretch")

    if save:
        if values.get("auto_trading_enabled") and not production_confirm:
            st.error("Steg 8 ble ikke lagret: produksjonsbekreftelsen mangler.")
            values["auto_trading_enabled"] = False
        # Fail closed: a later step cannot be active while an earlier step is off.
        first_off = None
        for number, _, key, _, _ in STEPS:
            if not values.get(key):
                first_off = number
                break
        if first_off is not None:
            for number, _, key, _, _ in STEPS:
                if number > first_off:
                    values[key] = False
        actor = str((current_user or {}).get("username") or "admin")
        _apply_requested_states(values, actor=actor)
        st.success("Driftsstatus lagret. Effektiv status avhenger fortsatt av sikkerhetsporter og Render-konfigurasjon.")
        st.rerun()

    a, b = st.columns(2)
    with a:
        if st.button("▶️ Aktiver neste steg", key="drift_center_next_v19168", type="primary", width="stretch"):
            next_step = next((item for item in STEPS if not requested[item[2]]), None)
            if next_step is None:
                st.info("Alle steg er allerede forespurt aktivert.")
            elif next_step[0] == 8:
                st.warning("Steg 8 må aktiveres manuelt med produksjonsbekreftelse.")
            else:
                requested[next_step[2]] = True
                actor = str((current_user or {}).get("username") or "admin")
                _apply_requested_states(requested, actor=f"{actor} aktiverte steg {next_step[0]}")
                st.success(f"Steg {next_step[0]} – {next_step[1]} er forespurt aktivert.")
                st.rerun()
    with b:
        confirm_safe = st.checkbox("Bekreft sikker modus", key="drift_center_safe_confirm_v19168")
        if st.button("🛑 Tilbake til sikker modus", key="drift_center_safe_v19168", disabled=not confirm_safe, width="stretch"):
            actor = str((current_user or {}).get("username") or "admin")
            _safe_mode(actor=actor)
            st.success("Sikker modus er aktivert. Alle steg er AV og nødstopp/full stopp er satt.")
            st.rerun()

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
