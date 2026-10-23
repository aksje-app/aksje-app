from app_version import APP_BUILD_LABEL, APP_VERSION, APP_VERSION_NAME, PREVIOUS_APP_VERSION, get_app_build_label, get_version_contract


def test_current_release_is_canonical_runtime_version():
    from release_contract_checks import assert_current_release
    assert_current_release()
