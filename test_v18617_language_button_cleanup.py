from pathlib import Path
import py_compile


ROOT = Path(__file__).resolve().parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="ignore")


def test_core_files_do_not_have_classic_mojibake_markers():
    markers = [
        chr(0x00C3),
        chr(0x00C2),
        chr(0x00E2) + chr(0x20AC),
        chr(0x00F0) + chr(0x0178),
        chr(0xFFFD),
    ]
    for name in ["app.py", "app_version.py"]:
        py_compile.compile(str(ROOT / name), doraise=True)
        text = _read(name)
        for marker in markers:
            assert marker not in text


def test_v18617_compact_buttons_and_version_label():
    app = _read("app.py")
    version = _read("app_version.py")

    assert 'APP_VERSION = "v18.6.24"' in version
    assert "Sarskilt bannerklikk, fart og kompakte knapper" in version
    assert "v18.6.19: final compact action style" in app
    assert "max-width: min(100%, 220px) !important;" in app
    assert "rgba(20,83,45,.74)" in app
    assert "Hvorfor dette signalet?" in app
    assert chr(0x00F0) + chr(0x0178) not in app




