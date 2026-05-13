
from pathlib import Path
import app_version


def test_version_v18574():
    assert app_version.get_app_version() == "v18.5.74"


def test_normal_mode_removed_and_migrated():
    src = Path("app.py").read_text()
    assert '["Kompakt", "Full"]' in src
    assert '== "normal"' in src.lower()
    assert '["Kompakt", "Normal", "Full"]' not in src


def test_global_button_uses_blue_visible_status_without_overlap():
    src = Path("app.py").read_text()
    assert "v18574-global-status" in src
    assert "linear-gradient(180deg,#38d5ff,#0284c7)" in src
    assert "v18572-inline-spinner" in src
    assert "display:inline-block" in src


def test_analysis_density_classes_present():
    src = Path("app.py").read_text()
    assert "v18574-readable-fund" in src
    assert "v18574-quick-title" in src
    assert "#### ⚡ Hurtigliste med kurs" in src
