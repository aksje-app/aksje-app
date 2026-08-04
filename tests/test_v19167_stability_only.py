from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_python_runtime_is_pinned_to_3119() -> None:
    assert (ROOT / 'runtime.txt').read_text(encoding='utf-8').strip() == 'python-3.11.9'
    assert (ROOT / '.python-version').read_text(encoding='utf-8').strip() == '3.11.9'
    render = (ROOT / 'render.yaml').read_text(encoding='utf-8')
    assert 'value: 3.11.9' in render


def test_remember_bridge_is_not_invoked_by_login_paths() -> None:
    auth = (ROOT / 'auth.py').read_text(encoding='utf-8')
    assert '_remember_storage_bridge(bootstrap=True)' not in auth
    assert '_remember_storage_bridge(token, reload_after_store=True)' not in auth
    assert 'SameSite=Strict' in auth
    assert '_remember_token_hash_v19144' in auth
    assert '_set_logged_in(user, remember=bool(remember_me))' in auth


def test_release_has_no_report_or_ui_source_changes_against_manifest() -> None:
    # The release inventory is intentionally limited to authentication/runtime/version/docs.
    allowed = {
        '.python-version', 'auth.py', 'app_version.py',
        'RELEASE_NOTES_v19.16.7.md', 'DEPLOY_v19.16.7.md',
        'tests/test_v19167_stability_only.py',
    }
    inventory = (ROOT / 'CHANGE_INVENTORY_v19.16.7.txt').read_text(encoding='utf-8').splitlines()
    assert set(filter(None, inventory)) == allowed
