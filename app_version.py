APP_VERSION = "v18.5.70"
APP_VERSION_NAME = "Loading Global Version Fix"
APP_BUILD_LABEL = f"{APP_VERSION} {APP_VERSION_NAME}"
APP_BUILD_ID = "v18570-loading-global-no-dim"

def get_app_version() -> str:
    return APP_VERSION

def get_app_build_label() -> str:
    return APP_BUILD_LABEL

def get_app_build_id() -> str:
    return APP_BUILD_ID
