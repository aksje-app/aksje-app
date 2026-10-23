"""Current release identity, independent of historical feature-test filenames."""
import json
from pathlib import Path
import re


def assert_current_release():
    import app_version as version
    from app_version import get_app_build_label, get_app_version, get_version_contract, validate_version_contract
    assert re.fullmatch(r'v\d+\.\d+\.\d+-rc\d+\.\d+[a-z]*', version.APP_VERSION)
    assert version.APP_VERSION != version.PREVIOUS_APP_VERSION
    assert version.APP_BUILD_LABEL == get_app_build_label() == get_app_version() == version.APP_VERSION
    contract = get_version_contract()
    assert contract['app_version'] == version.APP_VERSION
    assert contract['app_version_name'] == version.APP_VERSION_NAME
    assert validate_version_contract(contract)['ok']
    assert json.loads(json.dumps(contract)) == contract
    root = Path(__file__).resolve().parents[1]
    notes = root / ('RELEASE_NOTES_' + version.APP_VERSION.replace('-rc', '_RC') + '.md')
    assert notes.is_file(), notes
    assert version.APP_VERSION_NAME.strip()
