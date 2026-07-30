from pathlib import Path

from daily_user_experience import (
    ADVANCED_MODE,
    SIMPLE_MODE,
    build_attention_items,
    candidate_action_payload,
    get_user_mode,
    navigation_for_mode,
    set_user_mode,
    status_label,
)

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
SIDEBAR = (ROOT / "ui_sidebar_stable.py").read_text(encoding="utf-8")
VERSION = (ROOT / "app_version.py").read_text(encoding="utf-8")


def test_version_and_changelog():
    assert 'APP_VERSION = "v19.14.6"' in VERSION
    assert "Forenklet daglig brukeropplevelse" in VERSION


def test_mode_is_saved_per_user_and_simple_is_default():
    settings = {}
    assert get_user_mode(settings, {"username": "per"}) == SIMPLE_MODE
    settings = set_user_mode(settings, {"username": "per"}, ADVANCED_MODE)
    assert get_user_mode(settings, {"username": "per"}) == ADVANCED_MODE
    assert get_user_mode(settings, {"username": "anne"}) == SIMPLE_MODE


def test_simple_navigation_has_four_daily_areas_and_more():
    nav = navigation_for_mode(SIMPLE_MODE)
    assert [x[1] for x in nav["primary"]] == ["Oversikt", "Rapport", "Analyse", "Portefølje"]
    assert [x[1] for x in nav["more"]] == [
        "Autonomi", "Paper Trading", "Godkjenninger", "Jobber",
        "Varsler", "Valuta", "Drift", "Innstillinger",
    ]


def test_advanced_mode_keeps_specialist_panels():
    labels = [x[1] for x in navigation_for_mode(ADVANCED_MODE)["primary"]]
    assert {"Top Picks", "Long Engine", "AI-verktøy", "System"}.issubset(labels)


def test_sidebar_renders_global_mode_and_more_group():
    assert "_render_daily_mode_selector_v19022" in SIDEBAR
    assert '"Visning"' in SIDEBAR
    assert 'st.sidebar.expander("☰ Mer"' in SIDEBAR
    assert "navigation_for_mode" in SIDEBAR


def test_simple_mode_uses_responsive_sidebar_without_duplicate_mobile_dom():
    assert "Do not inject a second mobile/navigation DOM into the main page" in APP
    assert 'st.sidebar.expander("☰ Mer"' in SIDEBAR
    experience = (ROOT / "daily_user_experience.py").read_text(encoding="utf-8")
    for label in ("Oversikt", "Rapport", "Analyse", "Portefølje"):
        assert label in experience


def test_attention_home_is_task_based_and_read_only():
    assert "render_daily_attention_dashboard_v19022" in APP
    assert "Hva trenger oppmerksomhet nå?" in APP
    assert "Ingen ny markedshenting startes her" in APP
    for action in ("Kjør rapport", "Siste rapport", "Se endringer", "Godkjenninger", "Drift"):
        assert action in APP


def test_attention_contract_prioritises_real_problems():
    items = build_attention_items([{
        "report_label": "Kveldsrapport", "has_errors": True, "error_count": 2,
        "report_reliability": 52, "reserve_feed_used": True, "urgent_task_count": 1,
    }], pending_approvals=2, scheduler_ok=False, max_items=10)
    codes = {x["code"] for x in items}
    assert {"REPORT_ERRORS", "LOW_RELIABILITY", "RESERVE_FEED", "PENDING_APPROVALS", "SCHEDULER_ERROR"}.issubset(codes)
    assert items[0]["severity"] == "critical"


def test_candidate_cards_have_direct_actions_and_details():
    assert "_render_candidate_actions_v19022" in APP
    for label in ("📈 Analyse", "👁 Overvåk", "🧾 Paper", "↻ Oppdater"):
        assert label in APP
    for label in ("Beslutning", "Kilder", "Hendelser", "Historikk", "Eksport"):
        assert label in APP
    assert "Last ned kandidatanalyse som JSON" in APP


def test_candidate_payload_and_statuses_are_norwegian():
    payload = candidate_action_payload({
        "ticker": "eqnr.ol", "candidate_state": "review", "blockers": ["Mangler kilde"],
        "change_conditions": ["Ny verifisering"], "sources": ["E24"],
    })
    assert payload["ticker"] == "EQNR.OL"
    assert payload["status"] == "Krever vurdering"
    assert status_label("ready") == "Beslutningsklar"
    assert status_label("draft") == "Foreløpig"
    assert status_label("final") == "Endelig"
    assert status_label("HOLD / WAIT") == "Vent"


def test_simple_mode_drives_compact_layout_without_changing_logic():
    assert 'APP_VIEW_MODE = "Kompakt" if _early_ui_mode_v19022 == UX_SIMPLE_MODE_V19022 else "Full"' in APP
    assert "Ingen analyse-, handels-, risiko-, autonomi- eller porteføljeregler er endret" in VERSION
