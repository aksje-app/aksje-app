from app_version import APP_BUILD_LABEL, APP_VERSION, APP_VERSION_NAME, PREVIOUS_APP_VERSION


def test_rc16_32f_is_canonical_runtime_version():
    from release_contract_checks import assert_current_release
    assert_current_release()
