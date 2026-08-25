from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_python_runtime_is_pinned_to_31213() -> None:
    assert (ROOT / 'runtime.txt').read_text(encoding='utf-8').strip() == 'python-3.12.13'
    assert (ROOT / '.python-version').read_text(encoding='utf-8').strip() == '3.12.13'
    render = (ROOT / 'render.yaml').read_text(encoding='utf-8')
    assert render.count('value: 3.12.13') == 2


def test_remember_bridge_is_not_invoked_by_login_paths() -> None:
    auth = (ROOT / 'auth.py').read_text(encoding='utf-8')
    assert '_remember_storage_bridge(bootstrap=True)' not in auth
    assert '_remember_storage_bridge(token, reload_after_store=True)' not in auth
    assert 'SameSite=Strict' in auth
    assert '_remember_token_hash_v19144' in auth
    assert '_set_logged_in(user, remember=bool(remember_me))' in auth


def test_distribution_keeps_only_current_root_release_contract() -> None:
    from app_version import APP_VERSION

    tag = APP_VERSION.replace('-rc', '_RC')
    current = {
        f'RELEASE_NOTES_{tag}.md', f'ACCEPTANCE_{tag}.md', f'DEPLOY_{tag}.md',
    }
    release_docs = {
        path.name for pattern in ('RELEASE_NOTES_*.md', 'ACCEPTANCE_*.md', 'DEPLOY_*.md')
        for path in ROOT.glob(pattern)
    }
    assert release_docs == current
    assert not list(ROOT.glob('CHANGE_INVENTORY_*.txt'))
