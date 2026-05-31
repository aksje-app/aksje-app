from pathlib import Path

from module_overlap_audit import assess_module_overlap, format_overlap_markdown, get_module_roles


ROOT = Path(__file__).resolve().parent


def test_module_overlap_roles_keep_valuable_differences():
    roles = {role.name: role for role in get_module_roles()}

    assert set(roles) == {"Marked/rangering", "Top Picks", "Smart AI", "Auto Test Lab"}

    assert roles["Marked/rangering"].owns_data_fetch is True
    assert roles["Marked/rangering"].owns_shortlist is False

    assert roles["Top Picks"].owns_data_fetch is False
    assert roles["Top Picks"].owns_shortlist is True

    assert roles["Smart AI"].owns_universe_selection is True
    assert roles["Smart AI"].owns_validation is False

    assert roles["Auto Test Lab"].owns_validation is True
    assert roles["Auto Test Lab"].owns_shortlist is False


def test_overlap_audit_recommends_shared_services_not_single_engine():
    audit = assess_module_overlap()

    assert audit["can_merge_single_engine"] is False
    assert audit["should_share_services"] is True
    assert "Ikke sla" in audit["recommendation"]
    assert any("ranking_service" in action for action in audit["merge_actions"])
    assert any(pair["merge_level"] == "Auto Test Lab er downstream validering" for pair in audit["overlap_pairs"])


def test_overlap_markdown_is_static_and_complete():
    text = format_overlap_markdown()

    for name in ("Marked/rangering", "Top Picks", "Smart AI", "Auto Test Lab"):
        assert name in text
    assert "Tunge kall" in text
    assert "Praktisk sammenslaing" in text


def test_overlap_audit_module_has_no_heavy_dependencies():
    source = (ROOT / "module_overlap_audit.py").read_text(encoding="utf-8")

    blocked_terms = [
        "streamlit",
        "requests",
        "yfinance",
        "finnhub",
        "newsapi",
        "score_stock",
        "auto_rank_market",
        "run_auto_test_lab",
    ]
    for term in blocked_terms:
        assert term not in source


def test_auto_test_lab_ui_shows_static_audit_without_moving_run_gate():
    source = (ROOT / "app.py").read_text(encoding="utf-8", errors="replace")
    start = source.index("def render_auto_test_lab_control_center_v18536")
    end = source.index("# v18.5.43", start)
    segment = source[start:end]

    audit_idx = segment.index("from module_overlap_audit import assess_module_overlap")
    run_button_idx = segment.index("run_clicked = st.button")
    run_gate_idx = segment.index("if run_clicked:")
    heavy_import_idx = segment.index("from auto_test_lab import run_auto_test_lab")

    assert audit_idx < run_button_idx < run_gate_idx < heavy_import_idx
    assert "st.expander(\"Modul-overlapp / sammenslaing\"" in segment








