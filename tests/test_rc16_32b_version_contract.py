from app_version import APP_BUILD_LABEL, APP_VERSION, APP_VERSION_NAME, PREVIOUS_APP_VERSION, get_app_build_label, get_version_contract


def test_rc16_32b_is_canonical_runtime_version():
    assert APP_VERSION == "v19.22.0-rc16.32b"
    assert APP_BUILD_LABEL == APP_VERSION
    assert get_app_build_label() == APP_VERSION
    assert "16.32b" in APP_VERSION_NAME
    assert PREVIOUS_APP_VERSION == "v19.22.0-rc16.32a"
    contract = get_version_contract()
    assert contract["app_version"] == APP_VERSION
    assert contract["app_version_name"] == APP_VERSION_NAME
