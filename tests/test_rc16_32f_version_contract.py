from app_version import APP_BUILD_LABEL, APP_VERSION, APP_VERSION_NAME, PREVIOUS_APP_VERSION


def test_rc16_32f_is_canonical_runtime_version():
    assert APP_VERSION == 'v19.22.0-rc16.32f'
    assert APP_BUILD_LABEL == APP_VERSION
    assert '16.32f' in APP_VERSION_NAME
    assert PREVIOUS_APP_VERSION == 'v19.22.0-rc16.32e'
